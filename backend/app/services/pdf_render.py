"""
backend/app/services/pdf_render.py

Jinja2 HTML 템플릿 → Playwright(headless Chromium) → PDF 바이트.
배포 환경(Railway 등 Linux 컨테이너)에 한글 시스템 폰트가 없을 수 있어,
Noto Sans KR(OFL) 파일을 직접 임베드(@font-face)한다 — 시스템 폰트 의존 없음.
"""
from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from playwright.sync_api import sync_playwright

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
_FONTS_DIR = Path(__file__).resolve().parent.parent / "static" / "fonts"

_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(["html"]),
)


def render_report_html(context: dict) -> str:
    """report.html 템플릿 렌더. 폰트는 file:// URI로 절대경로 주입."""
    template = _env.get_template("report.html")
    ctx = {
        **context,
        "font_regular_uri": (_FONTS_DIR / "NotoSansKR-Regular.ttf").as_uri(),
        "font_bold_uri": (_FONTS_DIR / "NotoSansKR-Bold.ttf").as_uri(),
    }
    return template.render(**ctx)


def html_to_pdf(html: str) -> bytes:
    """HTML 문자열 → A4 PDF 바이트 (Playwright headless Chromium)."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page()
            page.set_content(html, wait_until="load")
            return page.pdf(
                format="A4",
                print_background=True,
                margin={"top": "0", "bottom": "0", "left": "0", "right": "0"},
            )
        finally:
            browser.close()


def render_report_pdf(context: dict) -> bytes:
    return html_to_pdf(render_report_html(context))
