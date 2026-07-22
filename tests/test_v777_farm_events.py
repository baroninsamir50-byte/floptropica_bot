from pathlib import Path

from app.farm_events import CROPS, ESTATE_EVENTS, FARM_PRICE, FARMER_PRICE, FARM_START_PLOTS, event_payload
from app.models import Character, EstateEventCycle, Farm, FarmPlot, FarmStock, NpcUnit


def test_farm_balance_and_models():
    assert FARM_PRICE == 0
    assert FARMER_PRICE == 70
    assert FARM_START_PLOTS == 3
    assert len(CROPS) == 5
    assert {"farm_tutorial_completed", "events_tutorial_completed"}.issubset(Character.__table__.columns.keys())
    assert {"hunger", "hunger_updated_at", "starvation_started_at", "exhaustion_started_at"}.issubset(NpcUnit.__table__.columns.keys())
    assert Farm.__tablename__ == "farms"
    assert FarmPlot.__tablename__ == "farm_plots"
    assert FarmStock.__tablename__ == "farm_stock"


def test_twenty_numbered_event_cards_have_upload_keys():
    assert len(ESTATE_EVENTS) == 20
    assert [event["number"] for event in ESTATE_EVENTS] == list(range(1, 21))
    assert len({event["id"] for event in ESTATE_EVENTS}) == 20
    for event in ESTATE_EVENTS:
        payload = event_payload(str(event["id"]))
        assert payload["image_url"].endswith(f"event_card_{event['number']}")
        assert payload["impact"]


def test_event_cycle_tracks_popup_and_guard_safety():
    columns = EstateEventCycle.__table__.columns.keys()
    assert "result_acknowledged" in columns
    assert "guard_death_applied" in columns


def test_frontend_has_one_time_tutorials_selected_events_and_auto_popup():
    js = Path("app/miniapp/static/app.js").read_text(encoding="utf-8")
    assert 'GAME_TUTORIALS' in js
    assert '/tutorial/${kind}/complete' in js
    assert 'state.farm.tutorial_required' in js
    assert 'Нанять первого фермера' in js
    assert 'Построить за ${d.price}' not in js
    assert 'state.events?.tutorial_required' in js
    assert 'selectedEventsPanel' in js
    assert 'Ваши выбранные события' in js
    assert 'pending_event_result' in js
    assert 'ПРИНЯТЬ ПОСЛЕДСТВИЯ' in js
    assert 'УЗНАТЬ СУДЬБУ' not in js.upper()
    assert 'window.scrollTo' not in js


def test_creator_panel_has_numbered_event_art_uploads():
    admin = Path("app/routers/admin.py").read_text(encoding="utf-8")
    keyboards = Path("app/keyboards.py").read_text(encoding="utf-8")
    assert 'admin:event_media' in admin
    assert 'adminevent:' in admin
    assert 'event_card_{number}' in admin
    assert 'Оформление событий' in keyboards
    assert 'farm_bg' in admin
    assert 'icon_farm' in admin


def test_asset_credits_and_static_version_are_present():
    credits = Path("ASSET_CREDITS.md").read_text(encoding="utf-8")
    html = Path("app/miniapp/static/index.html").read_text(encoding="utf-8")
    assert 'Kenney' in credits and 'CC0' in credits
    assert 'Calciumtrice' in credits and 'CC BY 3.0' in credits
    assert 'styles.css?v=7.7.7.1' in html
    assert 'app.js?v=7.7.7.1' in html
