# -*- coding: utf-8 -*-
"""2차 발표 슬라이드(.pptx) 생성 스크립트.

근거 문서: docs/발표_PPT_구성안.md (3절 13장 스펙), docs/발표_대사.md
사용법:  python scripts/build_presentation.py <assets_dir>
  assets_dir 에 slide6@2x.png, slide11@2x.png, arch@2x.png 가 있어야 함
  (docs/*.svg 를 Chrome headless --screenshot 으로 변환)
출력:    docs/발표_슬라이드.pptx
"""
import sys
from pathlib import Path

import qrcode
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from pptx.oxml.ns import qn

# ---- 브랜드 팔레트 ----
CREAM = RGBColor(0xF6, 0xF5, 0xF0)
FOREST = RGBColor(0x15, 0x35, 0x1F)
FOREST_CARD = RGBColor(0x23, 0x4A, 0x30)
GREEN = RGBColor(0x2E, 0x9E, 0x57)
GREEN_DK = RGBColor(0x1F, 0x80, 0x47)
SAGE = RGBColor(0xA8, 0xC6, 0x6C)
SAGE_DK = RGBColor(0x6F, 0x8F, 0x3A)
OLIVE = RGBColor(0x7A, 0x8A, 0x66)
OLIVE_DK = RGBColor(0x5A, 0x6A, 0x44)
INK = RGBColor(0x16, 0x24, 0x1B)
MUTED = RGBColor(0x5E, 0x6A, 0x61)
GRAY = RGBColor(0x9A, 0xA4, 0x9B)
BORDER = RGBColor(0xE3, 0xE6, 0xDD)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
PALE = RGBColor(0xCD, 0xD8, 0xCF)
TINT_GREEN = RGBColor(0xE3, 0xF2, 0xE8)
TINT_SAGE = RGBColor(0xF0, 0xF5, 0xE2)
TINT_OLIVE = RGBColor(0xEE, 0xF0, 0xE6)
AMBER = RGBColor(0xB4, 0x53, 0x09)

FONT = "맑은 고딕"
SW, SH = Inches(13.333), Inches(7.5)


def _set_run(run, text, size, bold=False, color=INK, font=FONT):
    run.text = text
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    run.font.name = font
    rPr = run._r.get_or_add_rPr()
    ea = rPr.find(qn("a:ea"))
    if ea is None:
        ea = rPr.makeelement(qn("a:ea"), {})
        rPr.append(ea)
    ea.set("typeface", font)


def text(slide, x, y, w, h, lines, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP,
         line_spacing=1.12, space_after=0):
    """lines: [(text, size, bold, color), ...] 또는 [[(run),(run)], ...] (한 줄 다중 런)."""
    box = slide.shapes.add_textbox(x, y, w, h)
    tf = box.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    for m in ("margin_left", "margin_right", "margin_top", "margin_bottom"):
        setattr(tf, m, 0)
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.line_spacing = line_spacing
        p.space_after = Pt(space_after)
        runs = line if isinstance(line, list) else [line]
        for spec in runs:
            _set_run(p.add_run(), *spec[0:2], **{"bold": spec[2] if len(spec) > 2 else False,
                                                 "color": spec[3] if len(spec) > 3 else INK})
    return box


def rect(slide, x, y, w, h, fill, line=None, line_w=0.75, radius=None):
    shape_type = MSO_SHAPE.ROUNDED_RECTANGLE if radius is not None else MSO_SHAPE.RECTANGLE
    sp = slide.shapes.add_shape(shape_type, x, y, w, h)
    if radius is not None:
        try:
            sp.adjustments[0] = radius
        except Exception:
            pass
    if fill is None:
        sp.fill.background()
    else:
        sp.fill.solid()
        sp.fill.fore_color.rgb = fill
    if line is None:
        sp.line.fill.background()
    else:
        sp.line.color.rgb = line
        sp.line.width = Pt(line_w)
    sp.shadow.inherit = False
    sp.text_frame.paragraphs[0].text = ""
    return sp


def card(slide, x, y, w, h, accent=None):
    c = rect(slide, x, y, w, h, WHITE, BORDER, radius=0.06)
    if accent is not None:
        rect(slide, x + Inches(0.18), y, w - Inches(0.36), Pt(4.5), accent)
    return c


