from app.work_catalog import available_professions, profession_by_key

def test_faction_chair_restricted():
    citizen = {key for key, _ in available_professions("Гражданин")}
    leader = {key for key, _ in available_professions("Хорги")}
    assert "faction_chair" not in citizen
    assert "faction_chair" in leader

def test_throne_role_restricted():
    citizen = {key for key, _ in available_professions("Гражданин")}
    queen = {key for key, _ in available_professions("Королева")}
    assert "throne_chair" not in citizen
    assert "throne_chair" in queen

def test_profession_key_exists():
    assert profession_by_key("royal_designer")["name"] == "Королевский художник-дизайнер"
