"""Step 5: evaluation metrics, LLM judging, caching, and abstention accounting."""
from circulariq.evaluate import (CachedLLM, abstained, faithfulness, first_relevant_rank, mrr_at, recall_at,
                                 sentences, summarize, threshold_sweep, to_markdown)

EV = [{"nid": 1, "quote": "quarterly"}]


def hit(nid, text):
    return {"nid": nid, "text": text, "ref": f"R{nid}", "para": "1"}


def test_rank_recall_mrr_by_hand():
    hits = [hit(2, "quarterly"), hit(1, "annually"), hit(1, "tested quarterly")]
    assert first_relevant_rank(hits, EV) == 3  # only same-circular + quote counts
    ranks = [1, 2, None, 6]
    assert recall_at(ranks, 5) == 0.5
    assert mrr_at(ranks, 10) == (1 + 1 / 2 + 1 / 6) / 4
    assert mrr_at(ranks, 5) == (1 + 1 / 2) / 4  # rank 6 falls outside @5


def test_sentence_split_keeps_citations_with_sentence():
    assert sentences("Banks test quarterly [S1]. Boards approve [S2][S3]. Done.") == \
        ["Banks test quarterly [S1].", "Boards approve [S2][S3].", "Done."]


def test_faithfulness_judges_each_claim_against_its_cited_source():
    seen = []

    def judge(messages, temperature=0.0):
        seen.append(messages[0]["content"])
        return "YES" if "8 per cent" in messages[0]["content"].split("Claim:")[1] else "NO"

    sources = [hit(1, "compensation at 8 per cent per annum"), hit(2, "unrelated text")]
    score, verdicts = faithfulness("Compensation is 8 per cent [S1]. It is paid weekly [S2].", sources, judge)
    assert score == 0.5 and [v["supported"] for v in verdicts] == [True, False]
    assert "compensation at 8 per cent" in seen[0] and "unrelated text" not in seen[0]  # only the cited source
    assert "unrelated text" in seen[1]


def test_cached_llm_calls_once_and_persists(tmp_path):
    calls = []

    def llm(messages, temperature=0.0):
        calls.append(1)
        return "YES"

    c = CachedLLM(tmp_path / "cache.jsonl", llm)
    msg = [{"role": "user", "content": "q"}]
    assert c(msg) == c(msg) == "YES" and len(calls) == 1
    assert CachedLLM(tmp_path / "cache.jsonl", llm)(msg) == "YES" and len(calls) == 1  # reloaded from disk


def rows():
    return [
        {"type": "fact", "rank": 1, "top_score": 0.9, "llm_abstained": False, "faithfulness": 1.0, "correct": True},
        {"type": "fact", "rank": 7, "top_score": 0.03, "llm_abstained": False, "faithfulness": 0.5, "correct": False},
        {"type": "fact", "rank": None, "top_score": 0.2, "llm_abstained": True},
        {"type": "unanswerable", "rank": None, "top_score": 0.01, "llm_abstained": False, "faithfulness": 0.0},
        {"type": "unanswerable", "rank": None, "top_score": 0.4, "llm_abstained": True},
    ]


def test_gate_only_applies_to_reranker_mode():
    r = rows()[3]
    assert abstained(r, "rerank", 0.05) and not abstained(r, "hybrid", 0.05)


def test_summary_counts_abstentions_correctly():
    s = summarize(rows(), "rerank", 0.05, generate=True)
    assert s["recall@5"] == 1 / 3 and s["mrr@10"] == (1 + 1 / 7) / 3
    assert s["answered"] == 1 / 3  # row 2 gated (0.03 < 0.05), row 3 LLM abstained
    assert s["faithfulness"] == 1.0 and s["correct"] == 1 / 3
    assert s["abstention_acc"] == 1.0


def test_threshold_sweep_trades_coverage_for_abstention():
    sweep = {r["threshold"]: r for r in threshold_sweep(rows())}
    assert sweep[0.0]["abstain_on_unanswerable"] == 0.5 and sweep[0.0]["answered_answerable"] == 2 / 3
    assert sweep[0.05]["abstain_on_unanswerable"] == 1.0 and sweep[0.05]["answered_answerable"] == 1 / 3


def test_markdown_table_renders():
    res = {"threshold": 0.05, "n_answerable": 3, "n_unanswerable": 2,
           "summary": {"BM25 only": summarize(rows(), "bm25", 0.05, True)},
           "sweep": threshold_sweep(rows()), "by_type": {"fact": {"n": 3, "recall@5": 1 / 3, "correct": 1 / 3}}}
    md = to_markdown(res, generate=True)
    assert "| BM25 only | 33.3% | 0.381 |" in md and "## Abstention threshold sweep" in md


def test_ui_evaluation_tab_shows_ablation_table(page, app_url):
    """Playwright: the Evaluation tab renders the committed ablation table."""
    from pathlib import Path

    from playwright.sync_api import expect

    page.goto(app_url)
    page.get_by_role("tab", name="Evaluation").click()
    results = page.locator(".st-key-results")
    if Path("data/eval/results.md").exists():
        for config in ["BM25 only", "Dense only", "Hybrid (RRF)", "Hybrid + re-ranker"]:
            expect(results.get_by_role("cell", name=config, exact=True)).to_be_visible(timeout=60_000)
    else:
        expect(results).to_contain_text("No evaluation results yet", timeout=60_000)


def test_failures_are_categorised_from_the_rows():
    from circulariq.evaluate import failures

    gold = [{"id": i, "question": f"question {i}"} for i in "abcdefg"]
    base = {"top_score": 0.9, "llm_abstained": False, "top5": ["X p1"], "answer": "ans"}
    rows = [
        {**base, "id": "a", "type": "fact", "rank": 1, "correct": True},                       # fine
        {**base, "id": "b", "type": "fact", "rank": None},                                       # retrieval miss
        {**base, "id": "c", "type": "fact", "rank": 2, "llm_abstained": True},                 # false abstention
        {**base, "id": "d", "type": "recency", "rank": 1, "correct": False, "cites_stale": True},  # stale
        {**base, "id": "e", "type": "fact", "rank": 3, "correct": False},                       # wrong answer
        {**base, "id": "f", "type": "unanswerable", "rank": None},                               # answered it
        {**base, "id": "g", "type": "unanswerable", "rank": None, "top_score": 0.01},           # gated: fine
    ]
    got = {f["id"]: f["category"] for f in failures(rows, gold, "rerank", 0.05)}
    assert got == {"b": "retrieval miss", "c": "false abstention", "d": "used superseded rule",
                   "e": "wrong answer", "f": "answered unanswerable"}
    assert [f["id"] for f in failures(rows, gold, "rerank", 0.05)][0] == "f"  # most serious first


def test_report_rebuilds_from_saved_rows_at_any_threshold():
    from circulariq.evaluate import build_report

    gold = [{"id": str(i), "type": r["type"], "question": "q"} for i, r in enumerate(rows())]
    rs = [{**r, "id": str(i), "top5": [], "answer": "a"} for i, r in enumerate(rows())]
    saved = {"Hybrid + re-ranker + rewrite": rs}
    lo, hi = build_report(saved, gold, 0.0, True), build_report(saved, gold, 0.05, True)
    s_lo, s_hi = lo["summary"]["Hybrid + re-ranker + rewrite"], hi["summary"]["Hybrid + re-ranker + rewrite"]
    assert s_lo["abstention_acc"] == 0.5 and s_hi["abstention_acc"] == 1.0
    assert any(f["category"] == "answered unanswerable" for f in lo["failures"])
    assert not any(f["category"] == "answered unanswerable" for f in hi["failures"])
