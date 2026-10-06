# Decision Log

Every non-obvious choice in CircularIQ: what was chosen, what was rejected, and why.
Newest entries go at the bottom of each section. Status: **done** = implemented, **planned** = decided but not built yet.

---

## 0. Environment and workflow

### D0.1 LLM runtime: local Ollama — *done (install in progress)*
- **Chosen:** Ollama running locally.
- **Rejected:** Groq free API (faster, stronger Llama 3.x models), Gemini free API.
- **Why:** Project owner's choice: fully offline, no API key, no rate limits, no data leaving the machine.
- **Trade-off accepted:** The dev machine has a GTX 1050 with 3 GB VRAM, so only ~3B-parameter models fit. Answers will be weaker and slower than a hosted 70B model.

### D0.2 LLM model: `qwen2.5:3b` — *planned*
- **Chosen:** Qwen2.5 3B Instruct (~1.9 GB quantised).
- **Rejected:** `llama3.2:3b` (similar size, but weaker at following strict output formats in our experience), `phi3:mini` (3.8B, tight fit in 3 GB), 7B+ models (do not fit in VRAM; CPU offload is too slow).
- **Why:** Best instruction following and JSON/format compliance at this size, which matters because the prompt demands exact `[Circular, Para]` citations and a fixed abstention phrase.

### D0.3 LLM client: OpenAI-compatible API through the `openai` package — *planned*
- **Chosen:** Call Ollama's `/v1` OpenAI-compatible endpoint.
- **Rejected:** The `ollama` Python package; LangChain.
- **Why:** The same 10 lines of code work against Ollama, Groq, Gemini, or OpenAI by changing `LLM_BASE_URL` / `LLM_MODEL` env vars. `openai` was already installed. LangChain was rejected per the project brief: hiding RRF, prompting, and eval behind a framework makes them impossible to explain line by line.

### D0.4 Test runner: pytest + pytest-playwright — *done*
- **Chosen:** One `pytest` suite with the Playwright plugin.
  - Pipeline steps (scrape parsing, chunking, retrieval, RRF, prompting, metrics) are tested as Python functions.
  - The Streamlit UI is tested end to end in a real Chromium browser through Playwright's `page` fixture.
