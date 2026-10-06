"""Step 1b: structure-aware chunking."""
import json
from pathlib import Path

from circulariq.chunk import MAX_WORDS, NUM_RE, blocks, chunk_circular, split_long, table_pieces

FX = Path(__file__).parent / "fixtures"
META = {m["id"]: m for m in map(json.loads, (FX / "manifest.jsonl").read_text(encoding="utf-8").splitlines())}


def chunks(nid):
    return chunk_circular(META[nid], (FX / f"{nid}.html").read_text(encoding="utf-8"))


def by_para(cs):
    return {c["para"]: c for c in cs}


def test_paragraph_number_regex():
    assert NUM_RE.match("2. On a review").group(1) == "2"
    assert NUM_RE.match("2.1 A fit note").group(1) == "2.1"
    assert NUM_RE.match("2.Accordingly").group(1) == "2"
    for not_a_para in ["30 days notice", "2.5 per cent of", "10 lakh"]:
        assert NUM_RE.match(not_a_para) is None


def test_one_chunk_per_numbered_paragraph():
    cs = chunks(13578)
    assert [c["para"] for c in cs] == ["1", "2", "3", "4"]
    assert cs[1]["text"].startswith("2. Consequent")


def test_boilerplate_removed():
    text = " ".join(c["text"] for c in chunks(13723) + chunks(13578))
    for junk in ["Madam", "Yours faithfully", "Chief General Manager", "RBI/2026-27/200"]:
        assert junk not in text


def test_quoted_amendment_stays_in_its_paragraph():
    # 62C/62D are inserted text quoted inside para 3, including a quoted <p class=head>
    para3 = by_para(chunks(13578))["3"]["text"]
    assert "62C." in para3 and "62D." in para3 and "A1. Income Recognition" in para3


def test_master_direction_sections_and_subsections():
    p = by_para(chunks(13723))
    assert p["2.1"]["text"].startswith("2.1 A fit note")
    assert p["2.1"]["section"].startswith("2. Guidelines on Note Authentication")
    assert p["5(iv)"]["section"] == "(iv) Tears"
    assert "Preamble" in p  # repeated title above the Master Direction body


def test_table_rows_keep_header():
    tears = by_para(chunks(13723))["5(iv)"]["text"]
    assert "Sl. No. | Direction | Width | Length" in tears
    assert "Vertical | 4 mm | 8 mm" in tears


def test_list_items_not_duplicated():
    # <li><p>same text</p></li> must be emitted once
    texts = [t for k, t in blocks((FX / "13723.html").read_text(encoding="utf-8")) if k == "p"]
    assert sum(t.startswith("Repairs covering an area greater than 100") for t in texts) == 1


def test_metadata_on_every_chunk():
    for c in chunks(13723):
        assert c["nid"] == 13723 and c["date"] == "2026-10-02" and c["para"] and c["text"]
        assert c["url"].endswith("Id=13723&Mode=0")
    assert len({c["chunk_id"] for c in chunks(13723)}) == len(chunks(13723))


def test_size_limit_respected():
    long = " ".join(f"Sentence number {i} is here." for i in range(400))
    pieces = split_long(long)
    assert len(pieces) > 1 and all(len(p.split()) <= MAX_WORDS for p in pieces)
    assert " ".join(pieces) == long  # nothing lost
    rows = ["H1 | H2"] + [f"row {i} " + "word " * 30 + "| x" for i in range(40)]
    tp = table_pieces(rows)
    assert len(tp) > 1 and all(p.startswith("H1 | H2") for p in tp)
    assert all(len(c["text"].split()) <= MAX_WORDS for nid in META for c in chunks(nid))


def test_browser_rendered_text_is_fully_chunked(page):
    """Playwright/Chromium renders the circular; every paragraph it shows must be in some chunk
    (except the addressee/sign-off boilerplate we drop on purpose)."""
    import re

    page.goto((FX / "13723.html").resolve().as_uri())
    shown = page.locator("p").evaluate_all("els => els.map(e => e.innerText)")
    corpus = re.sub(r"\s+", " ", " ".join(c["section"] + " " + c["text"] for c in chunks(13723)))
    boiler = re.compile(r"^(RBI/|October \d|The Chairman|Madam|Yours faithfully|\(Sanjeev|Encl)")
    missing = [t for t in (re.sub(r"\s+", " ", s).strip() for s in shown) if t and not boiler.match(t) and t not in corpus]
    assert missing == []


def test_short_circulars_carry_lead_paragraph_for_indexing():
    from circulariq.retrieve import doc_text

    short = chunks(13578)  # 4 chunks
    lead = " ".join(short[0]["text"].split()[:60])
    assert "lead" not in short[0] and all(c["lead"] == lead for c in short[1:])
    assert lead in doc_text(short[2]) and lead not in short[2]["text"]  # indexed, never cited
    assert not any("lead" in c for c in chunks(13723))  # long Master Direction: preamble is generic
