# tests/browser/conftest.py
"""Playwright fixtures for testing selectors against saved HTML pages."""
import os
import pytest

# Ensure CloakBrowser uses the local workspace cache directory which is writeable
os.environ["CLOAKBROWSER_CACHE_DIR"] = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    ".cloakbrowser"
)

import cloakbrowser

from linkedin.conf import FIXTURE_PAGES_DIR


@pytest.fixture(scope="session")
def browser():
    b = cloakbrowser.launch(headless=True, args=["--disable-gpu", "--disable-setuid-sandbox"])
    yield b
    b.close()


@pytest.fixture
def page(browser):
    p = browser.new_page()
    yield p
    p.close()


def load_fixture(page, *path_parts: str):
    """Load an HTML fixture file into the Playwright page."""
    filepath = FIXTURE_PAGES_DIR / "/".join(path_parts)
    if not filepath.exists():
        pytest.skip(f"Fixture not found: {filepath}")
    page.set_content(filepath.read_text(encoding="utf-8"))
    return page