- **Rejected:** Playwright Test (TypeScript/Node) for everything.
- **Why:** Playwright drives browsers; it cannot call a Python function. A Node test runner would have to shell out to Python for every pipeline step, which makes tests slower and harder to debug. pytest-playwright gives one command (`pytest`) that runs both kinds.
- **Every step gets at least one real-browser Playwright test**, not just Python asserts:
  - *Scrape:* Chromium loads a **live** RBI page and the scraper must parse the DOM the browser built (a contract test that fails if RBI changes their layout).
  - *Chunk:* Chromium renders a saved circular, and every paragraph it displays must appear in our chunks (Chromium's DOM independently checks our parser).
- **Fixtures are real RBI pages** saved under `tests/fixtures/`, not hand-made HTML, so tests exercise the real quirks.
- **Rule:** The suite must pass before every commit, enforced by `.githooks/pre-commit` (`git config core.hooksPath .githooks`).
- **Trade-off accepted:** The live contract test needs internet access to rbi.org.in, so committing offline fails. Deliberate: a silent layout change on RBI's side is exactly what it exists to catch.

### D0.5 Git identity and attribution — *planned*
- **Chosen:** Commits authored as `shingaladeep23-gif <shingaladeep23@gmail.com>` (the existing global git config), with no AI co-author trailers or AI mentions in commit messages.
- **Why:** Project owner's explicit requirement.

### D0.6 GitHub repo creation: REST API with the existing git credential — *planned*
- **Chosen:** Public repo `shingaladeep23-gif/CircularIQ`, created via `POST /user/repos` using the token already stored in Git Credential Manager.
- **Rejected:** Installing the `gh` CLI (another tool and another login for one API call); asking the owner to create the repo manually.
- **Why:** The credential already exists and pushing requires it anyway. Public, so the repo serves as a portfolio piece.

---

## 1. Data collection (Day 1)

### D1.1 Regulator: RBI — *done*
- **Chosen:** Reserve Bank of India notifications.
- **Rejected:** SEBI circulars (mentioned in the brief as an alternative).
- **Why:** RBI notification pages have stable sequential IDs and machine-readable structure (see D1.2), which makes a reproducible crawler simple.

### D1.2 Crawl strategy: walk notification IDs backwards — *done*
- **Chosen:** Fetch `NotificationUser.aspx?Id=N&Mode=0` for N = 13725, 13724, … until 300 valid notifications are collected.
- **Rejected:**
  - *Circular index page* (`BS_CircularIndexDisplay.aspx`): ASP.NET postback form with `__VIEWSTATE`/`__EVENTVALIDATION`. Scraping it means replaying form state per year/month. Fragile.
  - *Monthly notification listing*: same postback problem beyond the current month.
- **Why:** IDs are sequential, every page has the same layout, and empty IDs are trivially detected (no title or no PDF link → skip).

### D1.3 Corpus selection: latest 300 contiguous notifications — *done*
- **Chosen:** A contiguous slice (newest backwards), not topic-filtered.
- **Rejected:** Hand-picking circulars on one topic (e.g., KYC only).
- **Why:** A contiguous slice is unbiased and mirrors what a compliance team actually receives. Mixed topics also make retrieval harder (more distractors), which makes the ablation more meaningful.
- **Trade-off accepted:** Specific famous documents (e.g., the KYC Master Direction) may fall outside the slice. Gold questions are written against what is actually in the corpus.

### D1.4 Source format: notification-page HTML, not PDF — *done*
- **Chosen:** Save the HTML body of each notification page (`tr.tablecontent2`) to `data/raw/html/{id}.html`.
- **Rejected:** Downloading the PDFs from `rbidocs.rbi.org.in` and parsing them with PyMuPDF (the original plan).
- **Why:**
  1. `rbidocs.rbi.org.in` returns an image CAPTCHA ("What code is in the image?") to plain HTTP clients (`requests`, `curl` with browser headers) and to headless Chromium (tested with Playwright). Bypassing a CAPTCHA is evading bot protection, so we don't.
  2. The notification page carries the same full text, served openly.
  3. The HTML is *better* input: paragraphs are real `<p>` elements, headings are `<p class="head">`, and tables are real `<table>`s. PDF text extraction loses all three and needs heuristics to recover them.
- **Omitted:** PyMuPDF / PDF parsing entirely. `pdf_url` is still stored in metadata so the UI can link users to the official PDF.

### D1.5 Metadata captured per notification — *done*
- `id`, `title`, `ref` (e.g., `RBI/2026-27/279`), `circular_no` (department number, e.g., `A.P. (DIR Series) Circular No. 23`), `date` (ISO), `pdf_url`, `references`.
- **`references`:** IDs of older notifications that this one hyperlinks to. Amending circulars almost always link the circular they amend, so this is a free, explicit supersession signal for recency handling (Day 3). No NLP guesswork needed.
- **Reference formats found in the real corpus** (each discovered by auditing the crawl output, then pinned by `test_all_reference_formats`):
  - `RBI/2026-27/279` (standard)
  - `RBI/2026-2027/270` (four-digit second year: 67 of 300 used this and were missed by the first regex)
  - `RBI/DCM/2026-27/473`, `RBI/DoS/2026-27/221` (department-prefixed, mixed case)
  - `Notification No. FEMA 23(R)/(1)/2026-RB` (FEMA regulations carry no RBI/ ref at all; this line is used as the ref, and `circular_no` stays empty)
- **Title selector** reads `td.tableheader[align=center]` as a whole, not its `<b>` child. RBI's accessibility script rewrites that `<b>` into `<h2 class="dop_header">` once JavaScript runs; the live Playwright test caught this.
- **Body parsing split into `parse_body()`** so metadata can be re-derived from saved HTML without refetching (used once to repair the manifest after the regex fixes).

### D1.6 Crawler behaviour — *done*
- 0.5 s delay between requests (polite to a public-sector server).
- Resumable: `manifest.jsonl` is appended per notification, and a rerun skips IDs already in it.
- Raw bytes are passed to BeautifulSoup so it reads the page's declared charset. Decoding with `requests`' guessed encoding mangled characters like `₹` and `’`.
- Console output is forced to UTF-8 (`PYTHONIOENCODING=utf-8`). The Windows default codepage crashed on `₹` in a title.

### D1.8 PDF-only notifications are skipped — *done*
- **Chosen:** Skip notifications whose HTML body has no date. These are the "… Directions, 2026 (Updated as on …)" consolidated documents; their page body holds only a "Previous Versions" link, and the text exists only in the CAPTCHA-protected PDF.
- **Rejected:** Keeping them with title-only chunks (useless for answering, and noise for retrieval).
- **Trade-off accepted:** We lose the consolidated master texts and keep the amendment circulars that change them. 12 such pages were in the first 300 IDs; the crawler walked further back to keep the corpus at 300.
- **Result:** 300 notifications, IDs 13414–13725, dated 2026-04-29 to 2026-10-02.

### D1.7 What goes into git — *done*
- **Committed:** code, tests, `data/raw/manifest.jsonl` (small; documents exactly which circulars form the corpus), the gold Q&A set, eval results.
- **Not committed (gitignored):** raw HTML, chunk files, vector and BM25 indexes. All are regenerated by the pipeline scripts.
- **Why:** Keeps the repo small. Anyone can rebuild the identical corpus from the manifest IDs.

---

## 2. Chunking (Day 1)

### D2.1 Structure-aware chunking on the circular's own numbering — *done*
- **Chosen:** One chunk per numbered paragraph (`2`, `2.1`, `5(iv)`, …), tagged with its section heading. Unnumbered blocks attach to the current paragraph.
- **Rejected:** Fixed-size token windows with overlap (the naive baseline).
- **Why:** Fixed windows cut mid-rule ("customers shall re-verify every" | "two years"). Paragraph numbers are also exactly what a citation needs: `[RBI/2026-27/279, Para 2]`.
- **Size guard:** Paragraphs over ~350 words (≈450 tokens, under the embedding model's 512-token limit) split at block, then sentence, boundaries.
- **Paragraph-number rule:** `2.`, `2.1`, `3.2.1.` followed by a capital letter count as paragraph numbers. Requiring the dot and the capital rejects body text that merely starts with a number ("30 days notice", "2.5 per cent").
- **Under a numbered heading**, only that heading's own sub-numbers (`5.2` under `5.`) start a new paragraph; a `1.` inside section 5 is a list item, not paragraph 1.
- **Sub-headings** like `(iv) Tears` under `5. Fitness Sorting` become para `5(iv)`.
- **The repeated title** above an attached Master Direction becomes para `Preamble`.
- **Result:** 300 circulars → 5,679 chunks; median 59 words, p90 263, max 350.

### D2.2 Boilerplate removal — *done*
- Drop everything before the first heading (reference line, date, addressee, "Madam / Sir") and the sign-off ("Yours faithfully", signatory name and designation).
- **Why:** These blocks appear in every circular and would match generic queries, polluting retrieval.

### D2.3 Tables — *done*
- Render as `cell | cell | cell` rows. Large tables split by rows with the header row repeated in each piece.
- **Why:** Keeps column meaning attached to each value, so a chunk that only says "₹10 | 0.07 | 85%" still carries "Denomination | Max density difference | Min reflectance".

### D2.4 HTML quirks handled — *done*
- The outer layout `<table>` wraps the whole letter, so only `table.tablebg` counts as a data table.
- `<li>` elements contain duplicate `<p>` children, so a block nested inside an already-taken block is skipped.
- **Amendments quote inserted text inside `<blockquote>`**, sometimes including a `<p class="head">`. Such headings are treated as body text, so the inserted text stays inside the amending paragraph (e.g., para 3 of RBI/2026-27/200 keeps "A1. Income Recognition…", 62C, and 62D together).
- **Text is extracted the way a browser renders it** (`<br>` → space, then `get_text()` with no separator). The first version used `get_text(" ")`, which put spaces around every inline tag ("subject ( Annexed ) stand"). The Playwright cross-check caught it.

---

## 3. Retrieval (Day 2)

### D3.1 Embedding model: `BAAI/bge-small-en-v1.5` — *done*
- **Chosen:** bge-small-en-v1.5 (33M params, 384-d) via sentence-transformers.
- **Rejected:** `intfloat/e5-small-v2` (same size, slightly lower MTEB retrieval scores, and needs `query:`/`passage:` prefixes on both sides); `bge-base`/`bge-large` (3–10× slower on CPU for a modest gain); OpenAI embeddings (paid, and the project is offline by choice, see D0.1).
- **Query instruction:** Queries get bge's recommended prefix ("Represent this sentence for searching relevant passages: "); passages don't. This asymmetry is how bge-v1.5 was trained for short-query retrieval.
- **Contextual chunk text:** What gets embedded is `title + section + text`, not the bare paragraph. Many paragraphs ("2. Accordingly, it has been decided…") mean nothing without the circular's subject.

### D3.2 CPU-only PyTorch — *done*
- **Chosen:** Keep the installed CPU build of torch.
- **Rejected:** Installing a CUDA build for the GTX 1050.
- **Why:** The card is Pascal (sm_61) with 3 GB VRAM, and recent CUDA builds of PyTorch are dropping Pascal. bge-small embeds 5.7k chunks on CPU in a few minutes, once. Query-time encoding is a single sentence. Not worth a 2.5 GB reinstall with an uncertain outcome.

### D3.3 Vector index: FAISS `IndexFlatIP` — *done*
- **Chosen:** Exact inner-product search over L2-normalised vectors (= cosine similarity).
- **Rejected:**
  - *Chroma:* a database layer (persistence, collections, its own embedding hooks) we don't need, and it hides the search behind an API.
  - *Approximate indexes (IVF, HNSW):* at 5.7k × 384 floats (~9 MB), brute force takes about a millisecond. ANN would only add recall loss and tuning knobs.
- **Self-contained index dir:** `data/index/` holds `dense.faiss` plus its own `chunks.jsonl` copy, so FAISS row *i* is always chunk *i* even if `data/chunks.jsonl` is regenerated later.
- **Upgrade path:** Switch to `IndexHNSWFlat` if the corpus grows past ~500k chunks.

### D3.4 Keyword index: `rank_bm25.BM25Okapi`, built at load time — *done*
- **Chosen:** Rebuild BM25 in memory when the Retriever loads (under a second for 5.7k chunks).
- **Rejected:** Pickling the BM25 object (fragile across library versions); Elasticsearch/OpenSearch (a server for 5.7k documents).
- **BM25 sees `ref + circular_no + title + section + text`**, so a query containing "RBI/2026-27/200" or "DOR.AML.REC.233" hits the circular even though the code never appears in its paragraphs.
- **Tokenizer indexes codes at three levels:** whole code, `/` segments, and atoms. `DOR.AML.REC.233/14.06.001/2026-27` → the whole string; `dor.aml.rec.233`, `14.06.001`, `2026-27`; `dor`, `aml`, `rec`, `233`, … A user typing any partial form still matches. The first version skipped the middle level; a unit test caught it.
- **Omitted:** Stemming and stopword lists. BM25's IDF already down-weights common words, and stemming regulatory terms ("provisioning" → "provis") risks merging distinct concepts. Revisit if eval shows morphology misses.

### D3.5 Fusion: Reciprocal Rank Fusion, k = 60, hand-written — *done*
- **Chosen:** `score(d) = Σ 1 / (60 + rank)` over the BM25 and dense top-50 lists. 10 lines in `retrieve.rrf`.
- **Rejected:** Weighted sum of normalised scores (BM25 scores are unbounded and query-dependent, cosine is in [-1, 1]; any normalisation is arbitrary and needs tuning); library fusion helpers (the brief asks for code that can be explained line by line).
- **Why k = 60:** The value from the original RRF paper (Cormack et al., 2009); it damps the gap between rank 1 and rank 2 so one list cannot dominate. Not tuned, to avoid overfitting the small gold set.

### D3.6 UI started on Day 2 instead of Day 6 — *done*
- **Chosen:** A minimal Streamlit search page now (question box, retrieval-mode switch, passages with citation links and scores), grown each day.
- **Why:** It gives every pipeline step a real end-to-end Playwright test (type a question in Chromium, assert the right circular appears), as the project owner asked. It also meets the Day 6 requirement to show retrieved chunks with scores.
- **Stable selectors:** Each result is `st.container(key="hit-N")`, which Streamlit renders as CSS class `st-key-hit-N`. Tests use those and accessible labels, never Streamlit's internal class names.
- **Hermetic UI tests:** `app.py` reads the index location from `CIRCULARIQ_INDEX`. `tests/conftest.py` builds a small index from the 5 real fixture circulars and launches Streamlit on a free port against it, so the browser tests never depend on the full local corpus.

---

## 4. Re-ranking and answering (Day 3)

### D4.1 Re-ranker: `cross-encoder/ms-marco-MiniLM-L-6-v2` — *done*
- **Chosen:** MiniLM-L-6 cross-encoder (22M params) re-scoring the hybrid top 50 and keeping the top 5.
- **Rejected:** `BAAI/bge-reranker-base` (278M params), the original plan.
- **Evidence (full 5,679-chunk index, 4 probe questions, CPU):**

  | Model | Time per query (50 pairs) | Correct top passage |
  |---|---|---|
  | ms-marco-MiniLM-L-6-v2 | ~5 s | 4/4 |
  | bge-reranker-base | ~45 s | 3/4 (picked para 5(iii) Dog-Ears for a question about tear limits; the answer is 5(iv) Tears) |

- **Why:** 9× faster with no observed quality loss. 45 s per query would make the UI unusable and the eval take hours.
- **Kept switchable:** `CIRCULARIQ_RERANKER=BAAI/bge-reranker-base` swaps it back for the ablation.

### D4.2 Re-ranker scores are forced into [0, 1] with an explicit sigmoid — *done*
- `CrossEncoder(..., activation_fn=torch.nn.Sigmoid())`.
- **Why:** MiniLM outputs raw logits (−11 to +10); bge-reranker outputs probabilities. The abstention threshold (D4.4) needs one scale, whatever the model.
- **Bug this replaced:** The first version applied its own sigmoid on top of bge-reranker's built-in one, squeezing every score into 0.50–0.73 (an irrelevant question scored 0.5005). Ranking was unaffected, so only `test_reranker_scores_irrelevant_question_low`, which checks the absolute score, caught it.

### D4.3 Citations via `[S1]` markers, rendered in code — *done*
- **Chosen:** Sources are given to the LLM as `[S1] RBI/…, Para 7 | dated … | title`. The LLM cites `[S1]`, and `answer.render()` replaces each marker with `[RBI/DCM/2026-27/473, Para 7]`.
- **Rejected:** Asking the LLM to write the full citation itself.
- **Why:** (1) A 3B model mangles long strings like `DOR.STR.REC.165/21-04-048/2026-27`. (2) Markers are verifiable: a marker pointing at a source that wasn't given (`[S9]` with 5 sources) is dropped instead of becoming a fabricated citation. (3) We know exactly which sources were cited, which the faithfulness eval needs.

### D4.4 Abstention in three layers — *done*
1. **Retrieval gate:** If the best re-ranker score is below `CIRCULARIQ_MIN_SCORE` (default 0.05, provisional until tuned on the gold set on Day 5), answer "Not found in the provided circulars." *without calling the LLM*. Cheap, and the LLM cannot be talked into answering from irrelevant context.
2. **Prompted abstention:** The system prompt requires that exact phrase when the sources don't contain the answer.
3. **Uncited answers are not trusted:** If the LLM answers but cites no valid source, the output is replaced by the abstention phrase.
- **Trade-off accepted:** Layer 3 will sometimes discard a correct but uncited answer. For compliance use, a missed answer costs less than an unsupported one. The eval measures how often it happens.

### D4.5 Recency and supersession from hyperlinks — *done*
- **Chosen:** Each chunk carries `references` (the notification IDs its page links to). The Retriever builds a `cited_by` map: circular → newer circulars *in the corpus* that link to it. 42 of the 300 circulars have one.
  - Sources go to the LLM **newest first**, each with its date.
  - A source cited by a newer circular gets the note "newer circular X dated Y refers to this one and may amend it".
  - The prompt says to follow the newer source on conflict and to mention the older instruction was amended.
  - The UI shows a "May be amended by …" warning on such passages.
- **Rejected:** Detecting conflicts with NLP or LLM comparison of passage pairs (slow, unreliable at 3B, hard to test).
- **Why:** RBI amendments hyperlink the circular they amend, so the signal is explicit and free, and it is deterministic to test.
- **Known limit:** A link means "refers to", not always "amends". Hence the wording "*may* amend", and the LLM decides from the text.

### D4.6 Query rewriting by the LLM — *done*
- The LLM turns the question into one search query, expanding vague words into regulatory terms and keeping codes, amounts and dates verbatim. Empty or garbage output falls back to the original question.
- **The answer prompt still receives the original question**; only retrieval uses the rewrite.
- **Observed failure (kept for the failure analysis):** "what about the money sending form thing, who approves the internal rules?" (meaning Form A2) was rewritten to an RTGS query. Retrieval missed, and the system abstained rather than hallucinating. The Day 5 ablation measures whether rewriting helps or hurts overall.

### D4.7 LLM settings — *done*
- `temperature=0` for reproducible answers and eval runs.
- The OpenAI-compatible client (D0.3) is configured by `LLM_BASE_URL`, `LLM_MODEL` and `LLM_API_KEY`. Defaults: local Ollama with `qwen2.5:3b`.

### D4.8 Testing the LLM step — *done*
- **Unit tests use a scripted `FakeLLM`** that returns fixed replies and records the prompts. This makes the tests deterministic and lets them assert on what was sent (grounding rules present, `[S1]` labels correct, LLM not called when the gate abstains).
- **Two Playwright tests drive the real UI with the real local LLM:** one grounded question (must cite RBI/DCM/2026-27/473 and say "quarter"), one out-of-corpus question (must abstain). Assertions are deliberately loose because LLM wording varies.
- These two tests are **skipped, not failed, when Ollama is not running**, so the repo's suite still runs on a machine without a local LLM. On the dev machine Ollama is running, so they always execute before a commit.
- **UI fallback:** If the LLM is unreachable, the app shows an error and still lists the retrieved passages.
- The live RBI contract test got a 90 s navigation timeout after one transient failure while the CPU was saturated by model tests.

---

## 5. Gold Q&A set (Day 4)

### D5.1 Size and mix — *done*
- **82 questions: 67 answerable, 15 unanswerable** (the brief asks for 60–100 with about 15 unanswerable).
- **Types**, so failures can be broken down later:

  | Type | What it tests |
  |---|---|
  | `fact` | Direct lookups of numbers, dates and obligations |
  | `paraphrase` | Wording deliberately different from the source (tests dense retrieval) |
  | `exact-id` | Circular numbers and return codes like RBI/2026-27/273, R343 (tests BM25) |
  | `table` | The answer lives in a table row (tests table chunking) |
  | `recency` | A newer circular overrides an older one (tests D4.5) |
  | `colloquial` | Vague, informal phrasing (tests query rewriting, D4.6) |
  | `unanswerable` | Plausible for this corpus, but the answer is not in it (tests abstention, D4.4) |

- **Coverage:** 50+ different circulars: small standalone circulars, FEMA notifications, currency management, and the large consolidated Directions (fraud, cybersecurity, compliance, audit, KCC, market risk, Lead Bank Scheme, pensions).

### D5.2 Evidence is (notification id, verbatim quote), not chunk ids — *done*
- **Chosen:** `"evidence": [{"nid": 13641, "quote": "within 180 days from the date of first reporting"}]`. A retrieved chunk is relevant if it is from that notification and contains the quote (whitespace-insensitive).
- **Rejected:** Storing chunk ids like `13641-31`.
- **Why:** Chunk ids change whenever the chunker changes (a tweak to the paragraph regex renumbers everything after it). Chunk-id gold would silently go stale and corrupt every metric. Quote-based gold survives re-chunking, and `python -m circulariq.evaluate --validate` (also a test) proves every quote still exists.
- **Same circular required:** The corpus has near-identical amendments issued separately to Commercial Banks, Small Finance Banks, Payments Banks, UCBs and so on. Questions name the entity type, and only the named entity's circular counts. Retrieving the Small Finance Bank copy for a Commercial Bank question is a real error for a compliance officer.

### D5.3 Recency questions record the stale evidence — *done*
- Each `recency` question also lists `stale` evidence: the older circular's superseded text (e.g., the priority-sector FCNR(B) exemption end date, moved from September 30, 2026 by RBI/2026-27/232 to August 31, 2026 by RBI/2026-27/256).
- **Why:** The eval can then tell "answered from the outdated rule" apart from "retrieved nothing". The three FCNR(B) date changes are natural traps: the old date sounds just as authoritative.

### D5.4 Unanswerable questions were verified absent — *done*
- Every unanswerable question's key terms were searched for in all 5,679 chunks (repo rate, LRS, DICGC, LTV, contactless, interchange fee, Leh, and so on): zero hits.
- **Near-misses on purpose:** "When will ₹500 notes be withdrawn?" sits next to the real ₹2000 withdrawal circular. "Current CRR percentage?" sits next to a dozen CRR amendment circulars that never state the rate. "KYC re-verification period for high-risk customers" (the brief's own example) sits next to KYC amendments that only change the certified-copy rule.

### D5.5 How the questions were written — *done*
- Questions were written by reading each circular's chunks, with answers taken only from the text, and phrased to avoid copying the source wording except where the type requires it (`exact-id`, `table`).
- The set lives in `data/make_gold.py` (readable Python, one `add()` per question) and is generated into `data/gold.jsonl`.
- **Known limit:** One author wrote all questions, so phrasing has a single style. A second annotator writing 20 more questions blind (without reading the chunks first) would be the best next improvement to the eval.

---

## 6. Evaluation (Day 5)

### D6.1 Retrieval metrics: Recall@5 and MRR@10 — *done*
- **Recall@5:** Was any relevant chunk (D5.2) in the top 5? Five is what the LLM sees, so this is the ceiling on answer quality.
- **MRR@10:** 1/rank of the first relevant chunk, 0 if it's outside the top 10. Cut at 10 so a hit at rank 40 doesn't earn credit the generator never benefits from.
- Computed over the 67 answerable questions only.

### D6.2 Faithfulness: claim-level LLM judge — *done*
- The raw answer is split into sentences. Each sentence is judged YES/NO against **only the passages it cites** (all five, if it cites none). Faithfulness = supported sentences / all sentences, averaged over answered questions.
- **Rejected:** Judging the whole answer at once (one unsupported sentence hides among supported ones); RAGAS and similar libraries (another dependency and another LLM wrapper, and the brief asks for a hand-written eval loop).
- **Judging against the cited passage, not all retrieved ones,** catches mis-citation: a true statement attributed to the wrong paragraph fails. That matters in compliance, where the citation is what gets checked.

### D6.3 Correctness: a second judge question against the gold answer — *done*
- **Added beyond the brief.** Faithfulness alone can't catch an answer that is perfectly supported by an *outdated* circular. "Correct" asks whether the answer states the same key facts as the gold answer.
- Computed over **all** answerable questions; abstaining counts as not correct. Otherwise a system that abstains on everything hard would look perfect.
- The rows also record `cites_evidence` and `cites_stale`, for the recency analysis.

### D6.4 The judge is the same local qwen2.5:3b — *done, with a spot check*
- **Chosen:** Reuse the local model, temperature 0, YES/NO only.
- **Rejected:** A stronger hosted judge (breaks the offline choice, D0.1).
- **Known bias:** A model judging its own outputs is lenient. Mitigation: the brief's hand spot-check, done on a sample and reported in the results.

### D6.5 Abstention threshold chosen from a sweep, not guessed — *done*
- The eval runs generation with the gate *disabled* and stores each question's top re-ranker score, then applies the gate afterwards at several thresholds (0 to 0.5). This yields a trade-off table (unanswerable questions caught vs. answerable questions still answered) with zero extra LLM calls.
- **Caveat:** The threshold is picked on the same 82 questions it is measured on. With only 15 negatives, the abstention number is optimistic; a held-out set would be needed for an unbiased figure.

### D6.6 Every LLM call is cached on disk — *done*
- `data/eval/llm_cache.jsonl`, keyed by a SHA-1 of the exact messages. Re-running the eval after a metrics-only change costs nothing, and results are reproducible.
- The cache *is* committed. It is the raw evidence behind the reported numbers.

### D6.7 Ablation configurations — *done*
- BM25 only → dense only → hybrid (RRF) → hybrid + re-ranker → hybrid + re-ranker + query rewrite (the full system).
- All five share the same answer prompt and LLM; only retrieval differs. The score gate exists only where re-ranker scores exist.
- **Omitted:** A `bge-reranker-base` row. At about 45 s per query on CPU, it would add about an hour of compute to show what the 4-probe comparison in D4.1 already indicated. Add it if a GPU becomes available (`CIRCULARIQ_RERANKER=BAAI/bge-reranker-base`).

### D6.8 Evaluation tab in the UI — *done*
- The app's second tab renders `data/eval/results.md`, so a demo shows the ablation table next to the live system. A Playwright test checks the four configuration rows render.

### D6.9 Lead-paragraph context for short circulars (an experiment driven by eval failures) — *done, kept*
- **Observation (first retrieval run):** 4 of the 5 full-system misses were the same failure. The right circular *was* retrieved, but as its context paragraph ("Please refer to … temporary withdrawal of the interest rate ceiling on FCNR(B)…"). The answering paragraph ("5. … substituted with 'until August 31, 2026'", or "2. … dispense with the above reporting requirements") never names its subject, so neither BM25 nor dense could match it.
- **Change:** In circulars with ≤ 10 chunks, every chunk after the first carries the first 60 words of the lead paragraph as an index-only `lead` field, added to the BM25 text, the embedding text and the re-ranker input, but **not** to the cited text or the gold-matching text.
- **Rejected alternatives:**
  - *Merging small paragraphs into bigger chunks:* loses paragraph-level citations, and long Directions would get blurrier chunks.
  - *LLM-written context per chunk ("contextual retrieval"):* 5,679 LLM calls on a 3B model, non-deterministic, and slow to rebuild.
  - *Neighbour expansion at answer time:* helps the LLM but not retrieval, which is where the miss was.
- **Long Directions excluded:** Their lead paragraph is generic legal preamble ("In exercise of the powers conferred…"), which would add the same noise to hundreds of chunks.
- **Result (same gold set, same models):**

  | Configuration | Recall@5 | MRR@10 |
  |---|---|---|
  | BM25 only | 86.6% → 88.1% | 0.659 → 0.718 |
  | Dense only | 85.1% → 88.1% | 0.676 → 0.680 |
  | Hybrid (RRF) | 89.6% → 91.0% | 0.720 → 0.766 |
  | Hybrid + re-ranker | 92.5% → 95.5% | 0.831 → 0.836 |

  Full system: fixed q07, q22, q36; broke q20.
- **New failure it introduced ("sibling crowding"):** All chunks of a short circular now share the lead, so they compete with each other. In q20, the Maldives line-of-credit amount is in para 1 but ranked 6th, behind paras 2–6 of the same circular.
- **Deliberately not tuned further:** The remaining misses (q20, q30, q35) are all at ranks 6–7. More changes measured on these 67 questions would start fitting the eval set rather than the problem. A per-circular cap in the top 5, or showing the lead to the LLM, are the next things to try against a fresh question set.

### D6.10 Tolerate citation-marker variants, but still reject uncited answers — *done*
- **Found during the eval run:** 8 of the first 42 answers had no `[S#]` marker. Reading all 8:
  - **1 was a legitimate citation in a variant format:** `[Source S1] The Board can delegate…`. `normalize_markers()` now rewrites `[Source S1]`, `[S1, S3]` and `[S2 and S4]` to `[S1][S3]` before rendering. A test pins this, including that real `[RBI/…, Para 2]` citations are left untouched.
  - **7 were genuinely uncited**, and D4.4's "uncited = abstain" rule was right to block them. Two of them gave the *stale* September 30, 2026 date on recency questions. Another claimed a circular was *not* withdrawn when the withdrawal table lists it. Without the rule, all three wrong answers would have reached the user.
- **Why stop and restart the eval:** The marker bug would have counted correct, cited answers as abstentions in every configuration, understating all of them. The disk cache (D6.6) meant the restart replayed the finished questions without new LLM calls.

### D6.11 Eval runtime on this machine — *observed*
- `ollama ps` during the eval: qwen2.5:3b at 4096 context occupies 2.4 GB, split **38% CPU / 62% GPU**. Model weights plus KV cache exceed the GTX 1050's 3 GB, so part of every forward pass runs on the CPU.
- One question costs 1 answer call + 1 judge call per answer sentence + 1 correctness call. The 5-configuration eval takes a few hours, so the disk cache (D6.6) matters.
- **Not done (upgrade path):** `OLLAMA_FLASH_ATTENTION=1` with `OLLAMA_KV_CACHE_TYPE=q8_0` roughly halves KV-cache memory and would likely fit the model fully on the GPU. Not switched mid-run, to keep all configurations' generations comparable.
