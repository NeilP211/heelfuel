import pytest

from heelfuel.builds import TEMPLATE_BY_KEY, Build
from heelfuel.explain import build_payload, chips, dv_percent, item_payload, label_totals, steps
from heelfuel.score import item_vec, score_meal, target_for, vec_sum


def _build(food, key, picks, slot="lunch"):
    vec = vec_sum(item_vec(f, s) for _, f, s in picks)
    return Build(TEMPLATE_BY_KEY[key], tuple(picks), vec, score_meal(vec, target_for(slot)))


@pytest.fixture
def plate(food):
    return _build(food, "power_plate", [
        ("protein", food("Chicken Shawarma", "Simply Prepared"), 2),
        ("starch", food("Saffron Rice", "Simply Prepared"), 2),
        ("veg", food("Steamed Broccoli", "Simply Prepared Griddle"), 1),
        ("fruit", food("Red Grapes", "Salad Bar"), 1),
    ])


def test_label_totals_multiply_servings(plate, food):
    tot = label_totals(plate)
    shawarma = food("Chicken Shawarma", "Simply Prepared").nutrition
    rice = food("Saffron Rice", "Simply Prepared").nutrition
    assert tot["protein"] >= 2 * shawarma.protein + 2 * rice.protein
    assert tot["sugars"] >= tot["added_sugar"]
    assert tot["vit_c"] > 0  # estimated from the broccoli and grapes


def test_daily_values_match_the_fda_label():
    dv = dv_percent({"fat": 39, "sat_fat": 10, "trans_fat": 0, "cholesterol": 150, "sodium": 1150, "carbs": 137.5,
                     "fiber": 14, "sugars": 0, "added_sugar": 25, "protein": 50, "vit_d": 10, "calcium": 650,
                     "iron": 9, "potassium": 2350, "magnesium": 210, "zinc": 5.5, "vit_c": 90, "vit_a": 450,
                     "epa_dha": 250})
    assert all(v == 50 for k, v in dv.items() if k not in ("protein", "vit_c")), dv
    assert dv["protein"] == 100 and dv["vit_c"] == 100
    assert "trans_fat" not in dv and "sugars" not in dv  # no Daily Value exists for these


def test_steps_walk_the_line_base_first(plate):
    groups = steps(plate)
    first = groups[0]["items"][0]
    assert groups[0]["station"] == "Simply Prepared" and first["name"] == "Saffron Rice"
    shawarma = next(i for g in groups for i in g["items"] if i["name"] == "Chicken Shawarma")
    assert shawarma["servings"] == 2 and shawarma["portion"] == "2 portions"


def test_payload_speaks_per_meal(plate):
    out = build_payload(plate, 1, target_for("lunch"))
    assert out["why"][0].endswith("g protein")
    assert all("vitamin c" not in w for w in out["why"])  # "vitamin C", not "vitamin c"
    assert out["chips"] == sorted(out["chips"], key=lambda c: -c["pct"])
    assert out["score"] <= 100 and set(out["sub"]) == {"macros", "micros", "clean"}


def test_chips_mark_estimated_nutrients():
    c = chips({"fiber": 14, "potassium": 470, "iron": 1.8, "calcium": 130, "vit_d": 2, "magnesium": 400,
               "zinc": 1, "vit_c": 45, "vit_a": 90, "epa_dha": 50})
    by = {x["key"]: x for x in c}
    assert by["magnesium"]["est"] and not by["fiber"]["est"]
    assert c[0]["key"] == "magnesium" and c[0]["pct"] == 95


def test_item_payload_explains_label_fixes(food):
    salsa = food("Salsa", "Condiments and Spreads")
    out = item_payload(salsa, "tomatoes, onion, salt")
    assert any(n.startswith("Label corrected") and "iron" in n for n in out["notes"])
    assert out["label"]["iron"] < 1 and out["ingredients"] == "tomatoes, onion, salt"
    assert out["processing"] in ("Minimally processed", "Processed", "Ultra-processed")
