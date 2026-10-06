"""Step 1a: notification page -> metadata. Fixtures are real RBI pages saved on 2026-10-06."""
from pathlib import Path

from circulariq.scrape import parse_page

FX = Path(__file__).parent / "fixtures"


def page(name):
    return (FX / name).read_bytes()


def test_parses_ap_dir_circular():
    m = parse_page(13724, page("page_13724.html"))
    assert m["title"] == "Online submission of Form A2: Removal of limits on amount of remittance"
    assert m["ref"] == "RBI/2026-27/279"
    assert m["circular_no"] == "A.P. (DIR Series) Circular No. 23"
    assert m["date"] == "2026-10-01"
    assert m["pdf_url"].lower().endswith(".pdf")


def test_references_capture_amended_circular():
    # the page links A.P. (DIR Series) Circular No. 12 dated July 03, 2024 (Id 12697) twice
    assert parse_page(13724, page("page_13724.html"))["references"] == [12697]


def test_department_prefixed_ref():
    m = parse_page(13723, page("page_13723.html"))
    assert m["ref"] == "RBI/DCM/2026-27/473"
    assert m["circular_no"].startswith("DCM(NPD) No.S2154")
    assert m["date"] == "2026-10-02"
    assert 13723 not in m["references"]


def test_pdf_only_consolidated_direction_is_skipped():
    assert parse_page(13603, page("page_13603_pdf_only.html")) is None


def test_empty_id_is_skipped():
    assert parse_page(1, b"<html><body>No record</body></html>") is None


def test_live_rbi_page_contract(page):
    """Playwright/Chromium: the live RBI page still has the structure the scraper relies on."""
    page.goto("https://rbi.org.in/Scripts/NotificationUser.aspx?Id=13724&Mode=0", wait_until="domcontentloaded", timeout=90_000)
    assert page.get_by_text("Online submission of Form A2: Removal of limits").first.is_visible()
    m = parse_page(13724, page.content())  # parse the DOM exactly as the browser built it
    assert m["ref"] == "RBI/2026-27/279" and m["date"] == "2026-10-01" and m["references"] == [12697]


def test_all_reference_formats():
    from bs4 import BeautifulSoup

    from circulariq.scrape import parse_body

    def body(header):
        return BeautifulSoup(f'<tr class="tablecontent2"><td><p>{header}</p><p>September 24, 2026</p></td></tr>', "html.parser")

    cases = {
        "RBI/2026-27/279<br>A.P. (DIR Series) Circular No. 23": ("RBI/2026-27/279", "A.P. (DIR Series) Circular No. 23"),
        "RBI/2026-2027/270<br>DOR.AML.REC.233/14.06.001/2026-27": ("RBI/2026-2027/270", "DOR.AML.REC.233/14.06.001/2026-27"),
        "RBI/DoS/2026-27/221<br>DoS.CO.PPG.66/11.01.005/2026-27": ("RBI/DoS/2026-27/221", "DoS.CO.PPG.66/11.01.005/2026-27"),
        "RESERVE BANK OF INDIA<br>Notification No. FEMA 23(R)/(1)/2026-RB": ("Notification No. FEMA 23(R)/(1)/2026-RB", ""),
    }
    for header, (ref, no) in cases.items():
        m = parse_body(1, body(header))
        assert (m["ref"], m["circular_no"], m["date"]) == (ref, no, "2026-09-24"), header
