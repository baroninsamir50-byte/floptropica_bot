from pathlib import Path

from app.models import Character, StoryRead


def test_story_read_tracks_unique_reader_and_author():
    constraint_names = {constraint.name for constraint in StoryRead.__table__.constraints}
    assert "uq_story_reader_author" in constraint_names
    assert {"reader_character_id", "story_character_id", "completed_at"}.issubset(StoryRead.__table__.columns.keys())


def test_character_has_secret_story_achievement_flag():
    assert "story_reader_achievement_claimed" in Character.__table__.columns


def test_npc_card_hides_old_progression_text_and_school_button():
    js = Path("app/miniapp/static/app.js").read_text(encoding="utf-8")
    npc_card = js[js.index("function npcCard(npc){"):js.index("function npcsView(){")]
    assert "progression_rule" not in npc_card
    assert "Школа навыка" not in npc_card
    assert "npc.requires_kit" in npc_card


def test_work_timer_and_story_completion_are_wired():
    js = Path("app/miniapp/static/app.js").read_text(encoding="utf-8")
    api = Path("app/miniapp/api.py").read_text(encoding="utf-8")
    assert "data-work-countdown" in js
    assert "startWorkCountdown" in js
    assert "/story/complete" in api
    assert "achievement:secret_story_reader" in api
