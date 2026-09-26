from conftest import fixture_text

from heelfuel.parse import clean_text, parse_menu_page, parse_recipe, split_period_label


def test_menu_periods_and_slots(menu):
    assert menu.status == "ok"
    labels = [(p.label, p.hours, p.slot, p.counts) for p in menu.periods]
    assert labels == [
        ("Breakfast", "7am-11am", "breakfast", True),
        ("Lunch", "11am-3pm", "lunch", True),
        ("Late Night", "9pm-12am", "late_night", True),
    ]


def test_menu_items_carry_station_allergens_and_ingredients(menu, recipe_ids):
    lunch = next(p for p in menu.periods if p.label == "Lunch")
    shawarma = next(i for i in lunch.items if i.name == "Chicken Shawarma")
    assert shawarma.station == "Simply Prepared"
    assert shawarma.recipe_id == recipe_ids["Chicken Shawarma"]
    assert "chicken thigh" in shawarma.searchable
    wrap = next(i for i in lunch.items if i.name == "Spinach Wrap")
    assert "wheat" in wrap.allergens
    assert "vegetarian" in wrap.props


def test_soft_404_means_no_menu():
    m = parse_menu_page(fixture_text("page_not_found.html"), "lenoir", "2026-12-26")
    assert m.status == "no_menu"
    assert m.periods == []
    assert "No menu" in m.message


def test_period_labels():
    assert split_period_label("Late Night  (9pm-12am)") == ("Late Night", "9pm-12am")
    assert split_period_label("Dinner (5pm-8:30pm)") == ("Dinner", "5pm-8:30pm")
    assert split_period_label("Grab & Go") == ("Grab & Go", "")


def test_clean_text_swaps_typographic_dashes():
    s = "Chicken " + chr(0x2014) + " Grilled " + chr(0x2013) + " 4 oz"
    assert clean_text(s) == "Chicken - Grilled - 4 oz"


def test_recipe_label_fields(recipes, recipe_ids):
    waffle = recipes[recipe_ids["Waffle"]]
    n = waffle.nutrition
    assert waffle.name == "Waffle"
    assert waffle.serving == "1 each"
    assert (n.kcal, n.protein, n.carbs, n.sodium) == (90, 3, 20, 270)
    assert n.fiber == 0.63
    assert n.added_sugar == 3  # the label's added sugar exceeds its total sugar; kept as reported
    assert waffle.allergens == ["Wheat", "Milk", "Gluten"]
    assert "Mono And Diglycerides" in waffle.ingredients


def test_blank_vitamin_d_is_none(recipes, recipe_ids):
    assert recipes[recipe_ids["Rainbow Sprinkles"]].nutrition.vit_d is None


def test_thousands_separator_and_fraction_serving(recipes, recipe_ids):
    swiss = recipes[recipe_ids["Swiss Cheese"]]
    assert swiss.nutrition.kcal == 1780
    rice = recipes[recipe_ids["Saffron Rice"]]
    assert rice.serving == chr(0x00BD) + " cup"


def test_bad_payload_raises():
    import pytest
    with pytest.raises(ValueError):
        parse_recipe('{"success": false}', "1")
