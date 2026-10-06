# CircularIQ

Cited question answering over Reserve Bank of India circulars, for the people who read them for a living: compliance teams at banks and NBFCs.

Ask *"How long does a commercial bank have to decide whether a red-flagged account is a fraud?"* and CircularIQ finds the paragraph, answers in plain language, and cites it:

> A commercial bank has 180 days from the date of first reporting the account as red-flagged on CRILC platform to decide whether it is a fraud. [RBI/DoS/2026-27/412, Para 31](https://rbi.org.in/Scripts/NotificationUser.aspx?Id=13641&Mode=0)

*(Actual output, recorded in [docs/demo.webm](docs/demo.webm).)*

When the circulars don't contain the answer, it says **"Not found in the provided circulars."** instead of guessing.

Runs fully offline on a laptop: local embeddings, a local cross-encoder, and a local 3B LLM through Ollama.

| Cited answer | Abstention |
|---|---|
| ![answer](docs/answer.png) | ![abstain](docs/abstain.png) |

## Architecture

```mermaid
flowchart LR
  subgraph Offline["Offline (once)"]
    A[rbi.org.in<br/>300 notifications] -->|scrape.py| B[HTML + metadata<br/>ref, date, links]
    B -->|chunk.py| C[5,679 paragraph chunks<br/>para id, section, lead]
    C -->|bge-small-en-v1.5| D[(FAISS<br/>exact cosine)]
    C -->|tokenizer keeps codes| E[(BM25)]
  end
  subgraph Online["Online (per question)"]
    Q[Question] --> D & E
    D & E -->|RRF k=60, top 50| F[Hybrid list]
    F -->|MiniLM cross-encoder| G[Top 5 + scores]
    G -->|score < 0.05| X[Abstain]
    G -->|newest first, S1..S5,<br/>'may be amended by' notes| L[qwen2.5:3b via Ollama]
    L -->|S-markers to citations,<br/>uncited = abstain| ANS[Cited answer]
  end
```

| Stage | Choice | Why (details in [decisions.md](decisions.md)) |
|---|---|---|
| Source | RBI notification pages (HTML) | The PDFs sit behind a CAPTCHA; the HTML has real `<p>` paragraphs and `<table>`s |
| Chunking | One chunk per numbered paragraph (`2.1`, `5(iv)`), tables split with header repeated | Citations need paragraph numbers; fixed windows cut rules in half |
| Dense | `BAAI/bge-small-en-v1.5` + FAISS `IndexFlatIP` | Small enough for CPU; exact search is about 1 ms at this scale |
| Sparse | `rank_bm25`, codes indexed whole + by segment + by atom | `DOR.AML.REC.233/14.06.001/2026-27` must match exactly |
| Fusion | Reciprocal Rank Fusion, k = 60 (hand-written) | Rank-based, so incomparable score scales don't matter |
| Re-rank | `cross-encoder/ms-marco-MiniLM-L-6-v2`, top 50 → 5 | 9× faster than bge-reranker-base on CPU, with equal or better results on probes |
| Answer | `qwen2.5:3b` (Ollama, any OpenAI-compatible API) | Fits a 3 GB GPU; follows the strict citation format |
| Recency | Hyperlinks between circulars → "may be amended by" | Amendments link what they amend: explicit, testable signal |

## Results

82 hand-written gold questions over the corpus: 67 answerable (fact, paraphrase, exact-id, table, recency, colloquial) and 15 *unanswerable* near-misses. Evidence is stored as (circular, verbatim quote), so the gold set survives re-chunking. Full tables and every failure: [data/eval/results.md](data/eval/results.md).

| Configuration | Recall@5 | MRR@10 | Faithfulness | Correct | Answered | Abstention |
|---|---|---|---|---|---|---|
| BM25 only | 88.1% | 0.718 | 65.9% | 70.1% | 80.6% | 100% |
| Dense only | 88.1% | 0.680 | 67.3% | 73.1% | 82.1% | 100% |
| Hybrid (RRF) | 91.0% | 0.766 | 77.5% | 82.1% | 91.0% | 100% |
| **Hybrid + re-ranker (shipped)** | **95.5%** | **0.836** | 71.8% | 80.6% | 86.6% | **100%** |
| Hybrid + re-ranker + query rewrite | 88.1% | 0.776 | 69.8% | 65.7% | 71.6% | 100% |

*Correct* counts over all answerable questions, so an abstention counts as not correct. *Faithfulness* = share of answer sentences supported by the passage they cite. Both are judged by the local LLM; a hand spot-check agreed on 19/20 correctness and 17/20 faithfulness verdicts, and every disagreement was the judge being too strict.

**What the table says**

- **Hybrid beats either retriever alone.** BM25 and dense tie at 88.1% Recall@5 but miss *different* questions (exact codes vs. paraphrases). RRF fusion recovers both.
- **The re-ranker's main contribution is ordering.** MRR rises from 0.766 to 0.836 and Recall@5 to 95.5%. End-to-end correctness is within noise of plain hybrid (80.6% vs 82.1%, one question apart), because the 3B LLM, not retrieval, is now the bottleneck.
- **Query rewriting hurt, so it's off.** The 3B rewriter "generalises" specific questions (drops "for commercial banks", swaps codes, once turned "Form A2" into "RTGS"). Recall@5 fell 95.5% → 88.1% and correctness 80.6% → 65.7%. It's still in the UI as an opt-in toggle.
- **It never answered an unanswerable question.** All 15 near-misses (repo rate, LRS limit, ₹500 note withdrawal, the KYC re-verification period whose base Direction is not in the corpus, …) were refused in every configuration.
- **A fix that came from reading the failures:** 4 of the first 5 retrieval misses were answer paragraphs that never name their subject ("2. … dispense with the above reporting requirements"). Indexing each short circular's lead paragraph with its chunks lifted Recall@5 from 92.5% to 95.5% (details in [decisions.md](decisions.md), D6.9).

**Failure analysis (shipped system, 13 of 82)**

| Category | Count | What happens |
|---|---|---|
| False abstention | 8 | Evidence ranked 1–3, but the system declined. Four times the 3B model said "not found" despite the passage; twice it answered correctly but without a citation, so the strict uncited-means-abstain rule discarded it. That same rule also blocked two *wrong* uncited answers (wrong bond tenors; a circular wrongly called "not withdrawn"), a trade worth making in compliance. |
| Wrong answer | 4 | q04 inverts "Board *or* a delegated committee" into "the Board itself"; q38 gives only the unquoted-InvIT rule. q18 and q43 are actually right: the judge's two known errors. |
| Retrieval miss | 1 | q30: the NRO-return code paragraph ranks 7th behind a near-identical CIMS reporting circular. |

Recency held up: all three "deadline moved from 30 Sep to 31 Aug 2026" traps were answered with the *newer* date.

## Limitations

- **Corpus is a snapshot.** 300 notifications (IDs 13414–13725, 29 Apr – 2 Oct 2026). Consolidated "Updated as on…" Directions whose text exists only as a CAPTCHA-protected PDF are skipped. So the system knows the *amendments* to, say, the KYC Directions but not the base Directions. That is exactly why "KYC re-verification period for high-risk customers" is one of the unanswerable gold questions.
- **Small model.** qwen2.5:3b fits the 3 GB GPU but sometimes misreads a passage. Strict citation checking turns many of those misreadings into abstentions rather than wrong answers, which is the right failure direction for compliance, but it lowers coverage.
- **The judge is the same small model.** Faithfulness and correctness are judged by qwen2.5:3b, which is lenient on its own outputs. A sample was checked by hand (see the results).
- **The eval set is small and has one author.** 82 questions, and the abstention threshold was chosen on the same set it is reported on. Treat the abstention figure as optimistic.
- **Recency is link-based.** "May be amended by" comes from hyperlinks between circulars: precise when present, silent when an amendment doesn't link its predecessor or the predecessor is outside the corpus.

## What's next

1. A held-out question set written by someone who hasn't read the chunks, to get unbiased numbers and an honest abstention threshold.
2. A per-circular cap in the top 5, to fix the "sibling crowding" retrieval failure (D6.9 in `decisions.md`).
3. Date-aware retrieval: when several circulars for the same entity match, boost the newest before re-ranking, so the stale circular stops winning (the q35 failure).
4. A stronger judge (or two judges with disagreement review) for the faithfulness numbers.
5. Fit the LLM fully on the GPU with a quantised KV cache (`OLLAMA_KV_CACHE_TYPE=q8_0`) for faster answers.

## Running it

```bash
pip install -r requirements.txt
python -m playwright install chromium
ollama pull qwen2.5:3b                        # or set LLM_BASE_URL / LLM_MODEL / LLM_API_KEY

python -m circulariq.scrape --count 300       # data/raw: manifest + HTML (about 3 minutes)
python -m circulariq.chunk                    # data/chunks.jsonl
python -m circulariq.retrieve                 # data/index: FAISS + chunks (embeds on CPU)
streamlit run app.py                          # Ask tab + Evaluation tab

python -m circulariq.evaluate                 # ablation -> data/eval/results.md
pytest                                        # unit + Playwright browser tests
```

`git config core.hooksPath .githooks` enables the pre-commit hook that runs the whole suite before every commit.

## Layout

```
circulariq/scrape.py     crawl RBI notification pages -> manifest + HTML
circulariq/chunk.py      structure-aware paragraph chunking
circulariq/retrieve.py   BM25, dense, RRF, cross-encoder re-ranking, recency map
circulariq/answer.py     query rewrite, prompt, citation rendering, abstention
circulariq/evaluate.py   Recall@5, MRR@10, faithfulness, correctness, abstention, ablation
app.py                   Streamlit UI
data/make_gold.py        the 82-question gold set (source of truth)
data/eval/               results.md, results.json, and the cached LLM calls behind them
scripts/record_demo.py   drives the app with Playwright to record docs/demo.webm + screenshots
tests/                   pytest + Playwright (real RBI pages as fixtures)
decisions.md             every design decision, the alternatives, and why
```
