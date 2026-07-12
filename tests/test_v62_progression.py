from app.services import level_income_multiplier, level_rank

def test_level_income_multiplier():
    assert level_income_multiplier(1) == 1.0
    assert level_income_multiplier(5) == 1.2
    assert level_income_multiplier(30) == 2.0

def test_level_ranks():
    assert level_rank(1) == "Начинающий гражданин"
    assert level_rank(30) == "Легенда Флоптропики"
