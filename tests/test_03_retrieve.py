"""Step 2: BM25, dense, RRF fusion, and the search page."""
from playwright.sync_api import expect

from circulariq.retrieve import rrf, tokenize


def test_rrf_matches_formula():
    fused = dict(rrf([["a", "b", "c"], ["b", "c", "d"]], k=60))
    assert fused["b"] == 1 / 62 + 1 / 61  # rank 2 in list 1, rank 1 in list 2
    assert fused["a"] == 1 / 61
    assert fused["d"] == 1 / 63
    assert [d for d, _ in rrf([["a", "b", "c"], ["b", "c", "d"]])][:2] == ["b", "c"]


def test_rrf_uses_ranks_not_raw_scores():
    # a document ranked first by one judge and absent from the other still loses to one ranked 2nd by both
    order = [d for d, _ in rrf([["x", "y"], ["z", "y"]])]
    assert order[0] == "y"


def test_tokenizer_keeps_codes_whole_and_split():
    toks = tokenize("Circular DOR.AML.REC.233/14.06.001/2026-27 on KYC")
    assert "dor.aml.rec.233" in toks and "aml" in toks and "2026-27" in toks and "kyc" in toks


def test_bm25_finds_exact_identifier(retriever):
    hits = retriever.search("RBI/2026-27/200", mode="bm25")
    assert hits[0]["nid"] == 13578


def test_dense_finds_paraphrase(retriever):
    # no keyword overlap with "tested for accuracy and consistency on a quarterly basis"
    hits = retriever.search("how frequently must cash sorting equipment be checked for precision", mode="dense", k=3)
    assert any(h["nid"] == 13723 and h["para"] == "7" for h in hits)


def test_hybrid_contains_both_signals(retriever):
    q = "Form A2 outward remittance internal guidelines approved by the Board"
    top_bm25 = retriever.search(q, mode="bm25")[0]["idx"]
    top_dense = retriever.search(q, mode="dense")[0]["idx"]
    hybrid = [h["idx"] for h in retriever.search(q, mode="hybrid", k=5)]
    assert top_bm25 in hybrid and top_dense in hybrid
    assert retriever.search(q, mode="hybrid")[0]["nid"] == 13724


def test_scores_sorted_and_k_respected(retriever):
    for mode in ["bm25", "dense", "hybrid"]:
        hits = retriever.search("note sorting machine", mode=mode, k=5)
        assert 0 < len(hits) <= 5
        assert [h["score"] for h in hits] == sorted((h["score"] for h in hits), reverse=True)


def search(page, app_url, question, mode=None):
    page.goto(app_url)
    if mode:
        page.get_by_text(mode, exact=True).click()
    box = page.get_by_label("Ask a question about RBI circulars")
    box.fill(question)
    box.press("Enter")


def test_search_page_shows_cited_passages(page, app_url):
    """Playwright: type a question, see re-ranked passages with citation links and scores."""
    search(page, app_url, "What are the tear size limits for sorting banknotes as unfit?")
    first = page.locator(".st-key-hit-0")
    expect(first).to_contain_text("RBI/DCM/2026-27/473", timeout=120_000)
    expect(first.get_by_role("link").first).to_have_attribute("href", "https://rbi.org.in/Scripts/NotificationUser.aspx?Id=13723&Mode=0")
    expect(page.get_by_text("Retrieved passages (rerank)")).to_be_visible()


def test_search_page_mode_switch(page, app_url):
    search(page, app_url, "RBI/2026-27/200", mode="bm25")
    expect(page.get_by_text("Retrieved passages (bm25)")).to_be_visible(timeout=120_000)
    expect(page.locator(".st-key-hit-0")).to_contain_text("RBI/2026-27/200")


def test_example_button_fills_question_and_searches(page, app_url):
    """Playwright: clicking an example question fills the box and runs retrieval."""
    page.goto(app_url)
    page.get_by_role("button", name="How often must banks test their note sorting machines?").click()
    expect(page.get_by_label("Ask a question about RBI circulars")).to_have_value(
        "How often must banks test their note sorting machines?", timeout=30_000)
    expect(page.locator(".st-key-hit-0")).to_contain_text("RBI/DCM/2026-27/473", timeout=120_000)
