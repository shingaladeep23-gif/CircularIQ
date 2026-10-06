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

## 3. Retrieval (Day 2) — *planned, to be confirmed when built*

- **Embeddings:** `BAAI/bge-small-en-v1.5` (384-d, runs on the GTX 1050). Rejected `e5-small` (similar; bge ranks higher on MTEB retrieval) and large models (VRAM).
- **Vector index:** FAISS exact inner-product search (`IndexFlatIP`) over normalised vectors. Rejected Chroma (adds a persistence/server layer we don't need) and approximate indexes (with ~10k vectors, exact search takes milliseconds; ANN would only add recall loss).
- **Keyword index:** `rank_bm25` (BM25Okapi).
- **Fusion:** Reciprocal Rank Fusion with k = 60, written by hand (~10 lines).
- **Re-ranker:** `BAAI/bge-reranker-base` cross-encoder over the top 50 → top 5.
