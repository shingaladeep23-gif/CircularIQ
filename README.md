# CircularIQ

Cited question answering over RBI circulars: hybrid retrieval (BM25 + dense, RRF), cross-encoder re-ranking, answers that cite circular and paragraph, and abstention when the corpus has no answer.

Work in progress. Design decisions are logged in [decisions.md](decisions.md).

```bash
pip install -r requirements.txt && python -m playwright install chromium
python -m circulariq.scrape --count 300   # data/raw/manifest.jsonl + html
python -m circulariq.chunk                # data/chunks.jsonl
pytest                                    # unit + Playwright browser tests
```
