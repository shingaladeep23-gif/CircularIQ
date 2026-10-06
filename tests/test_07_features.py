"""Phase 2 features, each behind a Config flag: query router, corrective RAG, semantic cache."""
import json

import numpy as np
import pytest
from playwright.sync_api import expect

from circulariq import crag, router
from circulariq.answer import ABSTAIN, SYSTEM, Config, answer
from circulariq.cache import SemanticCache, changed_circulars, signature
from conftest import FakeLLM, PromptLLM
from test_04_answer import ask, needs_llm

NSM_Q = "How often must banks test note sorting machines for accuracy?"
NSM_ANSWER = "Banks must test note sorting machines quarterly [S1]."


# --- default path -------------------------------------------------------------------------------

def test_all_features_off_is_the_evaluated_path(retriever):
    """Default Config = exactly one LLM call: the answer prompt the eval measured."""
    llm = FakeLLM(NSM_ANSWER)
    r = answer(NSM_Q, retriever, Config(), llm)
    assert len(llm.calls) == 1 and llm.calls[0][0]["content"] == SYSTEM and llm.models == [None]
    assert r["route"] is None and r["crag"] is None and len(r["sources"]) == 5 and len(r["hits"]) == 10


# --- query router -------------------------------------------------------------------------------

def test_classify_parses_labels_and_uses_small_model():
    for reply, label in [("Comparison", "comparison"), ("out-of-scope", "out_of_scope"), ("unclear.", "unclear"),
                         ("simple", "simple"), ("I am not sure", "simple")]:
        llm = FakeLLM(reply)
        assert router.classify("q", llm) == label, reply
        assert llm.models == [router.SMALL_MODEL]


def test_sub_queries_keep_original_and_strip_list_markers():
    qs = router.sub_queries("compare X and Y", FakeLLM("1. ITSC meetings commercial banks\n- ITSC meetings NBFC\n\n"))
    assert qs == ["compare X and Y", "ITSC meetings commercial banks", "ITSC meetings NBFC"]


def test_out_of_scope_route_abstains_without_retrieval_or_generation(retriever):
    llm = PromptLLM([("Classify a question", "out_of_scope")])
    r = answer("Who won the cricket world cup?", retriever, Config(router=True), llm)
    assert r["route"] == "out_of_scope" and r["abstained"] and r["answer"] == ABSTAIN
    assert r["hits"] == [] and len(llm.calls) == 1


def test_simple_route_uses_top3_and_small_model(retriever):
    llm = PromptLLM([("Classify a question", "simple"), ("Sources:", NSM_ANSWER)])
    r = answer(NSM_Q, retriever, Config(router=True), llm)
    assert r["route"] == "simple" and len(r["sources"]) == 3 and not r["abstained"]
    assert llm.models[-1] == router.SMALL_MODEL  # generation call


def test_comparison_route_fuses_one_search_per_side(retriever):
    llm = PromptLLM([("Classify a question", "comparison"),
                     ("Split this comparison", "note sorting machine testing\nForm A2 internal guidelines Board"),
                     ("Sources:", "Quarterly testing [S1]; Board committee approval [S2].")])
    r = answer("Compare NSM testing frequency with Form A2 guideline approval", retriever, Config(router=True), llm)
    assert r["route"] == "comparison" and len(r["queries"]) == 3
    assert {13723, 13724} <= {h["nid"] for h in r["sources"]}  # both sides made it into the context
    assert len(r["sources"]) == 8 and llm.models[-1] is None  # full model for comparisons


def test_unclear_route_rewrites_first(retriever):
    llm = PromptLLM([("Classify a question", "unclear"), ("Rewrite the user's question", "note sorting machine testing frequency"),
                     ("Sources:", NSM_ANSWER)])
    r = answer("those cash machine things, how often checked?", retriever, Config(router=True), llm)
    assert r["route"] == "unclear" and r["query"] == "note sorting machine testing frequency"
    assert r["hits"][0]["nid"] == 13723


# --- corrective RAG ------------------------------------------------------------------------------

def hit(nid):
    return {"nid": nid, "title": "t", "section": "s", "text": f"text {nid}"}


def test_crag_accepts_relevant_first_round():
    out = crag.correct("q", "q", [hit(1)], lambda q: pytest.fail("no retry expected"), FakeLLM("YES"), 5)
    assert out["relevant"] and out["retries"] == 0


def test_crag_retries_with_new_query_then_succeeds():
    searched = []
    out = crag.correct("q", "q0", [hit(1)], lambda q: searched.append(q) or [hit(2)], FakeLLM("NO", "better query", "YES"), 5)
    assert out == {"hits": [hit(2)], "queries": ["q0", "better query"], "relevant": True, "retries": 1}
    assert searched == ["better query"]


