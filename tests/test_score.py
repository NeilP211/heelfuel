import pytest

from heelfuel import config as C
from heelfuel.score import IX, item_vec, penalties, score_meal, target_for, vec_add, vec_sum

LUNCH = target_for("lunch")


def _meal(**totals):
    v = [0.0] * len(IX)
    for k, val in totals.items():
        v[IX[k]] = val
    return tuple(v)


def _good_lunch(**over):
    t = LUNCH
    base = dict(kcal=t.kcal_mid, protein=t.protein * 1.1, carbs=90, fat=25, fiber=12, produce_cups=1.5,
                quality_carbs=80, pq_protein=t.protein, sodium=800, potassium=1500, calcium=400, iron=6, vit_d=3,
                magnesium=140, zinc=4, vit_c=40, vit_a=300, epa_dha=150)
    base.update(over)
    return _meal(**base)


def test_each_period_has_its_own_target():
    assert target_for("breakfast").kind == "breakfast"
    assert target_for("lunch") is target_for("dinner") is C.MEAL_TARGETS["main"]
    assert target_for("late_night").kind == "late"
    assert target_for("late_night").kcal_hi < target_for("lunch").kcal_lo + 100


def test_parts_stay_inside_their_budgets():
    _, parts = score_meal(_good_lunch(), LUNCH, explain=True)
    assert 0 <= parts["macros"] <= 35
    assert 0 <= parts["micros"] <= 35
    assert 0 <= parts["clean"] <= 30
    assert parts["macros"] + parts["micros"] + parts["clean"] > 85


def test_protein_dominates():
    good = _good_lunch()
    short = _good_lunch(protein=LUNCH.protein * 0.5, pq_protein=LUNCH.protein * 0.5)
    assert score_meal(good, LUNCH) - score_meal(short, LUNCH) > 8


def test_micros_reward_daily_value_coverage():
    thin = _good_lunch(fiber=2, potassium=300, vit_c=0, vit_a=0, magnesium=30, produce_cups=0)
    _, a = score_meal(thin, LUNCH, explain=True)
    _, b = score_meal(_good_lunch(), LUNCH, explain=True)
    assert b["micros"] - a["micros"] > 10
    assert b["coverage"]["potassium"] == pytest.approx(1500 / (C.DV["potassium"] * LUNCH.dv_share))


def test_one_gram_of_added_sugar_costs_nothing():
    base = score_meal(_good_lunch(), LUNCH)
    assert score_meal(_good_lunch(added_sugar=1), LUNCH) == base == score_meal(_good_lunch(added_sugar=9), LUNCH)


def test_added_sugar_penalty_scales_with_dose():
    p25 = penalties(_good_lunch(added_sugar=25), LUNCH)["added_sugar"]
    p40 = penalties(_good_lunch(added_sugar=40), LUNCH)["added_sugar"]
    assert p25 == pytest.approx((25 - C.ADDED_SUGAR_PER_MEAL) * C.ADDED_SUGAR_PTS_PER_G)
    assert p40 > p25


def test_single_dye_is_a_small_deduction():
    drop = score_meal(_good_lunch(), LUNCH) - score_meal(_good_lunch(dye_pts=C.DYE_PTS), LUNCH)
    assert 0.5 < drop < 2.0


def test_high_protein_meal_with_a_dye_beats_clean_low_protein_meal():
    dyed_high = _good_lunch(dye_pts=C.DYE_PTS)
    clean_low = _good_lunch(protein=LUNCH.protein * 0.6, pq_protein=LUNCH.protein * 0.6)
    assert score_meal(dyed_high, LUNCH) > score_meal(clean_low, LUNCH)


def test_sodium_penalty_scales_and_caps():
    s = [score_meal(_good_lunch(sodium=na), LUNCH) for na in (900, 1600, 2400, 5000, 9000)]
    assert s[0] > s[1] > s[2] > s[3]
    assert s[3] - s[4] < 1.0  # capped: 9,000 mg isn't punished much more than 5,000


def test_evidence_weight_keeps_seed_oil_tiny():
    base = score_meal(_good_lunch(), LUNCH)
    assert base - score_meal(_good_lunch(seed_oil_kcal=LUNCH.kcal_mid), LUNCH) < 1.0


def test_processed_meat_costs_more_than_a_dye():
    base = score_meal(_good_lunch(), LUNCH)
    ham = base - score_meal(_good_lunch(processed_meat_g=100), LUNCH)
    dye = base - score_meal(_good_lunch(dye_pts=C.DYE_PTS), LUNCH)
    assert ham > 2 * dye


def test_ultra_processed_share_costs_whole_food_points():
    _, clean = score_meal(_good_lunch(), LUNCH, explain=True)
    _, upf = score_meal(_good_lunch(upf_kcal=LUNCH.kcal_mid * 0.8), LUNCH, explain=True)
    assert clean["whole_food"] - upf["whole_food"] == pytest.approx(C.WHOLE_FOOD_POINTS * 0.8)


def test_protein_past_the_soft_cap_costs_a_little():
    on = _good_lunch(protein=LUNCH.protein * 1.1)
    way_over = _good_lunch(protein=LUNCH.protein * 2.2)
    gap = score_meal(on, LUNCH) - score_meal(way_over, LUNCH)
    assert 2 < gap <= 5.5


def test_calories_outside_the_meal_band_taper():
    s = [score_meal(_good_lunch(kcal=k), LUNCH) for k in (800, 1000, 1200, 1500)]
    assert s[0] > s[1] > s[2] >= s[3]


def test_item_vec_dose_factor_for_additives(food):
    wrap = food("Spinach Wrap", "Deli")
    one = item_vec(wrap, 1)[IX["dye_pts"]]
    two = item_vec(wrap, 2)[IX["dye_pts"]]
    assert two == pytest.approx(one * 1.5)
    assert item_vec(wrap, 2)[IX["kcal"]] == pytest.approx(2 * wrap.nutrition.kcal)


def test_vec_sum_matches_pairwise_add(food):
    a, b = item_vec(food("Chicken Shawarma"), 2), item_vec(food("Saffron Rice"), 3)
    assert vec_sum([a, b]) == vec_add(a, b)
