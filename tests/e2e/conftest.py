"""Pytest configuration, custom markers, Streamlit subprocess & Playwright fixtures.

All heavy third-party imports (`pandas`, `streamlit`, `playwright`, `unidata`) are
kept lazy inside functions/fixtures so `pytest tests/e2e --collect-only` works
even before all runtime packages or M2/M3 modules are provisioned.
"""

from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from typing import Iterator
import urllib.error
import urllib.request

import pytest

E2E_DIR: Path = Path(__file__).resolve().parent
REPO_ROOT: Path = E2E_DIR.parents[1]
SRC_DIR: Path = REPO_ROOT / "src"
PRIMARY_FIXTURE_DIR: Path = E2E_DIR / "fixtures" / "primary"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def pytest_configure(config: pytest.Config) -> None:
    """Register E2E markers without touching root pyproject.toml / pytest.ini."""
    markers = [
        "e2e: Opaque-box end-to-end tests under tests/e2e/",
        "ui: Live Streamlit HTTP + Playwright browser UI tests",
        "deliverable: Phase 7 live deliverable checks (README, presentation, zip)",
        "m4_deliverable: Live workspace checks for M4 artifacts (README.md, presentation/)",
        "m6_release_gate: Live workspace checks for M6 artifact (zip + release parity)",
    ]
    for marker in markers:
        config.addinivalue_line("markers", marker)


