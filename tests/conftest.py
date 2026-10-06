"""Shared fixtures: a small index built from the real fixture circulars, and a live Streamlit server on it."""
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

from circulariq.chunk import chunk_circular

FX = Path(__file__).parent / "fixtures"
ROOT = Path(__file__).parent.parent


@pytest.fixture(scope="session")
def fixture_chunks():
    metas = [json.loads(l) for l in (FX / "manifest.jsonl").read_text(encoding="utf-8").splitlines()]
    return [c for m in metas for c in chunk_circular(m, (FX / f"{m['id']}.html").read_text(encoding="utf-8"))]


@pytest.fixture(scope="session")
def fixture_index(fixture_chunks, tmp_path_factory):
    from circulariq.retrieve import build

    d = tmp_path_factory.mktemp("index")
    build(fixture_chunks, d)
    return d


@pytest.fixture(scope="session")
def retriever(fixture_index):
    from circulariq.retrieve import Retriever

    return Retriever(fixture_index)


@pytest.fixture(scope="session")
def app_url(fixture_index):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = {**os.environ, "CIRCULARIQ_INDEX": str(fixture_index), "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", "app.py", "--server.headless=true",
         f"--server.port={port}", "--browser.gatherUsageStats=false"],
        cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}"
    for _ in range(120):
        try:
            urllib.request.urlopen(url + "/_stcore/health", timeout=1)
            break
        except OSError:
            time.sleep(0.5)
    else:
        proc.kill()
        raise RuntimeError("streamlit did not start")
    yield url
    proc.terminate()
    proc.wait(timeout=10)
