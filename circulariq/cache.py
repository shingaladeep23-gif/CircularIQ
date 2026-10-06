"""Semantic cache: reuse the answer to a near-identical earlier question, skipping retrieval and the LLM.

A hit needs BOTH cosine similarity >= THRESHOLD AND an identical signature (entity types, acronyms, codes,
numbers). The signature guard exists because this corpus issues near-identical circulars per entity type:
"...for commercial banks?" and "...for small finance banks?" embed almost identically but have different
answers. Entries are dropped when a circular they cite changes, and abstentions are dropped when new
circulars arrive (the new text might answer them).
"""
import json
import os
import re
from pathlib import Path

import numpy as np

THRESHOLD = 0.95
CACHE_PATH = Path(os.environ.get("CIRCULARIQ_CACHE", "data/cache/semantic.jsonl"))

ENTITIES = {
    "commercial bank": r"commercial banks?|\bscbs?\b",
    "small finance bank": r"small finance banks?|\bsfbs?\b",
    "payments bank": r"payments? banks?",
    "urban co-operative bank": r"urban co-?operative banks?|\bucbs?\b",
    "rural co-operative bank": r"rural co-?operative banks?",
    "regional rural bank": r"regional rural banks?|\brrbs?\b",
    "local area bank": r"local area banks?",
    "nbfc": r"\bnbfcs?\b|non-banking financial compan",
    "aifi": r"\baifis?\b|all india financial institution",
    "housing finance company": r"housing finance compan|\bhfcs?\b",
    "authorised dealer": r"authori[sz]ed dealer|\bad (?:category|cat)",
    "primary dealer": r"primary dealer",
    "credit information company": r"credit information compan",
    "asset reconstruction company": r"asset reconstruction compan|\barcs?\b",
}


def signature(question: str) -> list[str]:
    """What must match exactly for two questions to share an answer."""
    low = question.lower()
    ents = {name for name, pat in ENTITIES.items() if re.search(pat, low)}
    acronyms = set(re.findall(r"\b[A-Z][A-Z0-9]{1,}(?:\([A-Z]\))?", question)) - {"RBI", "I"}
    codes = set(re.findall(r"[A-Za-z]*\d[\w./()-]*", question))  # R343, 2026-27, RBI/2026-27/273, 2026
    return sorted(ents | {a.upper() for a in acronyms} | {c.lower() for c in codes})


class SemanticCache:
    def __init__(self, path: Path | None = CACHE_PATH, embed=None, threshold: float = THRESHOLD):
        """embed(list[str]) -> normalised vectors; defaults to the retriever's bge-small."""
        self.path, self.threshold, self._embed = path, threshold, embed
        self.entries: list[dict] = []
        if path and path.exists():
            self.entries = [json.loads(l) for l in path.open(encoding="utf-8")]

    def embed(self, text: str) -> np.ndarray:
        if self._embed is None:
            from circulariq.retrieve import embedder
            self._embed = lambda xs: embedder().encode(xs, normalize_embeddings=True)
        return np.asarray(self._embed([text])[0], dtype="float32")

    def get(self, question: str) -> dict | None:
        if not self.entries:
            return None
        sims = np.asarray([e["vec"] for e in self.entries], dtype="float32") @ self.embed(question)
        best = int(np.argmax(sims))
        e = self.entries[best]
        if sims[best] >= self.threshold and e["sig"] == signature(question):
            return {**e["result"], "cache": {"hit": True, "similarity": float(sims[best]), "matched": e["question"]}}
        return None

    def put(self, question: str, result: dict):
        entry = {"question": question, "vec": self.embed(question).round(5).tolist(), "sig": signature(question),
                 "nids": sorted({h["nid"] for h in result.get("sources", []) + result.get("hits", [])}),
                 "result": {k: v for k, v in result.items() if k != "cache"}}
        self.entries.append(entry)
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def invalidate(self, changed_nids: set[int], new_circulars: bool = False) -> int:
        """Drop answers that relied on a changed circular; if circulars were added, drop abstentions too."""
        keep = [e for e in self.entries
                if not set(e["nids"]) & changed_nids and not (new_circulars and e["result"].get("abstained"))]
        dropped = len(self.entries) - len(keep)
        self.entries = keep
        if self.path and dropped:
            self.path.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in keep), encoding="utf-8")
        return dropped


def changed_circulars(old_chunks: list[dict], new_chunks: list[dict]) -> tuple[set[int], bool]:
    """(notification ids whose text changed or disappeared, whether any new notification appeared)."""
    def by_nid(chunks):
        out: dict[int, list[str]] = {}
        for c in chunks:
            out.setdefault(c["nid"], []).append(c["text"])
        return out

    old, new = by_nid(old_chunks), by_nid(new_chunks)
    changed = {n for n in old if old[n] != new.get(n)}
    return changed, bool(set(new) - set(old))
