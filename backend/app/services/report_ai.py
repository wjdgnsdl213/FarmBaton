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
from typing import Optional

CROP_NAMES = {"APPLE": "사과", "PEACH": "복숭아", "GRAPE": "포도"}
GRADE_DESC = {
    "A": "실사 기반 추정", "B": "농가 제출자료 기반 추정",
    "C": "사전 검토용 추정", "D": "참고용 자동 추정",
}

MODEL = "claude-haiku-4-5-20251001"

# 관점별 메타: (라벨, AI 프롬프트용 관점 지시, 폴백 조언 행동 항목)
_AUDIENCE = {
    "FARMER": {
        "label": "농장주",
        "perspective": (
            "이 리포트를 읽는 사람은 '농장을 넘기려는 농장주'다. "
            "매도·승계를 준비하는 입장에서, 위 숫자를 근거로 다음을 짚어라: "
            "시설 잔존가와 영업권을 더 인정받으려면 어떤 자료(매출 장부, 시설 설치 내역, "
            "판로 계약서 등)를 준비하면 좋은지, 승계 조건 협상에서 신뢰등급을 올릴 방법, "
            "지금 제시된 인수 검토가 범위를 어떻게 활용할지."
        ),
        "fallback_actions": [
            "최근 매출 장부·출하 내역을 정리해 영업권 근거 자료로 준비합니다.",
            "시설 설치·수리 내역과 연도를 문서화해 시설 잔존가 평가를 보강합니다.",
            "기존 판로(계약재배·직거래) 승계 가능 여부를 문서로 확보합니다.",
            "제시된 인수 검토가 범위를 협상 출발점으로 두고, 거래 전 공인중개사·감정평가사 검토를 받습니다.",
        ],
    },
    "YOUNG": {
        "label": "청년농",
        "perspective": (
            "이 리포트를 읽는 사람은 '이 농장을 인수하려는 청년농'이다. "
            "인수를 검토하는 입장에서, 위 숫자를 근거로 다음을 짚어라: "
            "보유 자본과 정책자금(청년창업농 융자 등)으로 인수 검토가 범위를 감당할 수 있는지, "
            "예상 연소득 대비 투자 회수 관점, 작목 수령과 시설 노후도가 초기 영농에 주는 부담, "
            "영농을 시작하기 전 확인할 체크리스트."
        ),
        "fallback_actions": [
            "보유 자본과 청년창업농 정책자금 한도로 인수 검토가 범위를 감당할 수 있는지 계산합니다.",
            "예상 연소득 기준으로 대략적인 투자 회수 기간을 가늠합니다.",
            "현장 방문으로 수목 생육 상태와 주요 시설의 가동 수명을 확인합니다.",
            "기존 판로 인수 가능 여부와 초기 추가 투자 필요액을 영농 시작 전에 점검합니다.",
        ],
    },
}


def _audience_meta(audience: str) -> dict:
    return _AUDIENCE.get(audience, _AUDIENCE["FARMER"])


# ── 리포트 요약/리스크 설명문 ─────────────────────────────────────────────────

@dataclass
class ReportContext:
    """리포트 PDF용 입력. 전부 calc_total_value 산출값(만원 단위)과 메타데이터.

    audience: 'FARMER'(농장주) | 'YOUNG'(청년농). 같은 숫자라도 관점별로
    설명문·조언을 달리 생성한다(숫자는 동일, 서술만 분기 — rule 1 안전).
    """
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
    audience: str = "FARMER"


@dataclass
class NarrativeResult:
    summary: str
    risk_notes: str
    advice_items: list[str]  # 관점별 조언/다음 단계 (행동 항목 3~5개)
    is_ai_generated: bool    # False면 폴백 템플릿 문장


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
    meta = _audience_meta(ctx.audience)
    summary = (
        f"{ctx.sido} 소재 {crop} {ctx.tree_age}년생, 면적 {ctx.area_m2:,.0f}㎡ 농장입니다. "
        f"예상 연소득은 {ctx.est_income_min:,}~{ctx.est_income_max:,}만원, "
        f"인수 검토가 범위는 {ctx.est_value_min:,}~{ctx.est_value_max:,}만원으로 추정됩니다 "
        f"({ctx.confidence_grade}등급, {GRADE_DESC.get(ctx.confidence_grade, '')})."
    )
    risk_notes = " / ".join(ctx.risk_flags) if ctx.risk_flags else "현재 확인된 추가 리스크 요인은 없습니다."
    return NarrativeResult(
        summary=summary, risk_notes=risk_notes,
        advice_items=list(meta["fallback_actions"]), is_ai_generated=False,
    )


