"""
backend/app/services/report_ai.py

AI 설명문 생성 — 결정론적 계산 결과(calc_total_value, calc_match_score)를
자연어로 풀어쓰는 역할만 한다. 숫자는 절대 LLM이 만들지 않고, 이미 계산된
값을 프롬프트에 그대로 주입한다.

Claude API 키가 없거나 호출이 실패하면 결정론적 템플릿 문장으로 즉시
폴백한다 — 외부 API 장애로 데모가 죽지 않게 한다는 CLAUDE.md rule 3 원칙을
LLM 호출에도 동일하게 적용.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass

CROP_NAMES = {"APPLE": "사과", "PEACH": "복숭아", "GRAPE": "포도"}
GRADE_DESC = {
    "A": "실사 기반 추정", "B": "농가 제출자료 기반 추정",
    "C": "사전 검토용 추정", "D": "참고용 자동 추정",
}

MODEL = "claude-haiku-4-5-20251001"


# ── 리포트 요약/리스크 설명문 ─────────────────────────────────────────────────

@dataclass
class ReportContext:
    """리포트 PDF용 입력. 전부 calc_total_value 산출값(만원 단위)과 메타데이터."""
    crop_code: str
    tree_age: int
    area_m2: float
    sido: str
    confidence_grade: str
    est_income_min: int
    est_income_max: int
    est_value_min: int
    est_value_max: int
    land_value_point: int
    facility_value: int
    goodwill_min: int
    goodwill_max: int
    risk_flags: list[str]


@dataclass
class NarrativeResult:
    summary: str
    risk_notes: str
    is_ai_generated: bool  # False면 폴백 템플릿 문장


def _strip_code_fence(text: str) -> str:
    """Claude가 JSON 응답을 ```json ... ``` 코드펜스로 감싸는 경우가 있어 제거."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    return text.strip()


def _get_client():
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        return None
    try:
        import anthropic
        return anthropic.Anthropic(api_key=api_key)
    except Exception:
        return None


def _fallback_narrative(ctx: ReportContext) -> NarrativeResult:
    crop = CROP_NAMES.get(ctx.crop_code, ctx.crop_code)
    summary = (
        f"{ctx.sido} 소재 {crop} {ctx.tree_age}년생, 면적 {ctx.area_m2:,.0f}㎡ 농장입니다. "
        f"예상 연소득은 {ctx.est_income_min:,}~{ctx.est_income_max:,}만원, "
        f"인수 검토가 범위는 {ctx.est_value_min:,}~{ctx.est_value_max:,}만원으로 추정됩니다 "
        f"({ctx.confidence_grade}등급, {GRADE_DESC.get(ctx.confidence_grade, '')})."
    )
    risk_notes = " / ".join(ctx.risk_flags) if ctx.risk_flags else "현재 확인된 추가 리스크 요인은 없습니다."
    return NarrativeResult(summary=summary, risk_notes=risk_notes, is_ai_generated=False)


def generate_narrative(ctx: ReportContext) -> NarrativeResult:
    """리포트 요약문 + 리스크 설명문 생성. 실패 시 결정론적 폴백."""
    client = _get_client()
    if client is None:
        return _fallback_narrative(ctx)

    crop = CROP_NAMES.get(ctx.crop_code, ctx.crop_code)
    risk_flags_text = "\n".join(f"- {f}" for f in ctx.risk_flags) or "- 없음"
    goodwill_text = (
        "해당 없음" if ctx.goodwill_min == 0
        else f"{ctx.goodwill_min:,}~{ctx.goodwill_max:,}만원"
    )

    prompt = f"""다음은 이미 결정론적으로 계산이 끝난 농장 인수 검토 수치다.
아래 숫자를 그대로 사용해 자연스러운 한국어 설명문을 작성하라.
**절대 숫자를 새로 만들거나 변경하지 마라** — 주어진 숫자만 문장에 그대로 인용할 것.

- 지역: {ctx.sido}
- 작목: {crop}, 수령 {ctx.tree_age}년
- 면적: {ctx.area_m2:,.0f}㎡
- 신뢰도 등급: {ctx.confidence_grade}등급 ({GRADE_DESC.get(ctx.confidence_grade, '')})
- 예상 연소득: {ctx.est_income_min:,}~{ctx.est_income_max:,}만원
- 인수 검토가 범위: {ctx.est_value_min:,}~{ctx.est_value_max:,}만원
- 토지 기준가: {ctx.land_value_point:,}만원
- 시설 잔존가: {ctx.facility_value:,}만원
- 영업권: {goodwill_text}
- 리스크 요인:
{risk_flags_text}

다음 JSON 형식으로만 응답하라 (다른 텍스트 없이):
{{"summary": "농장 개요와 가치평가 핵심을 2~3문장으로 요약", "risk_notes": "리스크 요인을 1~2문장으로 자연스럽게 풀어쓴 설명 (리스크 요인이 없으면 '확인된 추가 리스크 요인은 없습니다.')"}}"""

    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        data = json.loads(_strip_code_fence(resp.content[0].text))
        summary = str(data["summary"]).strip()
        risk_notes = str(data["risk_notes"]).strip()
        if not summary or not risk_notes:
            raise ValueError("empty AI output")
        return NarrativeResult(summary=summary, risk_notes=risk_notes, is_ai_generated=True)
    except Exception:
        return _fallback_narrative(ctx)