def test_crag_gives_up_after_max_retries():
    llm = FakeLLM("NO", "query 2", "NO", "query 3", "NO")
    out = crag.correct("q", "q1", [hit(1)], lambda q: [hit(9)], llm, 5)
    assert not out["relevant"] and out["retries"] == crag.MAX_RETRIES == 2 and len(llm.calls) == 5


def test_crag_stops_when_model_repeats_a_query():
    out = crag.correct("q", "same", [hit(1)], lambda q: pytest.fail("no search expected"), FakeLLM("NO", "same"), 5)
    assert not out["relevant"] and out["retries"] == 0


def test_pipeline_abstains_when_crag_finds_nothing(retriever):
    llm = PromptLLM([("contain the information needed", "NO"), ("did not find the answer", "another query")],
                    default="unused")
    r = answer(NSM_Q, retriever, Config(crag=True), llm)
    assert r["abstained"] and not r["crag"]["relevant"] and r["answer"] == ABSTAIN
    assert not any(m[0]["content"] == SYSTEM for m in llm.calls)  # never asked to answer


def test_pipeline_answers_when_crag_passes(retriever):
    llm = PromptLLM([("contain the information needed", "YES"), ("Sources:", NSM_ANSWER)])
    r = answer(NSM_Q, retriever, Config(crag=True), llm)
    assert not r["abstained"] and r["crag"] == {"queries": [NSM_Q], "relevant": True, "retries": 0}


# --- semantic cache ------------------------------------------------------------------------------

def test_signature_separates_entities_codes_and_instruments():
    base = "Until when are fresh FCNR(B) deposits of commercial banks exempt from CRR?"
    assert signature(base) == signature("Till when are fresh FCNR(B) deposits of commercial banks exempt from CRR?")
    assert signature(base) != signature(base.replace("commercial banks", "small finance banks"))
    assert signature(base) != signature(base.replace("FCNR(B)", "NRE"))
    assert signature("What is return R343?") != signature("What is return R006?")


def fake_embed(table):
    return lambda texts: [np.asarray(table[t], dtype="float32") for t in texts]


def test_cache_hit_needs_similarity_and_same_signature(tmp_path):
    a, a2 = "What is the CRR exemption for commercial banks?", "What's the CRR exemption for commercial banks?"
    swapped, far = a.replace("commercial", "small finance"), "Who is the lead bank for Nubra?"
    vec = {a: [1, 0], a2: [0.99, 0.141], swapped: [1, 0], far: [0, 1]}
    c = SemanticCache(tmp_path / "c.jsonl", embed=fake_embed(vec))
    c.put(a, {"answer": "Aug 31 [x]", "abstained": False, "sources": [{"nid": 13680}], "hits": []})
    assert c.get(a2)["answer"] == "Aug 31 [x]" and c.get(a2)["cache"]["hit"]
    assert c.get(swapped) is None  # cosine 1.0, but different entity: must not reuse
    assert c.get(far) is None
    assert SemanticCache(tmp_path / "c.jsonl", embed=fake_embed(vec)).get(a2) is not None  # persisted


def test_cache_invalidation(tmp_path):
    vec = {"q1": [1, 0], "q2": [0, 1], "q3": [0.7, 0.7]}
    c = SemanticCache(tmp_path / "c.jsonl", embed=fake_embed(vec))
    c.put("q1", {"answer": "a", "abstained": False, "sources": [{"nid": 1}], "hits": []})
    c.put("q2", {"answer": "b", "abstained": False, "sources": [{"nid": 2}], "hits": []})
    c.put("q3", {"answer": ABSTAIN, "abstained": True, "sources": [], "hits": []})
    assert c.invalidate({1}) == 1 and [e["question"] for e in c.entries] == ["q2", "q3"]
    assert c.invalidate(set(), new_circulars=True) == 1  # new circulars may answer what we abstained on
    assert [e["question"] for e in SemanticCache(tmp_path / "c.jsonl").entries] == ["q2"]


def test_changed_circulars():
    old = [{"nid": 1, "text": "a"}, {"nid": 2, "text": "b"}, {"nid": 3, "text": "c"}]
    new = [{"nid": 1, "text": "a"}, {"nid": 2, "text": "B!"}, {"nid": 4, "text": "d"}]
    assert changed_circulars(old, new) == ({2, 3}, True)


