"""Hybrid retrieval: BM25 + dense (bge-small, FAISS), fused with Reciprocal Rank Fusion,
then re-ranked by a cross-encoder.

python -m circulariq.retrieve            ->  builds data/index/ from data/chunks.jsonl
python -m circulariq.retrieve "question" ->  prints the top hybrid hits
"""
import json
import os
import re
import sys
from pathlib import Path

import faiss
import numpy as np
from rank_bm25 import BM25Okapi

EMBED_MODEL = "BAAI/bge-small-en-v1.5"
RERANK_MODEL = os.environ.get("CIRCULARIQ_RERANKER", "cross-encoder/ms-marco-MiniLM-L-6-v2")
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "  # bge-v1.5 query instruction
INDEX_DIR = Path(os.environ.get("CIRCULARIQ_INDEX", "data/index"))
RRF_K = 60

_models = {}


def embedder():
    if "embed" not in _models:
        from sentence_transformers import SentenceTransformer
        _models["embed"] = SentenceTransformer(EMBED_MODEL)
    return _models["embed"]


def reranker():
    if "rerank" not in _models:
        import torch
        from sentence_transformers import CrossEncoder
        # explicit sigmoid: MiniLM emits raw logits, bge-reranker probabilities; this makes both [0, 1]
        _models["rerank"] = CrossEncoder(RERANK_MODEL, max_length=512, activation_fn=torch.nn.Sigmoid())
    return _models["rerank"]


def doc_text(c: dict) -> str:
    """What gets indexed: the chunk plus its circular title, section and (short circulars) lead
    paragraph, so paragraphs that never name their subject stay findable. Citations use c['text'] only."""
    lead = f"{c['lead']}\n" if c.get("lead") else ""
    return f"{c['title']}\n{c['section']}\n{lead}{c['text']}"


def tokenize(text: str) -> list[str]:
    """Lowercase word tokens. Codes are indexed at three levels so any of them can match:
    DOR.AML.REC.233/14.06.001/2026-27 -> the whole code, its '/' segments (dor.aml.rec.233,
    2026-27), and their atoms (dor, aml, rec, 233, 2026, 27)."""
    out = []
    for tok in re.findall(r"[a-z0-9]+(?:[./()-][a-z0-9]+)*", text.lower()):
        out.append(tok)
        segs = [s for s in tok.split("/") if s]
        if len(segs) > 1:
            out.extend(segs)
        for seg in segs:
            atoms = [a for a in re.split(r"[.()-]", seg) if a]
            if len(atoms) > 1:
                out.extend(atoms)
    return out


def rrf(rankings: list[list[int]], k: int = RRF_K) -> list[tuple[int, float]]:
    """Reciprocal Rank Fusion: score(d) = sum over lists of 1 / (k + rank), rank starting at 1."""
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, doc in enumerate(ranking, start=1):
            scores[doc] = scores.get(doc, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda x: -x[1])


def build(chunks: list[dict], index_dir: Path = INDEX_DIR):
    index_dir.mkdir(parents=True, exist_ok=True)
    vecs = embedder().encode([doc_text(c) for c in chunks], batch_size=32, normalize_embeddings=True, show_progress_bar=True)
    index = faiss.IndexFlatIP(vecs.shape[1])  # exact cosine search (vectors are normalised)
    index.add(np.asarray(vecs, dtype="float32"))
    faiss.write_index(index, str(index_dir / "dense.faiss"))
    with (index_dir / "chunks.jsonl").open("w", encoding="utf-8") as f:
        f.writelines(json.dumps(c, ensure_ascii=False) + "\n" for c in chunks)


class Retriever:
    def __init__(self, index_dir: Path = INDEX_DIR):
        self.chunks = [json.loads(l) for l in (index_dir / "chunks.jsonl").open(encoding="utf-8")]
        self.index = faiss.read_index(str(index_dir / "dense.faiss"))
        # BM25 also sees the circular's ref and number, so exact-ID queries hit
        self.bm25 = BM25Okapi([tokenize(f"{c['ref']} {c['circular_no']} {doc_text(c)}") for c in self.chunks])
        # recency: nid -> newer circulars in the corpus that cite it (and so may amend it)
        circ = {c["nid"]: c for c in self.chunks}
        self.cited_by: dict[int, list[dict]] = {}
        for c in circ.values():
            for old in c.get("references", []):
                if old in circ and circ[old]["date"] <= c["date"]:
                    self.cited_by.setdefault(old, []).append({k: c[k] for k in ("nid", "ref", "date", "title", "url")})

    def bm25_search(self, query: str, k: int = 50) -> list[tuple[int, float]]:
        scores = self.bm25.get_scores(tokenize(query))
        top = np.argsort(-scores)[:k]
        return [(int(i), float(scores[i])) for i in top if scores[i] > 0]

    def dense_search(self, query: str, k: int = 50) -> list[tuple[int, float]]:
        q = embedder().encode([QUERY_PREFIX + query], normalize_embeddings=True)
        scores, ids = self.index.search(np.asarray(q, dtype="float32"), k)
        return [(int(i), float(s)) for i, s in zip(ids[0], scores[0]) if i >= 0]

    def hybrid_search(self, query: str, k: int = 50) -> list[tuple[int, float]]:
        lists = [[i for i, _ in self.bm25_search(query, k)], [i for i, _ in self.dense_search(query, k)]]
        return rrf(lists)[:k]

    def rerank(self, query: str, ids: list[int], top: int = 5) -> list[tuple[int, float]]:
        """Cross-encoder reads (query, chunk) together; returns relevance in [0, 1]."""
        if not ids:
            return []
        scores = np.asarray(reranker().predict([(query, doc_text(self.chunks[i])) for i in ids], batch_size=16))
        order = np.argsort(-scores)[:top]
        return [(ids[j], float(scores[j])) for j in order]

    def search(self, query: str, mode: str = "hybrid", k: int = 50) -> list[dict]:
        """mode: bm25 | dense | hybrid | rerank (hybrid top-50 re-scored by the cross-encoder, top k)."""
        if mode == "rerank":
            hits = self.rerank(query, [i for i, _ in self.hybrid_search(query, 50)], top=k)
        else:
            hits = {"bm25": self.bm25_search, "dense": self.dense_search, "hybrid": self.hybrid_search}[mode](query, k)
        return [{**self.chunks[i], "score": s, "idx": i, "cited_by": self.cited_by.get(self.chunks[i]["nid"], [])}
                for i, s in hits]


if __name__ == "__main__":
    if len(sys.argv) > 1:
        for h in Retriever().search(" ".join(sys.argv[1:]))[:5]:
            print(f"{h['score']:.4f}  {h['ref']}  para {h['para']}  {h['text'][:100]}")
    else:
        build([json.loads(l) for l in open("data/chunks.jsonl", encoding="utf-8")])
        print(f"index written to {INDEX_DIR}")