# ── 매칭 추천 설명문 ──────────────────────────────────────────────────────────

@dataclass
class MatchContext:
    """매칭 설명문용 입력. 전부 calc_match_score 산출값."""
    pref_sido: str
    pref_crop: str
    farm_sido: str
    farm_crop: str
    pref_succession: str
    succession_type: str
    total_score: float
    region_score: float
    crop_score: float
    capital_score: float
    experience_score: float
    succession_score: float
    policy_score: float
    risk_penalty: float


def _fallback_match_explanation(ctx: MatchContext) -> str:
    parts = []
    if ctx.region_score > 0:
        parts.append("희망 지역과 일치")
    if ctx.crop_score > 0:
        parts.append("희망 작목과 일치")
    if ctx.capital_score >= 15:
        parts.append("보유 자본이 검토가를 충분히 충족")
    elif ctx.capital_score > 0:
        parts.append("보유 자본이 검토가 하한에 다소 못 미침")
    if ctx.risk_penalty > 0:
        parts.append(f"리스크 {ctx.risk_penalty:.0f}점 감점 요인 있음")
    body = ", ".join(parts) if parts else "조건 일치도가 낮은 편"
    return f"종합 {ctx.total_score:.0f}점 — {body}."


def generate_match_explanation(ctx: MatchContext) -> str:
    """매칭 추천 설명문 생성 (1~2문장). 실패 시 결정론적 폴백."""
    client = _get_client()
    if client is None:
        return _fallback_match_explanation(ctx)

    prompt = f"""다음은 청년농과 농장의 매칭 점수(이미 계산 완료, 100점 만점)다.
아래 점수를 그대로 인용해 왜 이 점수가 나왔는지 1~2문장으로 자연스럽게 설명하라.
**절대 숫자를 새로 만들거나 변경하지 마라.**

- 총점: {ctx.total_score:.1f} / 100
- 지역 적합도: {ctx.region_score:.1f}/20 (희망 {ctx.pref_sido} vs 농장 {ctx.farm_sido})
- 작목 적합도: {ctx.crop_score:.1f}/20 (희망 {CROP_NAMES.get(ctx.pref_crop, ctx.pref_crop)} vs 농장 {CROP_NAMES.get(ctx.farm_crop, ctx.farm_crop)})
- 자본 적합도: {ctx.capital_score:.1f}/20
- 경력 적합도: {ctx.experience_score:.1f}/15
- 승계방식 적합도: {ctx.succession_score:.1f}/15 (희망 {ctx.pref_succession} vs 농장 {ctx.succession_type})
- 정책자금 적합도: {ctx.policy_score:.1f}/10
- 리스크 감점: -{ctx.risk_penalty:.1f}

순수 텍스트로만 응답하라 (JSON이나 다른 포맷 없이, 1~2문장)."""

    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text.strip()
        if not text:
            raise ValueError("empty AI output")
        return text
    except Exception:
        return _fallback_match_explanation(ctx)