def test_index_rebuild_invalidates_cache_for_changed_circular(fixture_chunks, tmp_path):
    from circulariq.retrieve import build

    build(fixture_chunks, tmp_path)
    c = SemanticCache(tmp_path / "c.jsonl", embed=fake_embed({"q": [1, 0], "r": [0, 1]}))
    c.put("q", {"answer": "x", "abstained": False, "sources": [{"nid": 13724}], "hits": []})
    c.put("r", {"answer": "y", "abstained": False, "sources": [{"nid": 13723}], "hits": []})
    edited = [{**ch, "text": ch["text"] + " (amended)"} if ch["nid"] == 13724 else ch for ch in fixture_chunks]
    build(edited, tmp_path, cache_path=tmp_path / "c.jsonl")
    assert [e["question"] for e in SemanticCache(tmp_path / "c.jsonl").entries] == ["r"]


def test_pipeline_cache_skips_llm_on_repeat(retriever, tmp_path):
    cache = SemanticCache(tmp_path / "c.jsonl")
    first = answer(NSM_Q, retriever, Config(semantic_cache=True), FakeLLM(NSM_ANSWER), cache)
    again = answer(NSM_Q + " ", retriever, Config(semantic_cache=True), FakeLLM(), cache)  # FakeLLM() would raise
    assert again["answer"] == first["answer"] and again["cache"]["hit"]


# --- evaluation plumbing --------------------------------------------------------------------------

def test_comparison_rank_needs_every_evidence_item():
    from circulariq.evaluate import evidence_rank

    q = {"evidence": [{"nid": 1, "quote": "a"}, {"nid": 2, "quote": "b"}], "need_all": True}
    hits = [{"nid": 1, "text": "a"}, {"nid": 3, "text": "x"}, {"nid": 2, "text": "b"}]
    assert evidence_rank(hits, q) == 3 and evidence_rank(hits[:2], q) is None
    assert evidence_rank(hits, {**q, "need_all": False}) == 1


def test_cached_llm_keeps_old_keys_and_separates_models(tmp_path):
    import hashlib

    from circulariq.evaluate import CachedLLM

    msgs = [{"role": "user", "content": "hi"}]
    seen = []
    c = CachedLLM(tmp_path / "c.jsonl", lambda m, model=None: seen.append(model) or f"reply-{model}")
    assert c(msgs) == "reply-None" and c(msgs, model="small") == "reply-small" and seen == [None, "small"]
    keys = [json.loads(l)["k"] for l in (tmp_path / "c.jsonl").open()]
    assert keys[0] == hashlib.sha1(json.dumps(msgs, ensure_ascii=False).encode()).hexdigest()  # pre-router format


# --- UI (Playwright + real local LLM) ---------------------------------------------------------------

def toggle_and_ask(page, app_url, label, question):
    page.goto(app_url)
    page.get_by_text(label, exact=True).click()
    page.get_by_label("Ask a question about RBI circulars").fill(question)
    page.get_by_label("Ask a question about RBI circulars").press("Enter")


@needs_llm
def test_ui_router_sends_off_topic_question_straight_to_abstention(page, app_url):
    toggle_and_ask(page, app_url, "Route by question type", "Who won the football world cup in 2022?")
    expect(page.locator(".st-key-answer")).to_contain_text(ABSTAIN, timeout=180_000)
    expect(page.get_by_text("route: out_of_scope")).to_be_visible()


@needs_llm
def test_ui_corrective_rag_reports_its_grade(page, app_url):
    toggle_and_ask(page, app_url, "Corrective RAG", NSM_Q)
    expect(page.get_by_text("corrective RAG:", exact=False)).to_be_visible(timeout=180_000)


@needs_llm
def test_ui_semantic_cache_serves_repeat_question(page, app_url):
    toggle_and_ask(page, app_url, "Semantic cache", "How often must note sorting machines be tested by banks?")
    expect(page.locator(".st-key-answer")).to_contain_text("RBI/DCM/2026-27/473", timeout=180_000)
    toggle_and_ask(page, app_url, "Semantic cache", "How often must note sorting machines be tested by banks?")
    expect(page.get_by_text("semantic cache hit", exact=False)).to_be_visible(timeout=60_000)


def test_crag_retry_on_comparison_keeps_both_sides(retriever):
    llm = PromptLLM([("Classify a question", "comparison"),
                     ("Split this comparison", "note sorting machine testing\nForm A2 internal guidelines Board"),
                     ("contain the information needed", "NO"), ("did not find the answer", "remittance approval committee")],
                    default="NO")
    r = answer("Compare NSM testing frequency with Form A2 guideline approval", retriever, Config(router=True, crag=True), llm)
    assert {13723, 13724} <= {h["nid"] for h in r["hits"][:8]}  # retries extended the fusion; both sides kept