def generate_narrative(ctx: ReportContext) -> NarrativeResult:
    """리포트 요약문 + 리스크 설명문 생성. 실패 시 결정론적 폴백."""
    client = _get_client()
    if client is None:
        return _fallback_narrative(ctx)

    crop = CROP_NAMES.get(ctx.crop_code, ctx.crop_code)
    meta = _audience_meta(ctx.audience)
    risk_flags_text = "\n".join(f"- {f}" for f in ctx.risk_flags) or "- 없음"
    goodwill_text = (
        "해당 없음" if ctx.goodwill_min == 0
        else f"{ctx.goodwill_min:,}~{ctx.goodwill_max:,}만원"
    )

    prompt = f"""다음은 이미 결정론적으로 계산이 끝난 농장 인수 검토 수치다.
아래 숫자를 그대로 사용해 자연스러운 한국어 설명문을 작성하라.
**절대 숫자를 새로 만들거나 변경하지 마라** — 주어진 숫자만 문장에 그대로 인용할 것.
조언(advice)에는 새로운 금액·수치를 만들지 말고, 위 숫자에 근거한 정성적 조언만 담아라.

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

[독자 관점] {meta['perspective']}

작성 규칙:
- summary: 큰 금액(인수 검토가 범위)은 별도 영역에 크게 표시되므로 요약에서는
  같은 숫자를 다시 반복하지 말고, 농장 성격과 판단 포인트를 1~2문장으로.
- advice_items: 위 독자 관점에서 바로 실행할 행동을 3~5개의 짧은 항목으로.
  각 항목은 한 문장, 명령형(~합니다/~확인합니다)으로. 새 금액·수치 만들지 말 것.

다음 JSON 형식으로만 응답하라 (다른 텍스트 없이):
{{"summary": "1~2문장 요약(큰 금액 반복 금지)", "risk_notes": "리스크 요인을 1문장으로 (없으면 '확인된 추가 리스크 요인은 없습니다.')", "advice_items": ["행동 항목1", "행동 항목2", "행동 항목3"]}}"""

    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=900,
            messages=[{"role": "user", "content": prompt}],
        )
        data = json.loads(_strip_code_fence(resp.content[0].text))
        summary = str(data["summary"]).strip()
        risk_notes = str(data["risk_notes"]).strip()
        advice_items = [str(x).strip() for x in data.get("advice_items", []) if str(x).strip()]
        if not summary or not risk_notes or not advice_items:
            raise ValueError("empty AI output")
        return NarrativeResult(
            summary=summary, risk_notes=risk_notes,
            advice_items=advice_items, is_ai_generated=True,
        )
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


def fallback_match_explanation(ctx: MatchContext) -> str:
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
        return fallback_match_explanation(ctx)

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
        return fallback_match_explanation(ctx)


# ── 지원사업 추천 사유 ────────────────────────────────────────────────────────

@dataclass
class ProgramPitchContext:
    """지원사업 추천 사유용 입력. 사업의 사실 정보(이름·내용·금액)는 CSV 원문
    그대로이며 LLM은 절대 바꾸지 않는다 — 청년농 프로필에 맞춰 왜 추천되는지
    한 문장만 덧붙인다."""
    program_name: str
    program_description: str
    amount_text: str
    pref_sido: Optional[str]
    pref_crop: Optional[str]
    policy_fund: bool


def fallback_program_pitch(ctx: ProgramPitchContext) -> str:
    return "지역·작목 조건에 부합하는 지원사업입니다."


def generate_program_pitch(ctx: ProgramPitchContext) -> str:
    """지원사업 추천 사유 1문장 생성. 실패 시 결정론적 폴백."""
    client = _get_client()
    if client is None:
        return fallback_program_pitch(ctx)

    sido_text = ctx.pref_sido or "지역 무관"
    crop_text = CROP_NAMES.get(ctx.pref_crop, ctx.pref_crop) if ctx.pref_crop else "작목 무관"

    prompt = f"""다음은 이미 필터링되어 추천 대상으로 확정된 지원사업이다.
아래 사업명·내용·금액은 그대로 인용하되 **절대 바꾸거나 새로운 숫자를
만들지 마라**. 이 청년농 프로필에 왜 이 사업이 맞는지 1문장으로만 설명하라.

- 사업명: {ctx.program_name}
- 지원 내용: {ctx.program_description}
- 지원 금액: {ctx.amount_text}
- 청년농 희망 지역: {sido_text}
- 청년농 희망 작목: {crop_text}
- 정책자금 신청 예정 여부: {"예" if ctx.policy_fund else "아니오"}

순수 텍스트로만 응답하라 (JSON이나 다른 포맷 없이, 1문장)."""

    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=150,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text.strip()
        if not text:
            raise ValueError("empty AI output")
        return text
    except Exception:
        return fallback_program_pitch(ctx)
