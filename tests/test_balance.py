from app.services import xp_for_next


def test_xp_formula():
    assert xp_for_next(1) == 100
    assert xp_for_next(2) == 300
