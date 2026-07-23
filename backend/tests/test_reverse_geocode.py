from backend.app.main import _find_static_reverse_address


def test_static_reverse_geocode_matches_exact_demo_coordinate():
    address = _find_static_reverse_address(127.88529118826408, 36.934954391816675)

    assert address == "충청북도 충주시 가주동 483"


def test_static_reverse_geocode_does_not_guess_distant_address():
    address = _find_static_reverse_address(126.9780, 37.5665)

    assert address is None
