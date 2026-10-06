"""Query router: a cheap LLM call sorts each question into a route; each route sets its own retrieval and model.

simple        one fact from one circular       -> top 3 passages, small model
comparison    contrasts circulars / entities   -> one query per side, fused; top 8; full model
out_of_scope  not about RBI regulation         -> abstain immediately, no retrieval
unclear       vague or colloquial               -> LLM rewrite first, then the normal path
"""
import os
import re

SMALL_MODEL = os.environ.get("LLM_SMALL_MODEL", "qwen2.5:1.5b")

# per-route settings; None model = the default (full) model
ROUTES = {  # "cheap" routing, as specified: small model for simple questions, instant abstain off-topic
    "simple": {"top_k": 3, "model": SMALL_MODEL, "rewrite": False, "multi_query": False},
    "comparison": {"top_k": 8, "model": None, "rewrite": False, "multi_query": True},
    "unclear": {"top_k": 5, "model": None, "rewrite": True, "multi_query": False},
    "out_of_scope": {"abstain": True},
}
# "quality" routing: keep only the routes that change retrieval. In the eval the 1.5B model answered simple
# questions correctly but without [S#] citations (so they were discarded), and the classifier sent answerable
# questions to out_of_scope while missing in-domain unanswerables -- the re-ranker score gate decides scope better.
QUALITY_ROUTES = {"simple": {}, "comparison": ROUTES["comparison"], "unclear": ROUTES["unclear"], "out_of_scope": {}}

CLASSIFY = """Classify a question sent to an assistant that answers ONLY from Reserve Bank of India (RBI) circulars
(banking regulation, KYC, foreign exchange/FEMA, currency, payments, audit, lending, deposits, reporting).

Labels:
simple - asks one specific fact, rule, date, limit or code
comparison - asks to compare or contrast two or more things, entities, dates or circulars
out_of_scope - not about Indian financial regulation at all (e.g. weather, sports, coding, personal advice)
unclear - about regulation but vague, informal or missing the key terms

Examples:
"Within how many days must a bank report a red-flagged account on CRILC?" -> simple
"How do the ITSC meeting rules differ between commercial banks and NBFCs?" -> comparison
"Who won the cricket world cup?" -> out_of_scope
"my bank flagged some dodgy loan, how long do they get?" -> unclear

Question: {q}
Answer with one label only."""

SPLIT = """Split this comparison question into separate search queries, one per thing being compared.
Keep entity names, dates, codes and amounts exactly. Output one query per line, at most 3 lines, nothing else.

Question: {q}"""


def classify(question: str, llm) -> str:
    """Route label; anything unparseable falls back to 'simple' (the normal path, never a silent abstention)."""
    reply = llm([{"role": "user", "content": CLASSIFY.format(q=question)}], model=SMALL_MODEL).lower()
    for label in ("out_of_scope", "comparison", "unclear", "simple"):
        if label in reply.replace("-", "_").replace(" ", "_"):
            return label
    return "simple"


def sub_queries(question: str, llm) -> list[str]:
    """One query per side of a comparison, plus the original question so nothing is lost."""
    lines = llm([{"role": "user", "content": SPLIT.format(q=question)}]).splitlines()
    queries = [re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", l).strip().strip('"') for l in lines]
    return [question] + [q for q in queries if q][:3]
