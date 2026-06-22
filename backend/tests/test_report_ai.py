"""
report_ai.py 폴백 경로 테스트.

ANTHROPIC_API_KEY 없이도(또는 호출 실패 시) 정적 템플릿 문장으로 즉시
대체되는지 확인 — 데모가 AI 장애로 죽지 않아야 한다는 요건의 핵심 검증.
실제 Claude API 호출은 키 발급 전이라 테스트 대상이 아님(네트워크 비의존).
"""
import pytest

from backend.app.services.report_ai import (
    MatchContext,
    ReportContext,
    _strip_code_fence,
    generate_match_explanation,
    generate_narrative,
)


@pytest.fixture(autouse=True)
def no_api_key(monkeypatch):
    """키가 설정돼 있어도 폴백 경로만 검증 — 네트워크 호출 차단."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


@pytest.fixture
def report_ctx():
    return ReportContext(
        crop_code="APPLE", tree_age=7, area_m2=5_000.0, sido="충북",
        confidence_grade="C",
        est_income_min=900, est_income_max=1_300,
        est_value_min=8_000, est_value_max=9_800,
        land_value_point=7_000, facility_value=500,
        goodwill_min=0, goodwill_max=0,
        risk_flags=["실거래 표본 부족 — 공시지가 기반 추정"],
    )


def test_generate_narrative_falls_back_without_key(report_ctx):
    result = generate_narrative(report_ctx)
    assert result.is_ai_generated is False
    # 숫자는 ctx 그대로 인용돼야 함 (LLM이 새로 만들지 않음을 폴백 경로에서도 보장)
    assert "8,000" in result.summary
    assert "9,800" in result.summary
    assert "실거래 표본 부족" in result.risk_notes


def test_generate_narrative_no_risk_flags(report_ctx):
    report_ctx.risk_flags = []
    result = generate_narrative(report_ctx)
    assert "리스크 요인은 없습니다" in result.risk_notes


@pytest.fixture
def match_ctx():
    return MatchContext(
        pref_sido="충북", pref_crop="APPLE", farm_sido="충북", farm_crop="APPLE",
        pref_succession="SALE", succession_type="SALE",
        total_score=95.0, region_score=20.0, crop_score=20.0, capital_score=20.0,
        experience_score=15.0, succession_score=15.0, policy_score=5.0, risk_penalty=0.0,
    )


def test_generate_match_explanation_falls_back_without_key(match_ctx):
    text = generate_match_explanation(match_ctx)
    assert "95" in text
    assert "일치" in text


def test_generate_match_explanation_with_risk_penalty(match_ctx):
    match_ctx.risk_penalty = 10.0
    match_ctx.capital_score = 0.0
    text = generate_match_explanation(match_ctx)
    assert "감점" in text


# ─────────────────────────────────────────────────────────────────────────────
# _strip_code_fence — Claude가 JSON 응답을 ```json ... ``` 로 감싸는 경우 대응
# (실제 키로 확인된 회귀: 펜스 미제거 시 json.loads가 실패해 항상 폴백으로 빠짐)
# ─────────────────────────────────────────────────────────────────────────────

def test_strip_code_fence_removes_json_fence():
    raw = '```json\n{"summary": "a", "risk_notes": "b"}\n```'
    assert _strip_code_fence(raw) == '{"summary": "a", "risk_notes": "b"}'


def test_strip_code_fence_removes_bare_fence():
    raw = '```\n{"a": 1}\n```'
    assert _strip_code_fence(raw) == '{"a": 1}'


def test_strip_code_fence_passthrough_when_unfenced():
    raw = '{"a": 1}'
    assert _strip_code_fence(raw) == '{"a": 1}'


def test_generate_narrative_parses_fenced_json_response(report_ctx, monkeypatch):
    """실제 Claude 응답이 ```json 펜스로 감싸여 와도 is_ai_generated=True로 파싱돼야 함."""
    fenced = '```json\n{"summary": "AI 생성 요약", "risk_notes": "AI 생성 리스크"}\n```'

    class _FakeBlock:
        text = fenced

    class _FakeResponse:
        content = [_FakeBlock()]

    class _FakeMessages:
        def create(self, **kwargs):
            return _FakeResponse()

    class _FakeClient:
        messages = _FakeMessages()

    monkeypatch.setattr("backend.app.services.report_ai._get_client", lambda: _FakeClient())

    result = generate_narrative(report_ctx)
    assert result.is_ai_generated is True
    assert result.summary == "AI 생성 요약"
    assert result.risk_notes == "AI 생성 리스크"
