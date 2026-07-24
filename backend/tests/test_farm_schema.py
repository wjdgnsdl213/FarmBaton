"""농가 등록 요청 스키마 회귀 테스트."""

import pytest
from pydantic import ValidationError

from backend.app.schemas import FarmCreate


def _payload(**overrides):
    data = {
        "address": "충북 충주시 테스트로 1",
        "crop_code": "APPLE",
        "tree_age": 7,
        "area_m2": 1_000,
        "annual_revenue": 50_000_000,
    }
    data.update(overrides)
    return data


@pytest.mark.parametrize("years", [1, 3])
def test_revenue_years_accepts_supported_periods(years):
    farm = FarmCreate(**_payload(revenue_years=years))
    assert farm.revenue_years == years


def test_revenue_years_rejects_unsupported_period():
    with pytest.raises(ValidationError):
        FarmCreate(**_payload(revenue_years=2))

