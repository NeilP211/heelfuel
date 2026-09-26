import dataclasses

import pytest

from heelfuel import config as C
from heelfuel.score import IX, item_vec, score_vec, slot_targets, vec_add, vec_sum

ALL = {"breakfast", "lunch", "dinner", "late_night"}


def test_slot_targets_add_up_to_the_day():
    t = slot_targets(ALL)
    assert sum(x.kcal for x in t.values()) == pytest.approx(C.DAILY.kcal)
    assert sum(x.protein for x in t.values()) == pytest.approx(C.DAILY.protein)


def test_missing_late_night_renormalizes():
    t = slot_targets({"breakfast", "lunch", "dinner"})
    main = [t[s] for s in ("breakfast", "lunch", "dinner")]
    assert sum(x.protein for x in main) == pytest.approx(C.DAILY.protein)
    assert t["lunch"].protein > slot_targets(ALL)["lunch"].protein


def _meal(**totals):
    v = [0.0] * len(IX)
    for k, val in totals.items():
        v[IX[k]] = val
    return tuple(v)


def _good_lunch(**over):
    t = slot_targets(ALL)["lunch"]
    base = dict(kcal=t.kcal, protein=t.protein * 1.05, carbs=t.carbs, fat=t.fat, fiber=t.fiber,
                produce_cups=t.produce_cups, quality_carbs=t.carbs * 0.9, pq_protein=t.protein * 1.05,
                sodium=800, potassium=1200, calcium=300, iron=3, vit_d=2)
    base.update(over)
    return _meal(**base), t


def test_protein_dominates():
    good, t = _good_lunch()
    short, _ = _good_lunch(protein=t.protein * 0.5, pq_protein=t.protein * 0.5)
    assert score_vec(good, t) - score_vec(short, t) > 10


def test_one_gram_of_added_sugar_costs_nothing():
    base, t = _good_lunch()
    one, _ = _good_lunch(added_sugar=1)
    nine, _ = _good_lunch(added_sugar=9)
    assert score_vec(one, t) == score_vec(base, t) == score_vec(nine, t)


def test_added_sugar_penalty_scales_with_dose():
    base, t = _good_lunch()
    _, parts25 = score_vec(_good_lunch(added_sugar=25)[0], t, explain=True)
    _, parts40 = score_vec(_good_lunch(added_sugar=40)[0], t, explain=True)
    assert parts25["added_sugar"] == pytest.approx(-(25 - 10) * C.ADDED_SUGAR_PTS_PER_G)
    assert parts40["added_sugar"] < parts25["added_sugar"]


def test_single_dye_is_a_small_deduction():
    base, t = _good_lunch()
    dyed, _ = _good_lunch(dye_pts=C.DYE_PTS)
    drop = score_vec(base, t) - score_vec(dyed, t)
    assert 0.5 < drop < 2.0


def test_high_protein_meal_with_a_dye_beats_clean_low_protein_meal():
    t = slot_targets(ALL)["lunch"]
    dyed_high, _ = _good_lunch(dye_pts=C.DYE_PTS)
    clean_low, _ = _good_lunch(protein=t.protein * 0.6, pq_protein=t.protein * 0.6)
    assert score_vec(dyed_high, t) > score_vec(clean_low, t)


def test_sodium_penalty_scales_and_caps():
    t = slot_targets(ALL)["lunch"]
    s = [score_vec(_good_lunch(sodium=na)[0], t) for na in (900, 1600, 2400, 5000, 9000)]
    assert s[0] > s[1] > s[2] > s[3]
    assert s[3] - s[4] < 1.0  # capped: 9,000 mg isn't punished much more than 5,000


def test_evidence_weight_keeps_seed_oil_tiny():
    base, t = _good_lunch()
    all_seed_oil, _ = _good_lunch(seed_oil_kcal=t.kcal)
    assert score_vec(base, t) - score_vec(all_seed_oil, t) < 1.0


def test_item_vec_dose_factor_for_additives(food):
    wrap = food("Spinach Wrap", "Deli")
    one = item_vec(wrap, 1)[IX["dye_pts"]]
    two = item_vec(wrap, 2)[IX["dye_pts"]]
    assert two == pytest.approx(one * 1.5)
    assert item_vec(wrap, 2)[IX["kcal"]] == pytest.approx(2 * wrap.nutrition.kcal)


def test_vec_sum_matches_pairwise_add(food):
    a, b = item_vec(food("Chicken Shawarma"), 2), item_vec(food("Saffron Rice"), 3)
    assert vec_sum([a, b]) == vec_add(a, b)
