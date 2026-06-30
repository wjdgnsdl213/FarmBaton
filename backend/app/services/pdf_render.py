"""
backend/app/services/pdf_render.py

Jinja2 HTML 템플릿 → Playwright(headless Chromium) → PDF 바이트.
배포 환경(Railway 등 Linux 컨테이너)에 한글 시스템 폰트가 없을 수 있어,
Noto Sans KR(OFL) 파일을 직접 임베드(@font-face)한다 — 시스템 폰트 의존 없음.
"""
from __future__ import annotations

import base64
import functools
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
_FONTS_DIR = Path(__file__).resolve().parent.parent / "static" / "fonts"

_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(["html"]),
)


@functools.lru_cache(maxsize=4)
def _font_data_uri(filename: str) -> str:
    """TTF를 base64 data: URI로 변환(1회 캐시).

    set_content는 about:blank 출처라 Chromium이 file:// 폰트 로드를 차단한다.
    data: URI로 인라인하면 외부 로드 없이 Noto Sans KR(OFL)이 그대로 로드·
    임베딩돼, 로컬과 Railway에서 동일하게 동작하고 폰트 없는 PC에서도 깨지지
    않는다.
    """
    raw = (_FONTS_DIR / filename).read_bytes()
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:font/ttf;base64,{b64}"


def render_report_html(context: dict) -> str:
    """report.html 템플릿 렌더. 폰트는 base64 data: URI로 인라인 임베드."""
    template = _env.get_template("report.html")
    ctx = {
        **context,
        "font_regular_uri": _font_data_uri("NotoSansKR-Regular.ttf"),
        "font_bold_uri": _font_data_uri("NotoSansKR-Bold.ttf"),
    }
    return template.render(**ctx)


# 컨테이너(Railway 등) 기본 /dev/shm은 64MB로 작아, 폰트를 base64로 인라인한
# 무거운 HTML을 set_content 할 때 Chromium 렌더러가 메모리 부족으로 죽는다
# ("Page crashed"). --disable-dev-shm-usage 로 공유 메모리를 /tmp 에 쓰게 해
# 크래시를 막고, --no-sandbox 로 root 컨테이너의 sandbox 기동 실패를 피한다.
_LAUNCH_ARGS = ["--no-sandbox", "--disable-dev-shm-usage"]


def _render_once(html: str) -> bytes:
    with sync_playwright() as p:
        browser = p.chromium.launch(args=_LAUNCH_ARGS)
        try:
            page = browser.new_page()
            page.set_content(html, wait_until="load")
            # @font-face(file:// TTF)가 실제로 로드돼 PDF에 임베딩되도록 대기
            page.evaluate("() => document.fonts.ready")
            return page.pdf(
                format="A4",
                print_background=True,
                margin={"top": "0", "bottom": "0", "left": "0", "right": "0"},
            )
        finally:
            browser.close()


def html_to_pdf(html: str) -> bytes:
    """HTML 문자열 → A4 PDF 바이트 (Playwright headless Chromium).

    렌더러가 일시적 메모리 압박 등으로 한 번 죽어도("Page crashed") 데모가
    멈추지 않도록 1회 재시도한다. 두 번째도 실패하면 그대로 예외를 올린다.
    """
    try:
        return _render_once(html)
    except PlaywrightError:
        return _render_once(html)


def render_report_pdf(context: dict) -> bytes:
    return html_to_pdf(render_report_html(context))
