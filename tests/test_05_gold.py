"""Step 4: the gold Q&A set and the relevance rule used to score retrieval."""
import json
from pathlib import Path

import pytest
from playwright.sync_api import expect

from circulariq.evaluate import is_relevant, load_gold, validate_gold

GOLD = load_gold()
CHUNKS = Path("data/chunks.jsonl")


def test_gold_shape_matches_brief():
    ids = [q["id"] for q in GOLD]
    assert len(ids) == len(set(ids))
    answerable = [q for q in GOLD if q["type"] != "unanswerable"]
    assert len(GOLD) >= 60 and len(answerable) >= 60
    assert sum(q["type"] == "unanswerable" for q in GOLD) >= 15
    assert {q["type"] for q in GOLD} == {"fact", "paraphrase", "exact-id", "table", "recency", "colloquial", "unanswerable"}
    for q in GOLD:
        assert q["question"].strip() and q["answer"].strip()
        assert (q["type"] == "unanswerable") == (not q["evidence"])
        assert (q["type"] == "recency") == bool(q["stale"])  # every recency question records what it supersedes


def test_relevance_needs_same_circular_and_quote():
    ev = [{"nid": 13723, "quote": "tested for accuracy and consistency on a quarterly basis"}]
    hit = {"nid": 13723, "text": "Banks shall ensure that the Note Sorting machines are tested for accuracy and\n consistency on a  quarterly basis"}
    assert is_relevant(hit, ev)  # whitespace and line breaks don't matter
    assert not is_relevant({**hit, "nid": 13724}, ev)  # same words in another circular don't count
    assert not is_relevant({"nid": 13723, "text": "machines are tested yearly"}, ev)


def test_validator_catches_bad_quote():
    bad = [{"id": "x", "type": "fact", "question": "?", "answer": "!", "stale": [],
            "evidence": [{"nid": 13723, "quote": "this sentence is not in the circular"}]}]
    chunks = [{"nid": 13723, "text": "something else"}]
    assert validate_gold(bad, chunks) == ["x: quote not found in 13723: 'this sentence is not in the circular'"]


@pytest.mark.skipif(not CHUNKS.exists(), reason="full corpus not built (run scrape + chunk)")
def test_every_gold_quote_exists_in_corpus():
    chunks = [json.loads(l) for l in CHUNKS.open(encoding="utf-8")]
    assert validate_gold(GOLD, chunks) == []


def test_unanswerable_questions_score_low_on_fixture_index(retriever):
    # sanity: the out-of-corpus questions get low re-ranker scores even on the small fixture index
    for q in [g for g in GOLD if g["type"] == "unanswerable"][:5]:
        assert retriever.search(q["question"], mode="rerank", k=1)[0]["score"] < 0.5, q["question"]


def test_ui_top_passage_contains_gold_evidence(page, app_url):
    """Playwright: ask a real gold question in the browser; the top passage must contain its evidence."""
    q = next(g for g in GOLD if g["evidence"] and g["evidence"][0]["nid"] == 13724)  # circular in the fixture index
    page.goto(app_url)
    box = page.get_by_label("Ask a question about RBI circulars")
    box.fill(q["question"])
    box.press("Enter")
    top = page.locator(".st-key-hit-0")
    expect(top).to_contain_text("RBI/2026-27/279", timeout=120_000)
    expect(top).to_contain_text(q["evidence"][0]["quote"])
