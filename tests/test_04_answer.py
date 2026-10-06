"""Step 3: re-ranking, prompting, citations, abstention, recency, query rewriting.

Unit tests use a scripted fake LLM so they are deterministic. The browser tests at the bottom
drive the real UI with the real local LLM (Ollama) and are skipped if it is not running.
"""
import urllib.request

import pytest
from playwright.sync_api import expect

from circulariq.answer import ABSTAIN, answer, build_context, render, rewrite


class FakeLLM:
    """Returns scripted replies in order and records every prompt it was sent."""

    def __init__(self, *replies):
        self.replies, self.calls = list(replies), []

    def __call__(self, messages, temperature=0.0):
        self.calls.append(messages)
        return self.replies.pop(0)


def test_reranker_puts_answering_paragraph_first(retriever):
    hits = retriever.search("How often must banks test note sorting machines for accuracy?", mode="rerank", k=5)
    assert (hits[0]["nid"], hits[0]["para"]) == (13723, "7")
    assert all(0 <= h["score"] <= 1 for h in hits)
    assert [h["score"] for h in hits] == sorted((h["score"] for h in hits), reverse=True)


def test_reranker_scores_irrelevant_question_low(retriever):
    hits = retriever.search("What is the capital gains tax rate on mutual funds?", mode="rerank", k=1)
    assert hits[0]["score"] < 0.05


def test_render_maps_markers_to_citations_and_drops_bogus_ones():
    src = [{"ref": "RBI/2026-27/279", "para": "2"}, {"ref": "RBI/DCM/2026-27/473", "para": "7"}]
    text, used = render("Machines are tested quarterly [S2]. Boards approve guidelines [S1][S9].", src)
    assert text == "Machines are tested quarterly [RBI/DCM/2026-27/473, Para 7]. Boards approve guidelines [RBI/2026-27/279, Para 2]."
    assert used == [1, 2]


def test_answer_cites_real_paragraph(retriever):
    llm = FakeLLM("note sorting machine testing frequency accuracy",
                  "Banks must test note sorting machines quarterly for accuracy and consistency [S1].")
    r = answer("how often are NSMs tested?", retriever, llm=llm)
    assert not r["abstained"]
    cited = r["sources"][r["cited"][0] - 1]
    assert (cited["nid"], cited["para"]) == (13723, "7")
    assert "[RBI/DCM/2026-27/473, Para 7]" in r["answer"]
    # the prompt carried the grounding rules and the numbered sources
    system, user = llm.calls[1]
    assert "ONLY the numbered sources" in system["content"] and ABSTAIN in system["content"]
    assert "[S1] RBI/DCM/2026-27/473, Para 7" in user["content"]


def test_llm_abstention_is_respected(retriever):
    r = answer("note sorting machines", retriever, llm=FakeLLM(ABSTAIN), use_rewrite=False)
    assert r["abstained"] and r["answer"] == ABSTAIN


def test_uncited_answer_is_treated_as_abstention(retriever):
    r = answer("note sorting machines", retriever, llm=FakeLLM("Machines are great."), use_rewrite=False)
    assert r["abstained"] and r["answer"] == ABSTAIN


def test_low_relevance_gate_skips_llm(retriever):
    llm = FakeLLM()  # any call would raise IndexError
    r = answer("What is the capital gains tax rate on mutual funds?", retriever, llm=llm, use_rewrite=False)
    assert r["abstained"] and llm.calls == []


def test_rewrite_uses_llm_and_falls_back():
    assert rewrite("kyc thing for risky ppl?", FakeLLM('"periodic KYC updation high risk customers"\n')) == \
        "periodic KYC updation high risk customers"
    assert rewrite("original question", FakeLLM("")) == "original question"


def test_context_is_newest_first_and_flags_amendments():
    old = {"ref": "RBI/2026-27/100", "para": "3", "date": "2026-05-01", "title": "Old", "text": "limit is 5",
           "cited_by": [{"ref": "RBI/2026-27/200", "date": "2026-08-01"}]}
    new = {"ref": "RBI/2026-27/200", "para": "2", "date": "2026-08-01", "title": "New", "text": "limit is 10", "cited_by": []}
    ctx = build_context(sorted([old, new], key=lambda h: h["date"], reverse=True))
    assert ctx.index("[S1] RBI/2026-27/200") < ctx.index("[S2] RBI/2026-27/100")
    assert "newer circular RBI/2026-27/200 dated 2026-08-01 refers to this one and may amend it" in ctx


def test_cited_by_map_links_amendment_to_original(fixture_chunks, tmp_path):
    # fixture 13578 (Jul 16) cites 13570, which is not in the fixture corpus -> no link;
    # add a synthetic newer chunk citing 13578 and the link must appear
    from circulariq.retrieve import Retriever, build

    newer = {**fixture_chunks[0], "chunk_id": "99999-0", "nid": 99999, "ref": "RBI/2026-27/999",
             "date": "2026-12-01", "references": [13578]}
    build(fixture_chunks + [newer], tmp_path)
    r = Retriever(tmp_path)
    assert [c["ref"] for c in r.cited_by[13578]] == ["RBI/2026-27/999"]
    assert 13570 not in r.cited_by


def ollama_up():
    try:
        urllib.request.urlopen("http://localhost:11434/api/version", timeout=2)
        return True
    except OSError:
        return False


needs_llm = pytest.mark.skipif(not ollama_up(), reason="local Ollama not running")


def ask(page, app_url, question):
    page.goto(app_url)
    page.get_by_label("Ask a question about RBI circulars").fill(question)
    page.get_by_label("Ask a question about RBI circulars").press("Enter")


@needs_llm
def test_ui_answers_with_clickable_citation(page, app_url):
    """Playwright + real LLM: a grounded question gets an answer citing the right circular."""
    ask(page, app_url, "How often must banks test their note sorting machines?")
    ans = page.locator(".st-key-answer")
    expect(ans).to_contain_text("RBI/DCM/2026-27/473", timeout=180_000)
    expect(ans).to_contain_text("quarter")
    expect(ans.get_by_role("link", name="RBI/DCM/2026-27/473").first).to_have_attribute("href", "https://rbi.org.in/Scripts/NotificationUser.aspx?Id=13723&Mode=0")


@needs_llm
def test_ui_abstains_when_corpus_has_no_answer(page, app_url):
    ask(page, app_url, "What is the capital gains tax rate on equity mutual funds?")
    expect(page.locator(".st-key-answer")).to_contain_text(ABSTAIN, timeout=180_000)
