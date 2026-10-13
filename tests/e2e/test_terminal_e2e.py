"""E2E (Playwright) cho thanh lenh, phim tat va bang du lieu.

Chay khi co dev server (Next + FastAPI), vd:
    E2E_BASE_URL=http://localhost:3100 python -m pytest tests/e2e -q
Khong dat E2E_BASE_URL -> bo qua (pytest thuong khong can trinh duyet).
"""
from __future__ import annotations

import os
import re

import pytest

BASE = os.getenv("E2E_BASE_URL", "").rstrip("/")
pytestmark = pytest.mark.skipif(not BASE, reason="đặt E2E_BASE_URL để chạy e2e")
sync_api = pytest.importorskip("playwright.sync_api")


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture
def page(browser):
    ctx = browser.new_context(viewport={"width": 1366, "height": 900}, accept_downloads=True)
    pg = ctx.new_page()
    pg.set_default_timeout(60_000)
    yield pg
    ctx.close()


def _open_bar(page, how="/"):
    page.locator("body").click(position={"x": 5, "y": 300})
    if how == "/":
        page.keyboard.press("/")
    else:
        page.keyboard.press("Control+k")
    box = page.get_by_test_id("command-input")
    box.wait_for()
    return box


def _wait_symbols(page):
    page.get_by_text("Tất cả").first.wait_for()
    page.wait_for_function("() => !document.body.innerText.includes('Tất cả 0')")


def test_command_bar_runs_ticker_command_and_remembers_it(page):
    page.goto(f"{BASE}/")
    box = _open_bar(page)
    _wait_symbols(page)
    box.fill("fpt fa")
    row = page.get_by_test_id("command-row")
    row.wait_for()
    assert "Báo cáo tài chính" in row.inner_text()
    box.press("Enter")
    page.wait_for_url("**/stock/FPT?tab=bctc")
    page.locator('[role="tab"][data-tab="bctc"][aria-selected="true"]').wait_for()
    box = _open_bar(page, "ctrl")
    history = page.get_by_test_id("command-history")
    history.wait_for()
    assert "FPT FA" in history.inner_text()


def test_command_bar_suggests_on_typo_and_autocompletes(page):
    page.goto(f"{BASE}/")
    box = _open_bar(page)
    _wait_symbols(page)
    box.fill("FPT FAA")
    err = page.get_by_test_id("command-error")
    err.wait_for()
    assert "FPT FA" in err.inner_text()
    box.fill("MAC")
    box.press("Tab")
    assert box.input_value().strip() == "MACRO"
    box.press("Enter")
    page.wait_for_url("**/vi-mo")


def test_compare_command_opens_compare_page(page):
    page.goto(f"{BASE}/")
    box = _open_bar(page)
    _wait_symbols(page)
    box.fill("CMP FPT HPG")
    page.get_by_test_id("command-row").wait_for()
    box.press("Enter")
    page.wait_for_url("**/so-sanh?ma=FPT,HPG")
    page.get_by_role("cell", name="HPG").first.wait_for()


def test_shortcuts_navigate_and_help(page):
    page.goto(f"{BASE}/")
    page.locator("body").click(position={"x": 5, "y": 300})
    page.keyboard.press("?")
    page.get_by_test_id("shortcuts-help").wait_for()
    page.keyboard.press("Escape")
    page.get_by_test_id("shortcuts-help").wait_for(state="detached")
    page.keyboard.press("g")
    page.keyboard.press("v")
    page.wait_for_url("**/vi-mo")


def test_shortcuts_ignored_while_typing(page):
    page.goto(f"{BASE}/vi-mo")
    box = _open_bar(page)
    box.type("gn")                                   # dang go: khong chuyen sang /nganh
    page.wait_for_timeout(500)
    assert page.url.endswith("/vi-mo") and box.input_value() == "gn"


def test_number_keys_switch_stock_tabs(page):
    page.goto(f"{BASE}/stock/FPT")
    page.locator('[role="tab"][data-tab="overview"][aria-selected="true"]').wait_for()
    page.locator("body").click(position={"x": 5, "y": 300})
    page.keyboard.press("4")
    page.locator('[role="tab"][data-tab="bctc"][aria-selected="true"]').wait_for()
    assert "tab=bctc" in page.url


def test_data_table_sort_filter_hide_persist_virtualize_csv(page):
    page.goto(f"{BASE}/nganh/1-cong-nghiep")                 # 549 ma -> bang ao hoa (> 500 dong)
    dt = page.locator(".dt", has=page.get_by_text("549 dòng")).first
    dt.wait_for()
    table = dt.locator("table.dt-table")
    rendered = table.locator("tbody tr:not([aria-hidden])").count()
    assert 0 < rendered < 200                                 # chi ve phan nhin thay
    headers = table.locator("thead tr").first.locator("th")
    second, third = headers.nth(1), headers.nth(2)
    second.locator("button").first.click()
    assert second.get_attribute("aria-sort") in ("descending", "ascending")
    third.locator("button").first.click(modifiers=["Shift"])
    assert third.get_attribute("aria-sort") and second.get_attribute("aria-sort")   # sap xep 2 cot
    symbol = table.locator("tbody tr:not([aria-hidden])").first.locator("td").first.inner_text().strip()
    dt.get_by_role("button", name="Lọc theo cột").click()
    first_label = headers.nth(0).locator("button").first.inner_text().strip(" ▲▼")
    dt.get_by_label(f"Lọc {first_label}").fill(symbol)
    dt.get_by_role("toolbar").get_by_text("1/549 dòng").wait_for()      # loc theo cot ma
    dt.get_by_label(f"Lọc {first_label}").fill("")
    col_name = re.sub(r"[\s▲▼\d]+$", "", third.locator("button").first.inner_text())   # bo mui ten + hang sap xep
    dt.get_by_role("button", name="Cột ▾").click()
    dt.get_by_role("menu").get_by_role("checkbox", name=col_name, exact=True).uncheck()
    with page.expect_download() as dl:
        dt.get_by_role("button", name="Xuất CSV").click()
    assert dl.value.suggested_filename.endswith(".csv")
    page.reload()
    dt = page.locator(".dt", has=page.get_by_text("549 dòng")).first
    dt.wait_for()
    head_text = dt.locator("table.dt-table thead tr").first.inner_text()
    assert col_name not in head_text                           # cau hinh cot duoc luu
