"""Download RBI notifications (metadata + full-text HTML) by walking notification IDs backwards.

The PDFs on rbidocs.rbi.org.in sit behind a CAPTCHA, so we keep the notification page's
own HTML body, which carries the same text with <p> paragraphs and real <table>s.

python -m circulariq.scrape --start 13725 --count 300
"""
import argparse
import json
import re
import time
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE = "https://rbi.org.in/Scripts/NotificationUser.aspx?Id={}&Mode=0"
RAW = Path("data/raw")
HEADERS = {"User-Agent": "Mozilla/5.0 (CircularIQ research crawler)"}
DATE_RE = re.compile(r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}")


def parse_body(nid: int, body) -> dict | None:
    """ref / circular number / date / cited notifications from the letter body. None if no date."""
    text = body.get_text("\n", strip=True) if body else ""
    lines = [l.strip() for l in text.split("\n")]
    date = DATE_RE.search(text)
    if not date:
        return None  # "Updated as on" consolidated directions: text lives only in the CAPTCHA'd PDF
    # RBI/2026-27/279, RBI/2026-2027/270, RBI/DCM/2026-27/473, RBI/DoS/2026-27/221
    ref = re.search(r"RBI/(?:[A-Za-z]+/)?\d{4}-\d{2,4}/\d+", text)
    ref = ref.group() if ref else next((l for l in lines if l.startswith("Notification No.")), "")  # FEMA notifications
    dept_no = ""
    if ref.startswith("RBI/"):
        # the line after the RBI/ref is the department's own circular number
        i = next(i for i, l in enumerate(lines) if ref in l)
        if i + 1 < len(lines) and not DATE_RE.fullmatch(lines[i + 1]):
            dept_no = lines[i + 1]
    return {
        "ref": ref,
        "circular_no": dept_no,
        "date": datetime.strptime(date.group(), "%B %d, %Y").date().isoformat(),
        # older notifications this one cites (often the ones it amends)
        "references": sorted({int(m) for m in re.findall(r"NotificationUser\.aspx\?Id=(\d+)", str(body)) if int(m) != nid}),
    }


def parse_page(nid: int, html: str | bytes) -> dict | None:
    """Extract metadata from a NotificationUser page. None if the ID is empty or PDF-only."""
    soup = BeautifulSoup(html, "html.parser")
    title = soup.select_one("td.tableheader[align=center]")  # <b> in raw HTML, <h2> after page JS runs
    pdf = soup.find("a", href=re.compile(r"rdocs/notification/PDFs/.*\.pdf", re.I))
    body = parse_body(nid, soup.select_one("tr.tablecontent2"))
    if not title or not pdf or not body:
        return None
    return {"id": nid, "title": title.get_text(" ", strip=True), **body, "pdf_url": pdf["href"]}


def main(start: int, count: int, delay: float = 0.5):
    (RAW / "html").mkdir(parents=True, exist_ok=True)
    manifest = RAW / "manifest.jsonl"
    done = {json.loads(l)["id"] for l in manifest.open(encoding="utf-8")} if manifest.exists() else set()
    s = requests.Session()
    s.headers.update(HEADERS)
    got, nid = len(done), start
    with manifest.open("a", encoding="utf-8") as out:
        while got < count and nid > 0:
            if nid in done:
                nid -= 1
                continue
            try:
                html = s.get(BASE.format(nid), timeout=30).content
                meta = parse_page(nid, html)
                if meta:
                    body = BeautifulSoup(html, "html.parser").select_one("tr.tablecontent2")
                    (RAW / "html" / f"{nid}.html").write_text(str(body), encoding="utf-8")
                    out.write(json.dumps(meta, ensure_ascii=False) + "\n")
                    out.flush()
                    got += 1
                    print(f"[{got}/{count}] {nid} {meta['date']} {meta['title'][:70]}")
            except requests.RequestException as e:
                print(f"skip {nid}: {e}")
            nid -= 1
            time.sleep(delay)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, default=13725)
    ap.add_argument("--count", type=int, default=300)
    a = ap.parse_args()
    main(a.start, a.count)
