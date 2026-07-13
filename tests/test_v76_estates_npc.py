from app.miniapp.api import unlocked_room_count


def test_room_unlocks():
    assert unlocked_room_count(1) == 1
    assert unlocked_room_count(3) == 2
    assert unlocked_room_count(6) == 3


def test_guard_time_formula():
    def minutes(count):
        return max(5, round(30 - (count - 1) * 3.5))
    assert minutes(1) == 30
    assert minutes(2) in {26, 27}
    assert minutes(8) == 6
