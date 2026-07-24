"""청년농 희망 작목 우선 추천 분리 검증."""

from backend.app.routers.young_farmers import _partition_matches
from backend.app.schemas import MatchItem


def _item(farm_id: int, crop_code: str, score: float) -> MatchItem:
    return MatchItem(
        farm_id=farm_id,
        address=f"{crop_code} 농장",
        sido="충북",
        crop_code=crop_code,
        tree_age=10,
        area_m2=3_000,
        succession_type="SALE",
        est_value_min=10_000,
        est_value_max=12_000,
        total_score=score,
        region_score=20,
        crop_score=20 if crop_code == "PEACH" else 0,
        capital_score=20,
        experience_score=10,
        succession_score=15,
        policy_score=10,
        risk_penalty=0,
    )


def test_preferred_crop_is_not_displaced_by_higher_other_crop_score():
    items = [
        _item(1, "APPLE", 95),
        _item(2, "PEACH", 72),
        _item(3, "GRAPE", 88),
        _item(4, "PEACH", 65),
    ]

    preferred, other = _partition_matches(items, "PEACH")

    assert [item.farm_id for item in preferred] == [2, 4]
    assert all(item.crop_code == "PEACH" for item in preferred)
    assert [item.farm_id for item in other] == [1, 3]
    assert all(item.crop_code != "PEACH" for item in other)


def test_no_crop_preference_keeps_combined_score_order():
    items = [
        _item(1, "APPLE", 81),
        _item(2, "PEACH", 92),
        _item(3, "GRAPE", 75),
    ]

    preferred, other = _partition_matches(items, None)

    assert [item.farm_id for item in preferred] == [2, 1, 3]
    assert other == []
