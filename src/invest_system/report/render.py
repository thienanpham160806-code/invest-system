"""HTML -> PDF. Thu lan luot: WeasyPrint -> Playwright (Chromium) -> chi luu HTML.

- WeasyPrint: dep nhat (ho tro @page, so trang, font nhung). Tren Windows can
  GTK runtime (xem README); Linux/macOS cai qua pip la chay.
- Playwright: `pip install playwright && playwright install chromium` - chay
  tot tren Windows, khong can GTK. Chromium khong ho tro @page margin box, nen
  so trang dat qua footer_template.
- Khong co engine nao: luu .html (mo bang trinh duyet -> In -> Luu PDF).
"""
from __future__ import annotations

from pathlib import Path

from ..logging_conf import get_logger

log = get_logger(__name__)


def _weasy(html: str, out: Path) -> Path:
    from weasyprint import HTML  # type: ignore

    HTML(string=html, base_url=str(out.parent)).write_pdf(str(out))
    return out


def _playwright(html: str, out: Path) -> Path:
    from playwright.sync_api import sync_playwright  # type: ignore

    tmp = out.with_suffix(".html")
    tmp.write_text(html, encoding="utf-8")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(tmp.resolve().as_uri(), wait_until="networkidle")
        page.pdf(path=str(out), format="A4", print_background=True,
                 margin={"top": "14mm", "bottom": "16mm", "left": "13mm", "right": "13mm"},
                 display_header_footer=True, header_template="<span></span>",
                 footer_template='<div style="font-size:7px;width:100%;text-align:right;'
                                 'padding-right:13mm;color:#8a94a3">Trang <span class="pageNumber">'
                                 '</span>/<span class="totalPages"></span></div>')
        browser.close()
    return out


def render_pdf(html: str, out: Path, engine: str = "auto") -> Path:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    order = {"auto": ["weasyprint", "playwright"], "weasyprint": ["weasyprint"],
             "playwright": ["playwright"], "html": []}.get(engine, ["weasyprint", "playwright"])
    errors = []
    for name in order:
        try:
            path = (_weasy if name == "weasyprint" else _playwright)(html, out)
            log.info("Da xuat PDF bang %s: %s", name, path)
            return path
        except Exception as exc:  # noqa: BLE001 - ImportError, OSError (thieu GTK)...
            errors.append(f"{name}: {exc}")
            log.warning("Engine %s khong dung duoc: %s", name, exc)
    html_path = out.with_suffix(".html")
    html_path.write_text(html, encoding="utf-8")
    log.warning("Khong xuat duoc PDF (%s) - da luu HTML: %s", "; ".join(errors), html_path)
    return html_path