def header(slide, kicker, title, num=None):
    rect(slide, 0, 0, SW, SH, CREAM)
    text(slide, Inches(0.55), Inches(0.38), Inches(12.2), Inches(0.3),
         [(kicker, 12, True, GREEN_DK)])
    text(slide, Inches(0.55), Inches(0.68), Inches(12.2), Inches(0.75),
         [(title, 29, True, FOREST)])
    rect(slide, Inches(0.57), Inches(1.32), Inches(0.85), Pt(3.5), SAGE)
    if num:
        text(slide, Inches(12.35), Inches(7.08), Inches(0.75), Inches(0.3),
             [(num, 10, False, GRAY)], align=PP_ALIGN.RIGHT)
    text(slide, Inches(0.55), Inches(7.08), Inches(3), Inches(0.3),
         [("팜바톤 FarmBaton", 9, True, GRAY)])


def build(assets: Path, out: Path):
    prs = Presentation()
    prs.slide_width, prs.slide_height = SW, SH
    blank = prs.slide_layouts[6]

    def new():
        return prs.slides.add_slide(blank)

    qr_path = assets / "qr.png"
    img = qrcode.make("https://farmbaton.vercel.app", box_size=10, border=1)
    img.save(qr_path)

    # ---------- S1 타이틀 ----------
    s = new()
    rect(s, 0, 0, SW, SH, FOREST)
    text(s, Inches(0.9), Inches(1.15), Inches(11), Inches(0.35),
         [("제11회 농업·농촌 공공데이터+AI 활용 창업경진대회 — 2차 발표", 13, True, SAGE)])
    text(s, Inches(0.9), Inches(1.75), Inches(11.5), Inches(1.4),
         [[("팜바톤 ", 60, True, WHITE), ("FarmBaton", 34, True, SAGE)]])
    text(s, Inches(0.93), Inches(3.1), Inches(11.5), Inches(0.6),
         [("떠나는 농장과 시작하는 청년을 잇다", 24, True, PALE)])
    text(s, Inches(0.93), Inches(3.75), Inches(11.5), Inches(0.4),
         [("고령 농가의 농장(농지·작목·시설·판로)을 청년농에게 잇는 승계 진단·매칭 플랫폼", 14, False, PALE)])
    pill = rect(s, Inches(0.9), Inches(4.6), Inches(6.5), Inches(0.62), FOREST_CARD, radius=0.5)
    text(s, Inches(1.2), Inches(4.72), Inches(6.1), Inches(0.4),
         [[("farmbaton.vercel.app", 16, True, WHITE), ("   — 지금 접속하시면 실제로 동작합니다", 12, False, PALE)]])
    rect(s, Inches(11.05), Inches(4.5), Inches(1.55), Inches(1.55), WHITE, radius=0.08)
    s.shapes.add_picture(str(qr_path), Inches(11.15), Inches(4.6), Inches(1.35), Inches(1.35))
    text(s, Inches(0.93), Inches(6.7), Inches(11.5), Inches(0.35),
         [("팀  김정훈 · 윤채원 · 유수민", 12, False, GRAY)])

    # ---------- S2 문제 ----------
    s = new()
    header(s, "문제 — 주제 시의성", "농장은 멈추는데, 이어받을 통로가 없다", "2")
    stats = [
        ("55.8%", "65세 이상 농가인구 비율", "역대 최고 (처음 55% 돌파)"),
        ("49만 가구", "70세 이상 경영주", "전체 경영주의 과반 (50.8%)"),
        ("4,601가구", "40세 미만 청년 경영주", "12,426 → 4,601 · 4년 만에 1/3, 역대 최저"),
    ]
    for i, (num, lbl, sub) in enumerate(stats):
        x = Inches(0.55 + i * 4.15)
        card(s, x, Inches(1.75), Inches(3.95), Inches(2.9), accent=[OLIVE, GREEN, AMBER][i])
        text(s, x + Inches(0.35), Inches(2.35), Inches(3.3), Inches(1.0),
             [(num, 44, True, FOREST)])
        text(s, x + Inches(0.35), Inches(3.45), Inches(3.3), Inches(0.9),
             [(lbl, 15, True, INK), (sub, 11.5, False, MUTED)], space_after=4)
    rect(s, Inches(0.55), Inches(5.1), Inches(12.23), Inches(0.85), FOREST, radius=0.12)
    text(s, Inches(0.55), Inches(5.28), Inches(12.23), Inches(0.5),
         [("수십만 농가가 은퇴를 앞두고 있지만 — 청년농과 만날 통로가 없습니다", 17, True, WHITE)],
         align=PP_ALIGN.CENTER)
    text(s, Inches(0.55), Inches(6.25), Inches(12.2), Inches(0.3),
         [("출처: 통계청 2024 농림어업조사", 10, False, GRAY)])

    # ---------- S3 / S9 공용 비교표 ----------
    def comparison(slide, filled):
        rows, cols = 5, 5
        top, left = Inches(1.7), Inches(0.55)
        gf = slide.shapes.add_table(rows, cols, left, top, Inches(12.23), Inches(4.0))
        tbl = gf.table
        tbl.first_row = False
        tbl.horz_banding = False
        widths = [1.9, 2.45, 2.45, 2.45, 2.98]
        for i, wv in enumerate(widths):
            tbl.columns[i].width = Inches(wv)
        heads = ["", "감정평가·중개", "부동산 플랫폼", "농지은행", "팜바톤"]
        data = [
            ("평가 대상", "토지·건물", "토지·건물(범용)", "농지만",
             "농장 전체\n(농지+작목+시설+판로)"),
            ("가치 산정", "감정평가\n(수십만 원·수일)", "실거래 조회·AVM", "공시지가·호가 수준",
             "공공데이터 결정론 산식\n즉시·무료 + 신뢰등급"),
            ("승계 매칭", "✕", "✕", "농지 한정 제도",
             "6요인 양면 매칭\n(자본·정책자금 반영)"),
            ("당사자 연결", "대면·전화", "매물 게시형", "매물 게시형",
             "인앱 상담 → 채팅"),
        ]
        for c in range(cols):
            cell = tbl.cell(0, c)
            cell.fill.solid()
            cell.fill.fore_color.rgb = FOREST if c < 4 else (GREEN_DK if filled else BORDER)
            tf = cell.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            p.alignment = PP_ALIGN.CENTER
            _set_run(p.add_run(), heads[c], 13.5, True,
                     WHITE if (c < 4 or filled) else MUTED)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
        for r in range(1, rows):
            for c in range(cols):
                cell = tbl.cell(r, c)
                cell.fill.solid()
                if c == 0:
                    cell.fill.fore_color.rgb = TINT_OLIVE
                elif c == 4:
                    cell.fill.fore_color.rgb = TINT_GREEN if filled else RGBColor(0xEF, 0xEF, 0xEC)
                else:
                    cell.fill.fore_color.rgb = WHITE
                tf = cell.text_frame
                tf.word_wrap = True
                cell.vertical_anchor = MSO_ANCHOR.MIDDLE
                cell.margin_left = Inches(0.1)
                cell.margin_right = Inches(0.1)
                val = data[r - 1][c] if c < 4 else (data[r - 1][4] if filled else "?")
                for j, seg in enumerate(val.split("\n")):
                    p = tf.paragraphs[0] if j == 0 else tf.add_paragraph()
                    p.alignment = PP_ALIGN.CENTER if c > 0 else PP_ALIGN.LEFT
                    p.line_spacing = 1.05
                    if c == 0:
                        _set_run(p.add_run(), seg, 12.5, True, OLIVE_DK)
                    elif c == 4:
                        _set_run(p.add_run(), seg, 12 if filled else 20,
                                 True, GREEN_DK if filled else GRAY)
                    else:
                        _set_run(p.add_run(), seg, 12, False, MUTED)

    # S3
    s = new()
    header(s, "기존 대안의 공백", "기존 수단은 '농장'을 통째로 다루지 못한다", "3")
    comparison(s, filled=False)
    text(s, Inches(0.55), Inches(6.1), Inches(12.23), Inches(0.6),
         [[("농장 = 농지 + 작목 + 시설 + 판로", 16, True, FOREST),
           ("  — 이 전체를 평가하고 연결하는 통로가 비어 있습니다", 14, False, MUTED)]],
         align=PP_ALIGN.CENTER)

    # ---------- S4 솔루션 ----------
    s = new()
    header(s, "솔루션", "주소 하나로 시작하는 양면 플랫폼", "4")
    card(s, Inches(0.7), Inches(2.15), Inches(3.4), Inches(2.5), accent=OLIVE)
    text(s, Inches(1.0), Inches(2.55), Inches(2.8), Inches(1.9),
         [("농장주", 20, True, OLIVE_DK), ("", 6), ("주소만 입력", 14, True, INK),
          ("→ 인수 검토가 범위(참고용 추정)\n→ 관점별 AI 리포트(PDF)", 12, False, MUTED)],
         space_after=6)
    card(s, Inches(9.25), Inches(2.15), Inches(3.4), Inches(2.5), accent=SAGE)
    text(s, Inches(9.55), Inches(2.55), Inches(2.8), Inches(1.9),
         [("청년농", 20, True, SAGE_DK), ("", 6), ("희망 조건만 입력", 14, True, INK),
          ("→ 승계 가능 농장 점수순 추천\n→ 지원사업·상담·채팅", 12, False, MUTED)],
         space_after=6)
    rect(s, Inches(4.85), Inches(2.15), Inches(3.65), Inches(2.5), FOREST, radius=0.08)
    text(s, Inches(5.1), Inches(2.6), Inches(3.15), Inches(1.8),
         [("팜바톤", 22, True, WHITE), ("", 6),
          ("진단 엔진  ·  매칭 엔진", 14, True, SAGE),
          ("공공데이터 7종 결합", 12, False, PALE)], align=PP_ALIGN.CENTER, space_after=6)
    for x, flip in ((Inches(4.18), False), (Inches(8.58), True)):
        ar = s.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW if not flip else MSO_SHAPE.LEFT_ARROW,
                                x, Inches(3.18), Inches(0.6), Inches(0.42))
        ar.fill.solid(); ar.fill.fore_color.rgb = GRAY; ar.line.fill.background()
        ar.shadow.inherit = False
    for i, t in enumerate(["①  농가 등록 → 인수 검토 리포트", "②  청년농 프로필 → 매칭 리스트"]):
        x = Inches(2.1 + i * 4.8)
        rect(s, x, Inches(5.35), Inches(4.35), Inches(0.62), TINT_GREEN, radius=0.5)
        text(s, x, Inches(5.49), Inches(4.35), Inches(0.4),
             [(t, 13.5, True, GREEN_DK)], align=PP_ALIGN.CENTER)
    text(s, Inches(0.55), Inches(6.35), Inches(12.23), Inches(0.4),
         [("기능은 이 두 개가 전부입니다 — 직접 보여드리겠습니다", 14, False, MUTED)],
         align=PP_ALIGN.CENTER)

    # ---------- S5 데모 ----------
    s = new()
    header(s, "라이브 데모", "설명 대신, 직접 보여드리겠습니다", "5")
    steps = [("1", "주소 입력", "팜맵 필지 면적\n자동 취득"),
             ("2", "검토 리포트", "인수 검토가 범위\n+ 신뢰등급"),
             ("3", "청년농 매칭", "6요인 100점\n점수순 추천"),
             ("4", "상담 · 채팅", "수락 시 인앱\n양방향 대화")]
    for i, (n, t, d) in enumerate(steps):
        x = Inches(0.75 + i * 3.15)
        card(s, x, Inches(2.35), Inches(2.6), Inches(2.6))
        circ = s.shapes.add_shape(MSO_SHAPE.OVAL, x + Inches(1.02), Inches(2.7), Inches(0.56), Inches(0.56))
        circ.fill.solid(); circ.fill.fore_color.rgb = GREEN; circ.line.fill.background()
        circ.shadow.inherit = False
        tf = circ.text_frame; p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
        _set_run(p.add_run(), n, 18, True, WHITE)
        text(s, x + Inches(0.15), Inches(3.45), Inches(2.3), Inches(0.45),
             [(t, 17, True, FOREST)], align=PP_ALIGN.CENTER)
        text(s, x + Inches(0.15), Inches(3.95), Inches(2.3), Inches(0.8),
             [(d, 11.5, False, MUTED)], align=PP_ALIGN.CENTER)
        if i < 3:
            ar = s.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, x + Inches(2.66), Inches(3.4),
                                    Inches(0.44), Inches(0.34))
            ar.fill.solid(); ar.fill.fore_color.rgb = SAGE; ar.line.fill.background()
            ar.shadow.inherit = False
    rect(s, Inches(3.2), Inches(5.65), Inches(6.9), Inches(0.62), FOREST, radius=0.5)
    text(s, Inches(3.2), Inches(5.79), Inches(6.9), Inches(0.4),
         [[("farmbaton.vercel.app", 15, True, WHITE), ("  · 실서비스 라이브 (백업 영상 준비)", 11.5, False, PALE)]],
         align=PP_ALIGN.CENTER)

    # ---------- S6 공공데이터 (풀블리드) ----------
    s = new()
    s.shapes.add_picture(str(assets / "slide6@2x.png"), 0, 0, SW, SH)

    # ---------- S7 AI ----------
    s = new()
    header(s, "AI 활용", "숫자는 알고리즘, 설명은 AI", "7")
    card(s, Inches(0.7), Inches(1.85), Inches(5.75), Inches(3.5), accent=GREEN)
    text(s, Inches(1.05), Inches(2.25), Inches(5.05), Inches(2.9),
         [("결정론 엔진 — 금액·점수", 18, True, GREEN_DK), ("", 8),
          ("금액 계산에 LLM을 쓰지 않습니다", 14, True, INK),
          ("· 100% 결정론 Python 산식 (pytest 55개로 고정)", 12.5, False, MUTED),
          ("· 같은 입력 → 같은 결과 · 추적·검증 가능", 12.5, False, MUTED),
          ("· 환각으로 인한 금액 오류 원천 차단", 12.5, False, MUTED)], space_after=7)
    card(s, Inches(6.85), Inches(1.85), Inches(5.75), Inches(3.5), accent=SAGE)
    text(s, Inches(7.2), Inches(2.25), Inches(5.05), Inches(2.9),
         [("생성형 AI — 설명 전담", 18, True, SAGE_DK), ("", 8),
          ("같은 수치를 관점별 언어로 번역합니다", 14, True, INK),
          ("· 농장주: 매도 준비·시설 가치 관점", 12.5, False, MUTED),
          ("· 청년농: 인수 자금·정책자금·체크리스트 관점", 12.5, False, MUTED),
          ("· 농장 수 × 관점 수 — 사람이 못 쓰는 규모의 개인화", 12.5, False, MUTED)], space_after=7)
    rect(s, Inches(0.7), Inches(5.75), Inches(11.9), Inches(0.85), FOREST, radius=0.12)
    text(s, Inches(0.7), Inches(5.95), Inches(11.9), Inches(0.5),
         [("“AI를 어디에 안 썼는지가 저희의 설계입니다”", 18, True, WHITE)],
         align=PP_ALIGN.CENTER)

    # ---------- S8 기술 ----------
    s = new()
    header(s, "기술성 · 완성도", "시제품이 아니라, 운영 중인 서비스", "8")
    pic_w = Inches(7.1)
    pic_h = Emu(int(pic_w * 664 / 1000))
    s.shapes.add_picture(str(assets / "arch@2x.png"), Inches(0.55), Inches(1.75), pic_w, pic_h)
    badges = [("pytest 55개 통과", "산식은 formula.md 예시 케이스로 TDD"),
              ("신뢰등급 A~D", "자료를 낼수록 정밀해지는 단계적 평가"),
              ("전 외부 API 정적 폴백", "데모가 죽지 않는 신뢰성 설계"),
              ("V-World 차단 → 국내 프록시", "공공데이터 국외반출 제약 실전 해결")]
    for i, (t, d) in enumerate(badges):
        y = Inches(1.75 + i * 1.18)
        card(s, Inches(7.95), y, Inches(4.85), Inches(1.0))
        text(s, Inches(8.25), y + Inches(0.14), Inches(4.3), Inches(0.75),
             [(t, 14.5, True, FOREST), (d, 11, False, MUTED)], space_after=3)
    text(s, Inches(0.55), Inches(6.6), Inches(12.2), Inches(0.35),
         [("Vercel · Railway · Supabase(PostGIS) — production 운영 중 · farmbaton.vercel.app", 11.5, False, GRAY)])

    # ---------- S9 독창성 ----------
    s = new()
    header(s, "독창성", "국내에 없던 '승계 특화' 가치평가", "9")
    comparison(s, filled=True)
    text(s, Inches(0.55), Inches(6.0), Inches(12.23), Inches(0.8),
         [[("수령계수 × 시설 잔존가 × 영업권의 결합", 15, True, FOREST),
           (" + 평가→매칭 파이프라인 — 확인된 범위에서 유사 사례를 찾지 못했습니다", 13, False, MUTED)]],
         align=PP_ALIGN.CENTER)

    # ---------- S10 시장 ----------
    s = new()
    header(s, "발전 가능성 — 시장", "49만 가구가 기다리는 시장", "10")
    funnel = [(Inches(6.2), FOREST, WHITE, "후계 연결이 필요한 70세 이상 경영주", "49만 가구"),
              (Inches(4.9), GREEN, WHITE, "충북·경북·충남 · 과수 3작목 (시작점)", "3개 도 48개 시군"),
              (Inches(3.6), SAGE, FOREST, "초기 타깃 — 승계 희망 등록 농가", "MVP 검증")]
    for i, (w, fill, tc, lbl, val) in enumerate(funnel):
        x = Inches(0.7) + (Inches(6.2) - w) / 2
        y = Inches(1.95 + i * 1.35)
        rect(s, x, y, w, Inches(1.1), fill, radius=0.14)
        text(s, x, y + Inches(0.16), w, Inches(0.8),
             [(val, 17, True, tc), (lbl, 11, False, tc)], align=PP_ALIGN.CENTER, space_after=3)
    card(s, Inches(7.5), Inches(1.95), Inches(5.3), Inches(4.05))
    text(s, Inches(7.85), Inches(2.3), Inches(4.6), Inches(3.5),
         [("승계 검토의 진입장벽", 16, True, FOREST), ("", 8),
          ("지금:  감정평가 수십만 원 · 수일", 14, False, MUTED),
          ("", 4),
          [("팜바톤:  ", 14, True, INK), ("무료 · 수십 초", 22, True, GREEN_DK)],
          ("", 10),
          ("문턱이 낮아지면 검토가 늘고,\n검토 하나하나가 매칭 풀이 됩니다", 13, False, MUTED)],
         space_after=6)

    # ---------- S11 수익 ----------
    s = new()
    header(s, "발전 가능성 — 매출", "매출이 발생하는 경로", "11")
    steps11 = [
        ("1단계 — B2G 지자체 구독", "승계 모니터링 대시보드 (발굴·보고·집행)\n3개 도 48개 시군이 1차 시장", GREEN),
        ("2단계 — 성사 성공보수 · 중개사 멤버십", "거래는 제휴 공인중개사가 수행,\n팜바톤은 플랫폼 연계 대가", OLIVE),
        ("상시 — 정밀 리포트 · 제휴", "실사 연계 A·B등급 리포트(유료) ·\n정책자금·보험·자재 제휴", SAGE),
    ]
    for i, (t, d, ac) in enumerate(steps11):
        y = Inches(1.8 + i * 1.35)
        card(s, Inches(0.55), y, Inches(5.9), Inches(1.18), accent=ac)
        text(s, Inches(0.9), y + Inches(0.16), Inches(5.3), Inches(0.95),
             [(t, 14, True, FOREST), (d, 11, False, MUTED)], space_after=3)
    text(s, Inches(0.55), Inches(5.95), Inches(5.9), Inches(0.5),
         [("개인(농장주·청년농)은 무료 — 매칭 풀이 플랫폼의 생명", 12, True, GREEN_DK)])
    pic_w11 = Inches(6.3)
    pic_h11 = Emu(int(pic_w11 * 9 / 16))
    s.shapes.add_picture(str(assets / "slide11@2x.png"), Inches(6.65), Inches(1.8), pic_w11, pic_h11)
    text(s, Inches(6.65), Inches(1.8) + pic_h11 + Inches(0.08), pic_w11, Inches(0.3),
         [("지자체 구독 대시보드 — 콘셉트 목업(예시 데이터)", 10, False, GRAY)], align=PP_ALIGN.CENTER)
    rect(s, Inches(0.55), Inches(6.32), Inches(12.23), Inches(0.62), FOREST, radius=0.12)
    text(s, Inches(0.55), Inches(6.45), Inches(12.23), Inches(0.4),
         [[("3개 도 과수원 실거래 5,122건 · 중앙값 5,958만 원", 14, True, WHITE),
           ("  — 저희 DB에서 실측한 숫자입니다", 12, False, PALE)]], align=PP_ALIGN.CENTER)

    # ---------- S12 팀 ----------
    s = new()
    header(s, "팀", "개발 + 디자인 + 농업 도메인", "12")
    team = [("김정훈", "대표 · 컴퓨터공학", "기획·풀스택 총괄\n공공데이터 적재 · 가치평가·매칭 엔진 · 배포", FOREST),
            ("윤채원", "컴퓨터공학", "UI/UX 디자인 · 사용성 검토\n모바일 퍼스트 화면 설계", GREEN),
            ("유수민", "농업 계열", "농업 도메인 자문\n승계 현장 이해 · 작목·시설 검증", SAGE)]
    for i, (name, role, desc, ac) in enumerate(team):
        x = Inches(0.7 + i * 4.15)
        card(s, x, Inches(2.1), Inches(3.85), Inches(3.2), accent=ac)
        text(s, x + Inches(0.35), Inches(2.6), Inches(3.15), Inches(2.4),
             [(name, 24, True, FOREST), (role, 13, True, GREEN_DK), ("", 6),
              (desc, 12, False, MUTED)], space_after=5)
    text(s, Inches(0.55), Inches(5.9), Inches(12.23), Inches(0.4),
         [("기술과 농업 현장 이해를 모두 갖춘 상호 보완 3인 팀", 14, False, MUTED)],
         align=PP_ALIGN.CENTER)

    # ---------- S13 클로징 ----------
    s = new()
    rect(s, 0, 0, SW, SH, FOREST)
    text(s, Inches(0.9), Inches(1.9), Inches(11.5), Inches(0.6),
         [("승계 검토의 진입장벽을", 26, True, PALE)])
    text(s, Inches(0.9), Inches(2.6), Inches(11.9), Inches(1.1),
         [[("수일 · 수십만 원", 40, True, WHITE), ("  →  ", 34, True, GRAY),
           ("무료 · 수십 초", 44, True, SAGE)]])
    text(s, Inches(0.93), Inches(4.05), Inches(11.5), Inches(0.5),
         [("사라지던 농장을 데이터로 다음 세대에 잇겠습니다", 18, False, PALE)])
    rect(s, Inches(0.9), Inches(5.0), Inches(5.6), Inches(0.62), FOREST_CARD, radius=0.5)
    text(s, Inches(1.2), Inches(5.12), Inches(5.2), Inches(0.4),
         [[("farmbaton.vercel.app", 16, True, WHITE), ("  — 지금 접속해 보세요", 12, False, PALE)]])
    rect(s, Inches(11.05), Inches(4.85), Inches(1.55), Inches(1.55), WHITE, radius=0.08)
    s.shapes.add_picture(str(qr_path), Inches(11.15), Inches(4.95), Inches(1.35), Inches(1.35))
    text(s, Inches(0.93), Inches(6.6), Inches(11.5), Inches(0.4),
         [("감사합니다 · 팜바톤  김정훈 · 윤채원 · 유수민", 12, False, GRAY)])

    prs.save(out)
    print(f"saved: {out} ({len(prs.slides.__iter__.__self__._sldIdLst)} slides)")


if __name__ == "__main__":
    assets_dir = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    out_path = Path(__file__).resolve().parent.parent / "docs" / "발표_슬라이드.pptx"
    build(assets_dir, out_path)
