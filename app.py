"""CircularIQ UI.  streamlit run app.py"""
from pathlib import Path

import streamlit as st

from circulariq.answer import ABSTAIN, SEARCH_K, Config, answer, citation
from circulariq.cache import SemanticCache
from circulariq.retrieve import Retriever

RESULTS = Path(__file__).parent / "data" / "eval" / "results.md"

st.set_page_config(page_title="CircularIQ", page_icon="📑", layout="wide")


@st.cache_resource
def retriever():
    return Retriever()


@st.cache_resource
def semantic_cache():
    return SemanticCache()


def linked(text: str, sources: list[dict]) -> str:
    """Turn each '[RBI/..., Para X]' citation in the answer into a link to the circular."""
    for h in sources:
        text = text.replace(citation(h), f"[{h['ref']}, Para {h['para']}]({h['url']})")
    return text


st.title("CircularIQ")
st.caption("Cited answers from RBI circulars. Answers use only the retrieved passages and say so when they can't answer.")
ask, evaluation = st.tabs(["Ask", "Evaluation"])

EXAMPLES = [
    "How long does a commercial bank have to decide whether a red-flagged account is a fraud?",
    "Till what date are fresh FCNR(B) deposits mobilised by commercial banks exempt from CRR and SLR?",
    "How often must banks test their note sorting machines?",
    "What is the current policy repo rate?",  # not in the corpus: shows abstention
]


def use_example(text: str):
    st.session_state["question"] = text


with ask:
    st.caption("Try an example:")
    for col, ex in zip(st.columns(len(EXAMPLES)), EXAMPLES):
        col.button(ex, on_click=use_example, args=(ex,), width="stretch")
    q = st.text_input("Ask a question about RBI circulars", key="question")
    c1, c2, c3 = st.columns([2, 1, 1])
    mode = c1.radio("Retrieval", ["rerank", "hybrid", "bm25", "dense"], horizontal=True, key="mode",
                    help="rerank = hybrid (BM25 + dense, RRF) top 50, re-scored by a cross-encoder")
    use_rewrite = c2.toggle("Rewrite query", value=False, key="rewrite",
                            help="LLM rewrites the question before search. Off by default: it lowered Recall@5 in the eval.")
    use_router = c2.toggle("Route by question type", value=False, key="router",
                           help="Small model sorts the question: simple / comparison / out of scope / unclear. "
                                "Off by default: it lowered correctness in the eval.")
    use_crag = c3.toggle("Corrective RAG", value=False, key="crag",
                         help="Grade the passages; if they don't answer, search again (up to 2 times), else abstain. "
                              "Off by default: it lowered correctness in the eval.")
    use_cache = c3.toggle("Semantic cache", value=True, key="semcache",
                          help="Reuse the answer to a near-identical earlier question asked with the same settings "
                               "(entities, codes and dates must match). 0 false hits in the eval; ~225x faster.")
    cfg = Config(mode=mode, rewrite=use_rewrite, router=use_router, crag=use_crag, semantic_cache=use_cache)

    if q:
        with st.spinner("Searching circulars and drafting an answer..."):
            try:
                r = answer(q, retriever(), cfg, cache=semantic_cache())
            except Exception as e:  # LLM unreachable: still show what retrieval found
                st.error(f"LLM unavailable ({type(e).__name__}); showing retrieved passages only.")
                r = {"abstained": True, "answer": ABSTAIN, "query": q, "sources": [],
                     "hits": retriever().search(q, mode, k=SEARCH_K)}

        with st.container(border=True, key="answer"):
            st.markdown("#### Answer")
            if r["abstained"]:
                st.warning(r["answer"])
            else:
                st.markdown(linked(r["answer"], r["sources"]))
        trace = []
        if r.get("cache"):
            trace.append(f"semantic cache hit ({r['cache']['similarity']:.3f}) for: {r['cache']['matched']}")
        if r.get("route"):
            trace.append(f"route: {r['route']}")
        if len(r.get("queries", [])) > 1 or r.get("query", q) != q:
            trace.append("search queries: " + " | ".join(r.get("queries") or [r["query"]]))
        if r.get("crag"):
            c = r["crag"]
            trace.append(f"corrective RAG: {'relevant' if c['relevant'] else 'not relevant'} after {c['retries']} "
                         f"retr{'y' if c['retries'] == 1 else 'ies'}" + (f" ({' | '.join(c['queries'][1:])})" if c["retries"] else ""))
        if trace:
            st.caption(" · ".join(trace), help="What the pipeline did for this question")

        st.subheader(f"Retrieved passages ({mode})")
        if not r["hits"]:
            st.info("No matching passages.")
        cited_ids = set() if r["abstained"] else {r["sources"][n - 1]["chunk_id"] for n in r.get("cited", [])}
        for i, h in enumerate(r["hits"]):
            with st.container(border=True, key=f"hit-{i}"):
                badge = " · :green-badge[cited in answer]" if h["chunk_id"] in cited_ids else ""
                st.markdown(f"**[{h['ref']}, Para {h['para']}]({h['url']})** · {h['date']} · score `{h['score']:.4f}`{badge}")
                st.caption(h["title"])
                for c in h.get("cited_by", []):
                    st.warning(f"May be amended by newer circular [{c['ref']}]({c['url']}) dated {c['date']}.")
                st.text(h["text"])

with evaluation:
    with st.container(key="results"):
        if RESULTS.exists():
            st.markdown(RESULTS.read_text(encoding="utf-8"))
        else:
            st.info("No evaluation results yet. Run: python -m circulariq.evaluate")
