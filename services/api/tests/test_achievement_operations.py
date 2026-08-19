from app.achievement_operations import _rarity


def test_rarity_bands_are_stable():
    assert _rarity(60) == "Common"
    assert _rarity(20) == "Uncommon"
    assert _rarity(7) == "Rare"
    assert _rarity(2) == "Epic"
    assert _rarity(0.5) == "Legendary"
