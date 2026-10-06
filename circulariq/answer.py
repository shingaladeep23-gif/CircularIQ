"""Question -> (rewrite) -> hybrid retrieve -> re-rank -> LLM answer with citations, or abstain.

python -m circulariq.answer "What is the tear size limit for unfit notes?"
"""
import os
import re
import sys

ABSTAIN = "Not found in the provided circulars."
MIN_RERANK_SCORE = float(os.environ.get("CIRCULARIQ_MIN_SCORE", "0.05"))  # below this, don't even ask the LLM
TOP_K = 5

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


def chat(messages: list[dict], temperature: float = 0.0) -> str:
    """Any OpenAI-compatible endpoint; defaults to local Ollama."""
    from openai import OpenAI

    client = OpenAI(base_url=os.environ.get("LLM_BASE_URL", "http://localhost:11434/v1"),
                    api_key=os.environ.get("LLM_API_KEY", "ollama"))
    r = client.chat.completions.create(model=os.environ.get("LLM_MODEL", "qwen2.5:3b"),
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
    """Small models drift from '[S1]': accept '[Source S1]', '[S1, S3]', '[S1 and S2]' -> '[S1][S3]'."""
    def fix(m):
        return "".join(f"[S{n}]" for n in re.findall(r"S\s*(\d+)", m.group(1)))

    return re.sub(r"\[((?:\s*(?:Sources?\s*)?S\s*\d+\s*(?:,|and|&)?)+)\]", fix, raw)


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


def answer(question: str, retriever, llm=chat, use_rewrite: bool = True, mode: str = "rerank",
           min_score: float = MIN_RERANK_SCORE, hits: list[dict] | None = None, query: str | None = None) -> dict:
    """hits/query let the evaluator reuse retrieval it already ran; min_score=0 disables the gate."""
    if query is None:
        query = rewrite(question, llm) if use_rewrite else question
    hits = retriever.search(query, mode=mode, k=TOP_K) if hits is None else hits[:TOP_K]
    out = {"question": question, "query": query, "hits": hits, "sources": [], "cited": [], "raw": "", "abstained": True}
    # gate: if the best re-ranked passage is barely relevant, abstain without asking the LLM
    if not hits or (mode == "rerank" and hits[0]["score"] < min_score):
        out["answer"] = ABSTAIN
        return out
    sources = sorted(hits, key=lambda h: h["date"], reverse=True)  # newest first
    raw = normalize_markers(llm([{"role": "system", "content": SYSTEM},
                                 {"role": "user", "content": f"Sources:\n\n{build_context(sources)}\n\nQuestion: {question}"}]))
    text, used = render(raw, sources)
    abstained = ABSTAIN.rstrip(".").lower() in raw.lower() or not used  # an uncited answer is not trusted
    out.update(sources=sources, raw=raw, cited=used, abstained=abstained, answer=ABSTAIN if abstained else text)
    return out


if __name__ == "__main__":
    from circulariq.retrieve import Retriever

    r = answer(" ".join(sys.argv[1:]), Retriever())
    print("query:", r["query"])
    print(r["answer"])
