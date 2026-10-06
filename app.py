"""CircularIQ UI.  streamlit run app.py"""
import streamlit as st

from circulariq.retrieve import Retriever

st.set_page_config(page_title="CircularIQ", page_icon="📑", layout="wide")


@st.cache_resource
def retriever():
    return Retriever()


st.title("CircularIQ")
st.caption("Cited answers from RBI circulars")

q = st.text_input("Ask a question about RBI circulars", key="question")
mode = st.radio("Retrieval", ["hybrid", "bm25", "dense"], horizontal=True, key="mode")

if q:
    hits = retriever().search(q, mode)[:10]
    st.subheader(f"Retrieved passages ({mode})")
    if not hits:
        st.info("No matching passages.")
    for i, h in enumerate(hits):
        with st.container(border=True, key=f"hit-{i}"):
            st.markdown(f"**[{h['ref']}, Para {h['para']}]({h['url']})** · {h['date']} · score `{h['score']:.4f}`")
            st.caption(h["title"])
            st.text(h["text"])