def find_free_port() -> int:
    """Return an available ephemeral TCP port on 127.0.0.1."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        return int(sock.getsockname()[1])


def detect_browser_executable() -> str | None:
    """Detect locally installed Chrome or Edge executable on Windows."""
    candidates = [
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    ]
    for cand in candidates:
        if cand.is_file():
            return str(cand)
    return None


def _terminate_process_tree(proc: subprocess.Popen[str]) -> None:
    """Cleanly terminate a subprocess and its process tree on Windows or POSIX."""
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True,
                check=False,
            )
        else:
            proc.kill()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass


@contextmanager
def launch_streamlit_app(
    data_dir: Path,
    *,
    app_root: Path | None = None,
    startup_timeout: float = 40.0,
) -> Iterator[tuple[str, subprocess.Popen[str]]]:
    """Launch Streamlit headless on a free port with `UNIDATA_DATA_DIR` set."""
    root = app_root or REPO_ROOT
    app_file = root / "app.py"
    if not app_file.is_file():
        raise AssertionError(f"Missing Streamlit entry point: {app_file}")

    port = find_free_port()
    base_url = f"http://127.0.0.1:{port}"
    health_url = f"{base_url}/_stcore/health"

    env = os.environ.copy()
    env["UNIDATA_DATA_DIR"] = str(data_dir)
    env["STREAMLIT_SERVER_HEADLESS"] = "true"
    env["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
    env["PYTHONUTF8"] = "1"

    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(app_file),
            "--server.port",
            str(port),
            "--server.address",
            "127.0.0.1",
            "--server.headless",
            "true",
            "--browser.gatherUsageStats",
            "false",
        ],
        cwd=str(root),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=creationflags,
    )

    try:
        deadline = time.monotonic() + startup_timeout
        last_err: str = "no response"
        while time.monotonic() < deadline:
            exit_code = proc.poll()
            if exit_code is not None:
                output = proc.stdout.read() if proc.stdout else ""
                raise AssertionError(
                    f"Streamlit exited prematurely (code={exit_code}):\n{output}"
                )
            try:
                with urllib.request.urlopen(health_url, timeout=2.0) as resp:
                    if resp.status == 200:
                        break
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_err = str(exc)
            time.sleep(0.4)
        else:
            raise AssertionError(
                f"Streamlit health check timed out after {startup_timeout}s at {health_url} ({last_err})"
            )

        yield base_url, proc
    finally:
        _terminate_process_tree(proc)
        if proc.stdout is not None:
            try:
                proc.stdout.close()
            except OSError:
                pass


@contextmanager
def open_playwright_page(
    *,
    viewport: tuple[int, int] = (1440, 900),
    reduced_motion: str = "no-preference",
    offline: bool = False,
):
    """Open a headless Playwright browser page with auto-detected Chrome/Chromium."""
    from playwright.sync_api import sync_playwright

    exe_path = detect_browser_executable()
    with sync_playwright() as p:
        launch_kwargs: dict[str, object] = {"headless": True}
        if exe_path is not None:
            launch_kwargs["executable_path"] = exe_path
        browser = p.chromium.launch(**launch_kwargs)
        context = browser.new_context(
            viewport={"width": viewport[0], "height": viewport[1]},
            reduced_motion=reduced_motion,
            offline=offline,
        )
        page = context.new_page()
        console_errors: list[str] = []
        page_errors: list[str] = []
        page.on(
            "console",
            lambda msg: console_errors.append(msg.text)
            if msg.type == "error"
            else None,
        )
        page.on("pageerror", lambda err: page_errors.append(str(err)))
        try:
            yield page, console_errors, page_errors
        finally:
            context.close()
            browser.close()


def wait_for_streamlit_ready(page, timeout_ms: int = 25000) -> str:
    """Wait for Streamlit main container to finish rendering and return visible text."""
    page.wait_for_selector('[data-testid="stAppViewContainer"]', timeout=timeout_ms)
    # Wait briefly for any initial status/running indicator to clear
    deadline = time.monotonic() + (timeout_ms / 1000.0)
    previous_main = None
    while time.monotonic() < deadline:
        running = page.locator('[data-testid="stStatusWidget"]').count()
        # The toolbar ("Skip to main content", "Deploy") is rendered before the script runs, so
        # readiness is judged on the main block: it must have real content and be stable.
        main_loc = page.locator('[data-testid="stMain"]')
        if main_loc.count() == 0:
            main_loc = page.locator('[data-testid="stAppViewContainer"]')
        main_text = main_loc.first.inner_text().strip()
        if running == 0 and len(main_text) > 40 and main_text == previous_main:
            # Give Plotly charts a brief moment to paint SVG
            page.wait_for_timeout(400)
            return page.locator('[data-testid="stAppViewContainer"]').inner_text()
        previous_main = main_text
        page.wait_for_timeout(300)
    return page.locator('[data-testid="stAppViewContainer"]').inner_text()


def normalize_brl_spaces(text: str) -> str:
    """Normalize NBSP / thin spaces in rendered BRL strings to ASCII space."""
    return text.replace("\xa0", " ").replace("\u202f", " ")


def apply_temporal_filter(page, target_text: str) -> str:
    """Interact with a Streamlit temporal filter widget (selectbox/radio/slider) without vacuous no-ops."""
    import re

    filter_widgets = page.locator(
        '[data-testid="stSelectbox"], [data-testid="stSlider"], '
        '[data-testid="stSelectSlider"], [data-testid="stRadio"]'
    )
    assert filter_widgets.count() > 0, (
        "Expected at least one Streamlit temporal filter widget "
        "(stSelectbox/stSlider/stSelectSlider/stRadio)"
    )

    # 1. Try selectboxes (only accept an option matching target_text)
    selectboxes = page.locator('[data-testid="stSelectbox"]')
    for idx in range(selectboxes.count()):
        sb = selectboxes.nth(idx)
        sb.click()
        page.wait_for_timeout(200)
        opt = page.locator('[role="option"]', has_text=re.compile(re.escape(target_text), re.I))
        if opt.count() > 0:
            opt.first.click()
            page.wait_for_timeout(700)
            wait_for_streamlit_ready(page)
            return "selectbox"
        page.keyboard.press("Escape")
        page.wait_for_timeout(150)

    # 2. Try radio controls
    radios = page.locator('[data-testid="stRadio"] label', has_text=re.compile(re.escape(target_text), re.I))
    if radios.count() > 0:
        radios.first.click()
        page.wait_for_timeout(700)
        wait_for_streamlit_ready(page)
        return "radio"

    # 3. Try slider / select_slider controls
    sliders = page.locator(
        '[data-testid="stSelectSlider"] [role="slider"], '
        '[data-testid="stSlider"] [role="slider"]'
    )
    if sliders.count() > 0:
        before_text = page.locator('[data-testid="stAppViewContainer"]').inner_text()
        slider = sliders.first
        slider.focus()
        for key in ("ArrowRight", "ArrowRight", "ArrowLeft"):
            page.keyboard.press(key)
            page.wait_for_timeout(500)
            after_text = wait_for_streamlit_ready(page)
            if after_text != before_text:
                return "slider"

    raise AssertionError(
        f"Could not apply temporal filter '{target_text}' via any Streamlit filter widget "
        f"(found {filter_widgets.count()} widget(s))."
    )


def click_reset_filter(page) -> str:
    """Click the UI filter reset button unconditionally and return normalized ready text."""
    import re

    reset_btn = page.locator(
        "button",
        has_text=re.compile(r"limpar|reset|voltar|todos|completo", re.I),
    )
    assert reset_btn.count() > 0, (
        "Expected a visible filter reset button matching Limpar|Reset|Voltar|Todos|Completo"
    )
    reset_btn.first.click()
    page.wait_for_timeout(700)
    return normalize_brl_spaces(wait_for_streamlit_ready(page))


def expand_methodology_section(page) -> str:
    """Expand 'Sobre os dados' / 'Metodologia' / diagnostics containers only if currently collapsed."""
    import re

    details_loc = page.locator("details")
    for idx in range(details_loc.count()):
        det = details_loc.nth(idx)
        if det.get_attribute("open") is None:
            summary = det.locator("summary")
            if summary.count() > 0:
                summary.first.click()
                page.wait_for_timeout(200)

    toggle_btns = page.locator(
        'button[aria-expanded="false"]',
        has_text=re.compile(r"sobre os dados|metodologia|diagn[óo]stic|qualidade", re.I),
    )
    for idx in range(toggle_btns.count()):
        toggle_btns.nth(idx).click()
        page.wait_for_timeout(200)

    return wait_for_streamlit_ready(page)


def try_select_empty_filter_in_ui(page) -> bool:
    """Attempt to select an empty/inverted temporal window via UI controls; return True if triggered."""
    import re

    selectboxes = page.locator('[data-testid="stSelectbox"]')
    temporal_boxes = []
    for idx in range(selectboxes.count()):
        txt = (selectboxes.nth(idx).inner_text() or "").lower()
        if any(k in txt for k in ("2017", "2018", "ano", "mês", "mes", "início", "inicio", "fim", "período", "periodo", "todos")):
            temporal_boxes.append(selectboxes.nth(idx))

    if len(temporal_boxes) >= 2:
        # Try inverted range: start=2018*, end=2017*
        temporal_boxes[0].click()
        page.wait_for_timeout(150)
        opt_start = page.locator('[role="option"]', has_text="2018")
        if opt_start.count() > 0:
            opt_start.first.click()
            page.wait_for_timeout(500)
            temporal_boxes[1].click()
            page.wait_for_timeout(150)
            opt_end = page.locator('[role="option"]', has_text="2017")
            if opt_end.count() > 0:
                opt_end.first.click()
                page.wait_for_timeout(700)
                wait_for_streamlit_ready(page)
                return True
            page.keyboard.press("Escape")
        else:
            page.keyboard.press("Escape")

    # Try selecting an explicit gap month (e.g., 2017-02 / Fev/2017) if listed
    for sb in temporal_boxes:
        sb.click()
        page.wait_for_timeout(150)
        opt_gap = page.locator('[role="option"]', has_text=re.compile(r"2017-02|fev/2017", re.I))
        if opt_gap.count() > 0:
            opt_gap.first.click()
            page.wait_for_timeout(700)
            wait_for_streamlit_ready(page)
            return True
        page.keyboard.press("Escape")

    return False


@pytest.fixture
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture
def primary_dir() -> Path:
    return PRIMARY_FIXTURE_DIR


@pytest.fixture
def streamlit_runner():
    return launch_streamlit_app


@pytest.fixture
def playwright_page():
    return open_playwright_page
