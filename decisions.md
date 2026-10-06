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
