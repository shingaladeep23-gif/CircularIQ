"""Corrective RAG: grade whether the re-ranked passages contain the answer; if not, search again with a
different query (at most MAX_RETRIES times), then give up so the pipeline abstains instead of guessing."""

MAX_RETRIES = 2

GRADE = """Passages:
{passages}

Question: {q}

Do these passages contain the information needed to answer the question? Answer only YES or NO."""

RETRY = """A search of RBI circulars for the question below did not find the answer.
Previous search queries (do not repeat them):
{tried}

Write ONE different search query that uses the specific regulatory terms a circular would contain.
Keep entity names, codes, amounts and dates from the question. Output only the query.

Question: {q}"""


def grade(question: str, passages: list[dict], llm) -> bool:
    text = "\n\n".join(f"[{i}] {p['title']} | {p['section']}\n{p['text']}" for i, p in enumerate(passages, 1))
    return llm([{"role": "user", "content": GRADE.format(passages=text, q=question)}]).strip().upper().startswith("YES")


def correct(question: str, query: str, hits: list[dict], search, llm, top_k: int) -> dict:
    """search(query) -> hits. Returns the hits to answer from, every query tried, and whether any round passed."""
    tried = [query]
    for attempt in range(MAX_RETRIES + 1):
        if hits and grade(question, hits[:top_k], llm):
            return {"hits": hits, "queries": tried, "relevant": True, "retries": attempt}
        if attempt == MAX_RETRIES:
            break
        new = llm([{"role": "user", "content": RETRY.format(tried="\n".join(tried), q=question)}]).strip().strip('"')
        new = new.splitlines()[0].strip() if new else ""
        if not new or new in tried:
            break  # the model has no new idea; more rounds would only repeat the failure
        tried.append(new)
        hits = search(new)
    return {"hits": hits, "queries": tried, "relevant": False, "retries": len(tried) - 1}
