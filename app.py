"""CircularIQ UI.  streamlit run app.py"""
import streamlit as st

from circulariq.answer import ABSTAIN, TOP_K, answer, citation
from circulariq.retrieve import Retriever

st.set_page_config(page_title="CircularIQ", page_icon="📑", layout="wide")


@st.cache_resource
def retriever():
    return Retriever()


def linked(text: str, sources: list[dict]) -> str:
    """Turn each '[RBI/..., Para X]' citation in the answer into a link to the circular."""
    for h in sources:
        text = text.replace(citation(h), f"[{h['ref']}, Para {h['para']}]({h['url']})")
    return text


st.title("CircularIQ")
st.caption("Cited answers from RBI circulars. Answers use only the retrieved passages and say so when they can't answer.")

q = st.text_input("Ask a question about RBI circulars", key="question")
c1, c2 = st.columns([3, 1])
mode = c1.radio("Retrieval", ["rerank", "hybrid", "bm25", "dense"], horizontal=True, key="mode",
                help="rerank = hybrid (BM25 + dense, RRF) top 50, re-scored by a cross-encoder")
use_rewrite = c2.toggle("Rewrite query", value=True, key="rewrite")

if q:
    with st.spinner("Searching circulars and drafting an answer..."):
        try:
            r = answer(q, retriever(), use_rewrite=use_rewrite, mode=mode)
        except Exception as e:  # LLM unreachable: still show what retrieval found
            st.error(f"LLM unavailable ({type(e).__name__}); showing retrieved passages only.")
            r = {"abstained": True, "answer": ABSTAIN, "query": q, "sources": [], "hits": retriever().search(q, mode, k=TOP_K)}

    with st.container(border=True, key="answer"):
        st.markdown("#### Answer")
        if r["abstained"]:
            st.warning(r["answer"])
        else:
            st.markdown(linked(r["answer"], r["sources"]))
    if use_rewrite:
        st.caption(f"Search query: {r['query']}")

    st.subheader(f"Retrieved passages ({mode})")
    if not r["hits"]:
        st.info("No matching passages.")
    for i, h in enumerate(r["hits"]):
        with st.container(border=True, key=f"hit-{i}"):
            st.markdown(f"**[{h['ref']}, Para {h['para']}]({h['url']})** · {h['date']} · score `{h['score']:.4f}`")
            st.caption(h["title"])
            for c in h.get("cited_by", []):
                st.warning(f"May be amended by newer circular [{c['ref']}]({c['url']}) dated {c['date']}.")
            st.text(h["text"])
