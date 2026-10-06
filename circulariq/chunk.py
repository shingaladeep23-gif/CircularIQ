"""Structure-aware chunking: one chunk per numbered paragraph of each circular.

python -m circulariq.chunk   ->  data/chunks.jsonl
"""
import json
import re
from pathlib import Path

from bs4 import BeautifulSoup

RAW = Path("data/raw")
OUT = Path("data/chunks.jsonl")
MAX_WORDS = 350  # ~450 tokens, under bge-small's 512-token limit
LEAD_WORDS = 60  # lead paragraph carried into the index header of short circulars
SHORT_CIRCULAR = 10  # chunks; longer documents open with generic legal preamble, so no lead
PAGE = "https://rbi.org.in/Scripts/NotificationUser.aspx?Id={}&Mode=0"

NUM_RE = re.compile(r"^(\d{1,2}(?:\.\d{1,2}){1,3}|\d{1,2}(?=\.))\.?\s*(?=[A-Z(\"'‘“])")  # "2. On", "2.1 A", not "30 days"/"2.5 per cent"
SUB_RE = re.compile(r"^\(([ivxlc]+|[a-z])\)\s*", re.I)  # "(iv) Tears", "(a) ..."
SIGNOFF_RE = re.compile(r"^yours (faithfully|sincerely)", re.I)


def table_rows(table) -> list[str]:
    rows = []
    for tr in table.find_all("tr"):
        cells = [re.sub(r"\s+", " ", c.get_text()).strip() for c in tr.find_all(["td", "th"])]
        if any(cells):
            rows.append(" | ".join(cells))
    return rows


def blocks(html: str):
    """Yield (kind, payload) in document order: ('head', text), ('p', text), ('table', rows)."""
    soup = BeautifulSoup(html, "html.parser")
    for br in soup.find_all("br"):
        br.replace_with(" ")  # then join text with no separator, like a browser's innerText
    taken = set()
    for el in soup.find_all(["p", "li", "table"]):
        if any(id(a) in taken for a in el.parents):
            continue  # nested inside a block we already emitted (li>p, table>p)
        if el.name == "table":
            if "tablebg" not in (el.get("class") or []):
                continue  # layout table wrapping the whole letter; descend into it
            taken.add(id(el))
            rows = table_rows(el)
            if rows:
                yield "table", rows
            continue
        if el.name == "li" and el.find("p"):
            continue  # its <p> children are emitted instead
        taken.add(id(el))
        text = re.sub(r"\s+", " ", el.get_text()).strip()
        # a heading inside <blockquote> is text quoted by an amendment, not a section of this circular
        is_head = "head" in (el.get("class") or []) and not el.find_parent("blockquote")
        if text:
            yield ("head" if is_head else "p"), text


def split_long(text: str, limit: int = MAX_WORDS) -> list[str]:
    """Split text at sentence boundaries into pieces of at most ~limit words."""
    if len(text.split()) <= limit:
        return [text]
    out, cur = [], []
    for sent in re.split(r"(?<=[.;:])\s+", text):
        if cur and len(" ".join(cur + [sent]).split()) > limit:
            out.append(" ".join(cur))
            cur = []
        cur.append(sent)
    if cur:
        out.append(" ".join(cur))
    # a single sentence longer than the limit: hard-split by words
    return [" ".join(w[i:i + limit]) for piece in out for w in [piece.split()] for i in range(0, len(w), limit)]


def table_pieces(rows: list[str], limit: int = MAX_WORDS) -> list[str]:
    """Split a table by rows, repeating the header row in every piece."""
    head, body = rows[0], rows[1:]
    pieces, cur = [], [head]
    for r in body:
        if len(cur) > 1 and len(" ".join(cur + [r]).split()) > limit:
            pieces.append("\n".join(cur))
            cur = [head]
        cur.append(r)
    pieces.append("\n".join(cur))
    return [q for p in pieces for q in split_long(p, limit)]  # a single huge row still gets split


def chunk_circular(meta: dict, html: str) -> list[dict]:
    paras = []  # list of (para_id, section, [texts])
    started = signed_off = False
    section, section_num, para = "", "", "1"

    def add(text):
        if paras and paras[-1][0] == para and paras[-1][1] == section:
            paras[-1][2].append(text)
        else:
            paras.append((para, section, [text]))

    for kind, payload in blocks(html):
        if kind == "head":
            started, signed_off = True, False
            section = payload
            m, s = NUM_RE.match(payload), SUB_RE.match(payload)
            if m:
                section_num = para = m.group(1)
            elif s and section_num:
                para = f"{section_num}({s.group(1)})"
            elif s:
                para = f"({s.group(1)})"
            elif not paras:
                para = "1"  # the circular's title: first, unnumbered paragraph is para 1
            elif payload == paras[0][1]:
                section_num, para = "", "Preamble"  # title repeated atop the attached Master Direction
            else:
                section_num, para = "", payload[:40]  # "Annex", "List of circulars withdrawn"
            continue
        if not started or signed_off:
            continue  # addressee block before the title / signature after the sign-off
        if kind == "p":
            if SIGNOFF_RE.match(payload):
                signed_off = True
                continue
            m = NUM_RE.match(payload)
            # under a numbered heading, only its own sub-numbers ("5.2" under "5.") are paragraph IDs;
            # anything else ("1. machines which...") is a list item inside the current paragraph
            if m and (not section_num or m.group(1).split(".")[0] == section_num.split(".")[0]):
                para = m.group(1)
            add(payload)
        else:
            for piece in table_pieces(payload):
                add(piece)

    chunks = []
    for para_id, sec, texts in paras:
        # pack the paragraph's blocks into pieces <= MAX_WORDS, splitting oversized blocks
        pieces, cur = [], []
        for t in (p for t in texts for p in ([t] if "\n" in t else split_long(t))):
            if cur and len(" ".join(cur + [t]).split()) > MAX_WORDS:
                pieces.append("\n".join(cur))
                cur = []
            cur.append(t)
        if cur:
            pieces.append("\n".join(cur))
        for text in pieces:
            chunks.append({
                "chunk_id": f"{meta['id']}-{len(chunks)}",
                "nid": meta["id"],
                "ref": meta["ref"],
                "circular_no": meta["circular_no"],
                "title": meta["title"],
                "date": meta["date"],
                "para": para_id,
                "section": sec,
                "text": text,
                "url": PAGE.format(meta["id"]),
                "references": meta.get("references", []),  # older circulars this one cites (recency)
            })
    # In short circulars the answer paragraph ("2. ... dispense with the above requirements") often
    # never names its subject; the lead paragraph does. Carry it as index-only context.
    if 1 < len(chunks) <= SHORT_CIRCULAR:
        lead = " ".join(chunks[0]["text"].split()[:LEAD_WORDS])
        for c in chunks[1:]:
            c["lead"] = lead
    return chunks


def main():
    metas = [json.loads(l) for l in (RAW / "manifest.jsonl").open(encoding="utf-8")]
    n = 0
    with OUT.open("w", encoding="utf-8") as out:
        for meta in metas:
            html = (RAW / "html" / f"{meta['id']}.html").read_text(encoding="utf-8")
            for c in chunk_circular(meta, html):
                out.write(json.dumps(c, ensure_ascii=False) + "\n")
                n += 1
    print(f"{len(metas)} circulars -> {n} chunks -> {OUT}")


if __name__ == "__main__":
    main()
