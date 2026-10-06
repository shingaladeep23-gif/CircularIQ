"""Record the demo video and README screenshots by driving the real app with Playwright.

Needs the full index (data/index) and a running Ollama.   python scripts/record_demo.py
Writes docs/demo.webm, docs/answer.png, docs/abstain.png, docs/evaluation.png
"""
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
LLM_WAIT = 300_000  # ms; a 3B model on a small GPU can take a while


def start_app() -> tuple[subprocess.Popen, str]:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    proc = subprocess.Popen([sys.executable, "-m", "streamlit", "run", "app.py", "--server.headless=true",
                             f"--server.port={port}", "--browser.gatherUsageStats=false"],
                            cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    for _ in range(120):
        try:
            urllib.request.urlopen(url + "/_stcore/health", timeout=1)
            return proc, url
        except OSError:
            time.sleep(0.5)
    proc.kill()
    raise RuntimeError("streamlit did not start")


def ask(page, example: str):
    page.get_by_role("button", name=example).click()
    page.wait_for_timeout(800)


def main():
    DOCS.mkdir(exist_ok=True)
    proc, url = start_app()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            ctx = browser.new_context(viewport={"width": 1366, "height": 820}, record_video_dir=str(DOCS / "_video"),
                                      record_video_size={"width": 1366, "height": 820})
            page = ctx.new_page()
            page.goto(url)
            expect(page.get_by_text("CircularIQ").first).to_be_visible(timeout=60_000)
            page.wait_for_timeout(1500)

            # 1. a grounded question: answer with a clickable citation, passages with scores
            ask(page, "How long does a commercial bank have to decide whether a red-flagged account is a fraud?")
            expect(page.locator(".st-key-answer")).to_contain_text("RBI/", timeout=LLM_WAIT)
            page.wait_for_timeout(2500)
            page.screenshot(path=str(DOCS / "answer.png"), full_page=False)
            page.mouse.wheel(0, 700)
            page.wait_for_timeout(2500)
            page.mouse.wheel(0, -700)

            # 2. a question the corpus cannot answer: abstention
            ask(page, "What is the current policy repo rate?")
            expect(page.locator(".st-key-answer")).to_contain_text("Not found in the provided circulars", timeout=LLM_WAIT)
            page.wait_for_timeout(2500)
            page.screenshot(path=str(DOCS / "abstain.png"), full_page=False)

            # 3. the evaluation tab
            page.get_by_role("tab", name="Evaluation").click()
            expect(page.locator(".st-key-results")).to_contain_text("Ablation", timeout=30_000)
            page.wait_for_timeout(3000)
            page.screenshot(path=str(DOCS / "evaluation.png"), full_page=False)

            video = page.video.path()
            ctx.close()  # finalises the video file
            browser.close()
        shutil.move(video, DOCS / "demo.webm")
        shutil.rmtree(DOCS / "_video", ignore_errors=True)
        print("wrote docs/demo.webm and screenshots")
    finally:
        proc.terminate()


if __name__ == "__main__":
    main()
