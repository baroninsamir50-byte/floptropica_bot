from app.services import WORK_REWARD_MULTIPLIER, guard_model_variant


def test_work_reward_multiplier_is_one_point_five():
    assert WORK_REWARD_MULTIPLIER == 1.5


def test_guard_appearance_tiers():
    assert guard_model_variant(1) == 1
    assert guard_model_variant(10) == 1
    assert guard_model_variant(19) == 1
    assert guard_model_variant(20) == 2
    assert guard_model_variant(29) == 2
    assert guard_model_variant(30) == 3
    assert guard_model_variant(50) == 3
