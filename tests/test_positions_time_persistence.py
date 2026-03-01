"""
Tests to verify positions as-of times persist on refresh.

These tests cover the Positions section "Valid time as-of" and "System time as-of"
inputs and ensure that clicking Refresh does not reset user selections.
"""
import os
import socket
import subprocess
import sys
import time
import urllib.request

import pytest
from playwright.sync_api import sync_playwright, Page


def _is_port_open(host: str, port: int) -> bool:
    """Return True when a TCP listener is available on the given host/port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def _wait_for_http(url: str, timeout_seconds: int = 30) -> None:
    """Wait until an HTTP endpoint responds successfully or timeout."""
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None

    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2):
                return
        except Exception as exc:
            last_error = exc
            time.sleep(0.5)

    raise RuntimeError(f"Timed out waiting for {url}: {last_error}")


@pytest.fixture(scope="module")
def app_server():
    """Ensure the Citus app is reachable for browser tests."""
    host = "127.0.0.1"
    port = 8000
    base_url = f"http://{host}:{port}"

    if _is_port_open(host, port):
        _wait_for_http(f"{base_url}/docs")
        yield base_url
        return

    env = os.environ.copy()
    env["PYTHONPATH"] = "."

    subprocess.run([sys.executable, "scripts/init_db.py"], check=True, env=env)
    subprocess.run([sys.executable, "scripts/book_sample.py"], check=True, env=env)

    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app_citus.main:app",
            "--host",
            host,
            "--port",
            str(port),
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        _wait_for_http(f"{base_url}/docs")
        yield base_url
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()


@pytest.fixture
def page(app_server: str):
    """Launch a headless browser and navigate to the app."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        page.goto(app_server)
        page.wait_for_load_state("networkidle")
        yield page
        browser.close()


def test_valid_time_persists_on_refresh(page: Page):
    """
    Valid time as-of should persist when clicking Refresh.
    """
    # Select a book
    page.select_option("#positionsBookId", "ALPHA_TRADING")

    # Set Valid time as-of to a specific past date/time
    past_time = "2026-02-20T15:30"  # 1 week ago, 3:30 PM
    valid_time_input = page.locator("#positionsValidTime")
    valid_time_input.fill(past_time)

    # Verify the time was set
    assert valid_time_input.input_value() == past_time, "Valid time should be set to past time"

    # Click the Refresh button
    page.click("#refreshBookViews")

    # Wait for the refresh to complete
    page.wait_for_timeout(1000)

    # Valid time should remain unchanged
    current_value = valid_time_input.input_value()
    assert current_value == past_time, f"Valid time should persist (expected: {past_time}, got: {current_value})"


def test_system_time_persists_on_refresh(page: Page):
    """
    System time as-of should persist when clicking Refresh.
    """
    # Select a book
    page.select_option("#positionsBookId", "ALPHA_TRADING")

    # Set System time as-of to a specific past date/time
    past_time = "2026-02-19T10:00"  # 1 week ago, 10:00 AM
    system_time_input = page.locator("#positionsSystemTime")
    system_time_input.fill(past_time)

    # Verify the time was set
    assert system_time_input.input_value() == past_time, "System time should be set to past time"

    # Click the Refresh button
    page.click("#refreshBookViews")

    # Wait for the refresh to complete
    page.wait_for_timeout(1000)

    # System time should remain unchanged
    current_value = system_time_input.input_value()
    assert current_value == past_time, f"System time should persist (expected: {past_time}, got: {current_value})"


def test_both_times_persist_on_refresh(page: Page):
    """
    Both Valid time and System time should persist when clicking Refresh.
    """
    # Select a book
    page.select_option("#positionsBookId", "ALPHA_TRADING")

    # Set both times to specific past values
    valid_past_time = "2026-02-20T15:30"
    system_past_time = "2026-02-19T10:00"

    valid_time_input = page.locator("#positionsValidTime")
    system_time_input = page.locator("#positionsSystemTime")

    valid_time_input.fill(valid_past_time)
    system_time_input.fill(system_past_time)

    # Verify both times were set
    assert valid_time_input.input_value() == valid_past_time
    assert system_time_input.input_value() == system_past_time

    # Click the Refresh button
    page.click("#refreshBookViews")

    # Wait for the refresh to complete
    page.wait_for_timeout(1000)

    # Both times should remain unchanged
    current_valid = valid_time_input.input_value()
    current_system = system_time_input.input_value()
    assert current_valid == valid_past_time, f"Valid time should persist (expected: {valid_past_time}, got: {current_valid})"
    assert current_system == system_past_time, f"System time should persist (expected: {system_past_time}, got: {current_system})"


def test_multiple_refreshes_keep_persisting(page: Page):
    """
    Multiple refreshes should not reset times.
    """
    page.select_option("#positionsBookId", "ALPHA_TRADING")
    valid_time_input = page.locator("#positionsValidTime")

    for attempt in range(3):
        # Set a time
        past_time = f"2026-02-{20-attempt}T15:30"
        valid_time_input.fill(past_time)

        # Verify it's set
        assert valid_time_input.input_value() == past_time

        # Click refresh
        page.click("#refreshBookViews")
        page.wait_for_timeout(500)

        # Time should persist
        assert valid_time_input.input_value() == past_time, f"Attempt {attempt+1} - time should persist"


def test_query_parameters_when_times_blank(page: Page):
    """
    Verify that when times are blank, the API queries use current/latest time.
    This is the EXPECTED behavior when times are blank.
    """
    # Select a book
    page.select_option("#positionsBookId", "ALPHA_TRADING")

    # Leave both times blank
    valid_time_input = page.locator("#positionsValidTime")
    system_time_input = page.locator("#positionsSystemTime")

    assert valid_time_input.input_value() == ""
    assert system_time_input.input_value() == ""

    # Setup network listener
    requests = []
    page.on("request", lambda request: requests.append(request.url))

    # Click refresh
    page.click("#refreshBookViews")
    page.wait_for_timeout(1000)

    # Find positions API request
    positions_requests = [r for r in requests if "/positions/ALPHA_TRADING" in r]
    assert len(positions_requests) > 0, "Should have made positions API request"

    # When times are blank, no query parameters should be added (meaning use latest)
    positions_url = positions_requests[0]
    print(f"Positions request URL: {positions_url}")

    # This is correct behavior - blank times mean "latest"
    # The URL should NOT have valid_time or system_time parameters
    assert "valid_time=" not in positions_url, "Blank times should not add valid_time parameter"
    assert "system_time=" not in positions_url, "Blank times should not add system_time parameter"


if __name__ == "__main__":
    print("Running positions as-of time persistence tests...")
    print("=" * 70)
    pytest.main([__file__, "-v", "-s"])
