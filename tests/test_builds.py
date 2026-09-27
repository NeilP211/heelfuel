import dataclasses
import re

from heelfuel import builds as B
from heelfuel.builds import MAX_ITEMS, NEAR_DUPLICATE, _overlap, best_builds, cuisine_clash, templates_for
from heelfuel.score import IX, target_for

PERIODS = (("Breakfast", "breakfast"), ("Lunch", "lunch"), ("Late Night", "late_night"))
FLAVOR_SLOTS = {"sauce", "dressing", "topping", "crunch"}


def _all(foods_for):
    return {label: best_builds(foods_for(label), slot, label) for label, slot in PERIODS}


def test_every_period_gets_builds_from_real_items(foods_for):
    for label, bs in _all(foods_for).items():
        assert 2 <= len(bs) <= 5, label
        for b in bs:
            assert len(b.picks) <= MAX_ITEMS
            for key, f, s in b.picks:
                assert not f.suspect, f.name
                # Salsa, hot sauce and dressings aren't meal components, but they belong in their flavor slots.
                assert f.usable or key in FLAVOR_SLOTS, (key, f.name)
                assert 1 <= s <= max(3, f.max_servings)


def test_builds_are_sorted_best_first(foods_for):
    for bs in _all(foods_for).values():
        assert [b.score for b in bs] == sorted((b.score for b in bs), reverse=True)


def test_no_tofu_vegan_or_quinoa_anywhere(foods_for):
    for bs in _all(foods_for).values():
        for b in bs:
            assert not any(B.NOT_ATHLETE.search(f.name) or B.PLANT.search(f.name) for _, f, _ in b.picks)


def test_processed_meat_never_anchors_a_build(foods_for):
    for bs in _all(foods_for).values():
        for b in bs:
            assert b.main is not None and B.unprocessed(b.main), b.name
            assert not any(f.name in ("Sliced Ham", "Bacon") for _, f, _ in b.picks)


def test_label_errors_and_junk_stay_out(foods_for):
    for bs in _all(foods_for).values():
        for b in bs:
            names = {f.name for _, f, _ in b.picks}
            assert not names & {"Swiss Cheese", "Baby Carrots", "Pancake Syrup", "Assorted Cookies", "Rainbow Sprinkles",
                                "Froot Loops®", "Waffle"}


def test_breakfast_and_lunch_use_their_own_dishes(foods_for):
    got = _all(foods_for)
    breakfast = {t.key for t in templates_for("breakfast")}
    main = {t.key for t in templates_for("lunch")}
    assert {b.template.key for b in got["Breakfast"]} <= breakfast
    assert {b.template.key for b in got["Lunch"]} <= main
    assert not breakfast & main


def test_lunch_leader_hits_the_protein_target(foods_for):
    best = best_builds(foods_for("Lunch"), "lunch", "Lunch")[0]
    assert best.vec[IX["protein"]] >= target_for("lunch").protein
    assert best.template.key in ("power_plate", "med_bowl", "rice_bowl", "burrito_bowl")


def test_late_night_is_smaller_than_lunch(foods_for):
    late = best_builds(foods_for("Late Night"), "late_night", "Late Night")[0]
    lunch = best_builds(foods_for("Lunch"), "lunch", "Lunch")[0]
    assert late.vec[IX["kcal"]] <= target_for("late_night").kcal_hi * 1.1
    assert late.vec[IX["kcal"]] < lunch.vec[IX["kcal"]]


def test_builds_in_a_period_are_different_meals(foods_for):
    for bs in _all(foods_for).values():
        for i, a in enumerate(bs):
            for b in bs[i + 1:]:
                assert a.rids != b.rids
                assert _overlap(a, b) < NEAR_DUPLICATE, (a.name, b.name)
                assert not (a.template.key == b.template.key and a.main.rid == b.main.rid)


def test_names_and_plating_text_read_cleanly(foods_for):
    for bs in _all(foods_for).values():
        for b in bs:
            how = b.template.how(b.by_slot())
            assert b.name and how.endswith(".")
            assert "  " not in how and ", ," not in how and ".." not in how
            assert not re.search(r"\band\b[^,.;]*\band\b[^,.;]*\band\b", how), how


def test_cuisines_do_not_mix(food):
    shawarma = food("Chicken Shawarma", "Simply Prepared")
    chipotle = food("Chipotle Lime Chicken", "Simply Prepared Griddle")
    rice = food("Saffron Rice", "Simply Prepared")
    assert cuisine_clash([shawarma, chipotle])
    assert not cuisine_clash([shawarma, rice])
    assert not cuisine_clash([chipotle, rice, food("Steamed Broccoli")])


def test_allergy_pantry_is_left_alone(food):
    oats = dataclasses.replace(food("Old Fashioned Oatmeal"), station="Stress Less Cabinet")
    eggs, grapes = food("Scrambled Eggs"), food("Red Grapes", "Salad Bar")
    bs = best_builds([oats, eggs, grapes], "breakfast", "Breakfast")
    assert bs and not any(f is oats for b in bs for _, f, _ in b.picks)


def test_empty_line_returns_nothing():
    assert best_builds([], "lunch", "Lunch") == []
