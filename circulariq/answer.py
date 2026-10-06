"""The answering pipeline. Every optional stage is a Config flag so the evaluator can ablate it:

Question -> [semantic cache] -> [router] -> [rewrite] -> hybrid retrieve + re-rank -> score gate
         -> [corrective RAG] -> LLM answer with [S#] citations -> rendered citations, or abstain

python -m circulariq.answer "What is the tear size limit for unfit notes?"
"""
import os
import re
import sys
from dataclasses import dataclass

from circulariq import crag, router
from circulariq.retrieve import rrf

ABSTAIN = "Not found in the provided circulars."
MIN_RERANK_SCORE = float(os.environ.get("CIRCULARIQ_MIN_SCORE", "0.05"))  # below this, don't even ask the LLM
TOP_K = 5  # passages given to the LLM
SEARCH_K = 10  # passages retrieved (and shown); MRR@10 is computed on these


@dataclass(frozen=True)
class Config:
    mode: str = "rerank"  # bm25 | dense | hybrid | rerank (hybrid top 50 re-scored by the cross-encoder)
    rewrite: bool = False  # rewrite every question first; lowered recall in the eval (decisions D6.14)
    router: bool = False  # route by question type: router.py
    crag: bool = False  # grade passages, retry retrieval, else abstain: crag.py
    semantic_cache: bool = False  # reuse answers to near-identical questions: cache.py
    min_score: float = MIN_RERANK_SCORE  # re-ranker score gate; 0 disables it
    top_k: int = TOP_K

SYSTEM = f"""You answer questions about Reserve Bank of India (RBI) circulars for bank compliance officers.
Rules:
1. Use ONLY the numbered sources given. Never use outside knowledge.
2. After every sentence that states a fact, cite its source(s) like [S1] or [S2][S4].
3. If the sources do not contain the answer, reply with exactly: {ABSTAIN}
4. If two sources conflict, follow the newer one (later date) and say that the older instruction was amended.
5. Be concise: 1-5 sentences, plain language, keep exact numbers, limits and dates from the sources."""

REWRITE = """Rewrite the user's question into one precise search query for RBI regulations.
Expand vague words into the regulatory terms a circular would use (e.g. "risky people" -> "high risk customers").
Keep any circular numbers, codes, amounts and dates exactly. Output only the query, nothing else.

Question: {q}
Query:"""


def chat(messages: list[dict], temperature: float = 0.0, model: str | None = None) -> str:
    """Any OpenAI-compatible endpoint; defaults to local Ollama. model=None means LLM_MODEL."""
    from openai import OpenAI

    client = OpenAI(base_url=os.environ.get("LLM_BASE_URL", "http://localhost:11434/v1"),
                    api_key=os.environ.get("LLM_API_KEY", "ollama"))
    r = client.chat.completions.create(model=model or os.environ.get("LLM_MODEL", "qwen2.5:3b"),
                                       messages=messages, temperature=temperature)
    return r.choices[0].message.content.strip()


def rewrite(question: str, llm=chat) -> str:
    q = llm([{"role": "user", "content": REWRITE.format(q=question)}]).strip().strip('"').splitlines()
    return q[0].strip() if q and q[0].strip() else question


def citation(h: dict) -> str:
    return f"[{h['ref']}, Para {h['para']}]"


def build_context(sources: list[dict]) -> str:
    """Sources newest-first, each labelled S1..Sn with date and a note if a newer circular cites it."""
    parts = []
    for n, h in enumerate(sources, 1):
        note = "".join(f"\n(Note: newer circular {c['ref']} dated {c['date']} refers to this one and may amend it.)"
                       for c in h.get("cited_by", []))
        parts.append(f"[S{n}] {h['ref']}, Para {h['para']} | dated {h['date']} | {h['title']}\n{h['text']}{note}")
    return "\n\n".join(parts)


def normalize_markers(raw: str) -> str:
    """Small models drift from '[S1]': accept '[Source S1]', '[S1, S3]', '[S1 and S2]', '[S1-S3]' -> '[S1][S3]'."""
    def fix(m):
        nums = []
        for a, b in re.findall(r"S\s*(\d+)(?:\s*[-–]\s*S?\s*(\d+))?", m.group(1)):
            nums += range(int(a), int(b or a) + 1)
        return "".join(f"[S{n}]" for n in nums)

    return re.sub(r"\[((?:\s*(?:Sources?\s*)?S\s*\d+(?:\s*[-–]\s*S?\s*\d+)?\s*(?:,|and|&)?)+)\]", fix, raw)


