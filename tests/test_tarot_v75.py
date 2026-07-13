from app.tarot_data import standard_tarot_cards


def test_standard_deck_has_78_cards():
    assert len(standard_tarot_cards()) == 78


def test_all_cards_have_two_meanings():
    for card in standard_tarot_cards():
        assert card["upright"]
        assert card["reversed"]
