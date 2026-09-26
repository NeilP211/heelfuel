from heelfuel.formats import main_protein, meal_format
from heelfuel.optimize import search
from heelfuel.score import IX, slot_targets

ALL = {"breakfast", "lunch", "dinner", "late_night"}


def test_lunch_top_pick_hits_protein_with_real_foods(foods_for):
    t = slot_targets(ALL)["lunch"]
    combos = search(foods_for("Lunch"), t)
    assert 1 <= len(combos) <= 3
    best = combos[0]
    assert best.vec[IX["protein"]] >= 0.95 * t.protein
    for f, s in best.items:
        assert f.role in ("protein", "carb", "produce", "extra")
        assert not f.suspect
        assert s <= f.max_servings


def test_chef_plate_wins_when_it_exists(foods_for):
    t = slot_targets(ALL)["lunch"]
    best = search(foods_for("Lunch"), t)[0]
    stations = {f.station for f, _ in best.items if f.role != "extra"}
    assert main_protein(best.items).name in ("Chicken Shawarma", "Chipotle Lime Chicken", "Blackened Tilapia")
    assert meal_format(best.items, "lunch") is not None
    assert len(stations) <= 2


def test_top_three_have_different_main_proteins(foods_for):
    combos = search(foods_for("Lunch"), slot_targets(ALL)["lunch"])
    mains = [main_protein(c.items).rid for c in combos]
    assert len(set(mains)) == len(mains)


def test_breakfast_only_food_stays_at_breakfast(foods_for):
    combos = search(foods_for("Lunch"), slot_targets(ALL)["lunch"])
    for c in combos:
        assert not any(f.kind == "cereal" or "waffle" in f.name.lower() for f, _ in c.items)


def test_no_suspect_or_excluded_items_anywhere(foods_for):
    for label, slot in (("Breakfast", "breakfast"), ("Lunch", "lunch"), ("Late Night", "late_night")):
        for c in search(foods_for(label), slot_targets(ALL)[slot]):
            names = {f.name for f, _ in c.items}
            assert not names & {"Swiss Cheese", "Baby Carrots", "Pancake Syrup", "Assorted Cookies", "Rainbow Sprinkles"}


def test_late_night_is_snack_sized(foods_for):
    t = slot_targets(ALL)["late_night"]
    best = search(foods_for("Late Night"), t)[0]
    assert best.vec[IX["kcal"]] < 600
    assert best.vec[IX["protein"]] >= 0.95 * t.protein


def test_empty_line_returns_nothing():
    assert search([], slot_targets(ALL)["lunch"]) == []


def test_main_dish_is_not_the_side_yogurt(food):
    shawarma = food("Chicken Shawarma", "Simply Prepared")
    yogurt = food("Plain Greek Yogurt", "Salad Bar")
    assert main_protein(((shawarma, 1), (yogurt, 2))) is shawarma
    assert main_protein(((yogurt, 2),)) is yogurt


def test_breakfast_plate_needs_a_breakfast_side(food):
    eggs = food("Scrambled Eggs")
    oats = food("Old Fashioned Oatmeal")
    beans = food("Southwest Black Beans")
    assert meal_format(((eggs, 2), (oats, 2)), "breakfast") == "breakfast plate"
    assert meal_format(((eggs, 2), (beans, 1)), "breakfast") != "breakfast plate"


def test_titles_in_a_period_are_distinct(foods_for):
    from heelfuel.explain import title_for
    for label, slot in (("Breakfast", "breakfast"), ("Lunch", "lunch")):
        combos = search(foods_for(label), slot_targets(ALL)[slot])
        titles = [title_for(c, slot) for c in combos]
        assert len(set(titles)) == len(titles), titles