def render(raw: str, sources: list[dict]) -> tuple[str, list[int]]:
    """Replace [S2] markers with real citations; drop markers pointing at sources that weren't given."""
    used = []

    def sub(m):
        n = int(m.group(1))
        if 1 <= n <= len(sources):
            used.append(n)
            return citation(sources[n - 1])
        return ""

    text = re.sub(r"\[S(\d+)\]", sub, raw)
    return re.sub(r"[ \t]+([.,;])", r"\1", text).strip(), sorted(set(used))


def generate(question: str, passages: list[dict], llm=chat, model: str | None = None) -> dict:
    """LLM step: sources newest-first as [S1]..[Sn]; uncited or self-declared abstentions become ABSTAIN."""
    sources = sorted(passages, key=lambda h: h["date"], reverse=True)
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": f"Sources:\n\n{build_context(sources)}\n\nQuestion: {question}"}]
    raw = normalize_markers(llm(messages) if model is None else llm(messages, model=model))
    text, used = render(raw, sources)
    abstained = ABSTAIN.rstrip(".").lower() in raw.lower() or not used  # an uncited answer is not trusted
    return {"sources": sources, "raw": raw, "cited": used, "abstained": abstained, "answer": ABSTAIN if abstained else text}


def fused_search(queries: list[str], search) -> list[dict]:
    """Search each query, fuse the ranked lists with RRF; each hit keeps its best score from any query."""
    lists = [search(q) for q in queries]
    best: dict[int, dict] = {}
    for hits in lists:
        for h in hits:
            if h["idx"] not in best or h["score"] > best[h["idx"]]["score"]:
                best[h["idx"]] = h
    return [best[i] for i, _ in rrf([[h["idx"] for h in hits] for hits in lists])][:SEARCH_K]


def answer(question: str, retriever, cfg: Config = Config(), llm=chat, cache=None) -> dict:
    if cfg.semantic_cache and cache is not None:
        hit = cache.get(question)
        if hit:
            return hit

    out = {"question": question, "query": question, "route": None, "queries": [question], "hits": [],
           "sources": [], "cited": [], "raw": "", "abstained": True, "answer": ABSTAIN, "crag": None}

    def finish(result):
        if cfg.semantic_cache and cache is not None:
            cache.put(question, result)
        return result

    settings = {}
    if cfg.router:
        out["route"] = router.classify(question, llm)
        settings = router.ROUTES[out["route"]]
        if out["route"] == "out_of_scope":
            return finish(out)  # nothing in an RBI corpus can answer it; don't spend retrieval or the LLM
    top_k = settings.get("top_k", cfg.top_k)

    def search(q):
        return retriever.search(q, mode=cfg.mode, k=SEARCH_K)

    if settings.get("multi_query"):
        out["queries"] = router.sub_queries(question, llm)
        hits = fused_search(out["queries"], search)
    else:
        if cfg.rewrite or settings.get("rewrite"):
            out["query"] = out["queries"][0] = rewrite(question, llm)
        hits = search(out["query"])
    out["hits"] = hits

    # gate: if even the best re-ranked passage is barely relevant, abstain without asking the LLM
    if not hits or (cfg.mode == "rerank" and max(h["score"] for h in hits[:top_k]) < cfg.min_score):
        return finish(out)

    if cfg.crag:
        def retry(q):  # a comparison keeps its per-side queries; a retry adds to the fusion, never replaces it
            return fused_search(out["queries"] + [q], search) if settings.get("multi_query") else search(q)

        c = crag.correct(question, out["query"], hits, retry, llm, top_k)
        out.update(hits=c["hits"], crag={k: c[k] for k in ("queries", "relevant", "retries")})
        if not c["relevant"]:
            return finish(out)  # graded irrelevant after every retry: a deliberate abstention
        hits = c["hits"]

    out.update(generate(question, hits[:top_k], llm, settings.get("model")))
    return finish(out)


if __name__ == "__main__":
    from circulariq.retrieve import Retriever

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    r = answer(" ".join(args), Retriever(), Config(router="--router" in sys.argv, crag="--crag" in sys.argv))
    print("route:", r["route"], "| queries:", r["queries"])
    print(r["answer"])
