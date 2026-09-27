from heelfuel.classify import _upf, parse_serving, sanitize
from heelfuel.model import Nutrition


def test_parse_serving():
    half = chr(0x00BD)
    assert parse_serving(f"{half} cup") == (0.5, "cup")
    assert parse_serving("0.75 cup") == (0.75, "cup")
    assert parse_serving("3 slices") == (3.0, "slice")
    assert parse_serving("2 Tbsp") == (2.0, "tbsp")
    assert parse_serving("12 floz") == (12.0, "floz")
    assert parse_serving("4 oz") == (4.0, "oz")
    assert parse_serving("1 Serving") == (1.0, "serving")
    assert parse_serving("1 each") == (1.0, "each")
    assert parse_serving("1 1/2 cup") == (1.5, "cup")


def test_roles(food):
    assert food("Chicken Shawarma", "Simply Prepared").role == "protein"
    rice = food("Saffron Rice", "Simply Prepared")
    assert (rice.role, rice.kind) == ("carb", "grain")
    assert food("Roasted Cauliflower", "Simply Prepared").role == "produce"
    assert food("Red Grapes", "Salad Bar").kind == "fruit"
    assert food("Pancake Syrup").role == "excluded"
    assert food("Assorted Cookies", "Bakery").kind == "dessert"
    y = food("Plain Greek Yogurt", "Salad Bar")
    assert (y.role, y.kind) == ("protein", "dairy")
    assert food("Froot Loops®", "Cereal").kind == "cereal"
    assert food("Skim Milk", "Beverages").kind == "milk"
    assert food("Southwest Black Beans").kind == "legume"


def test_dyes_are_detected_and_named(food):
    wrap = food("Spinach Wrap", "Deli")
    assert {"Yellow 5", "Blue 1"} <= set(wrap.dyes)
    loops = food("Froot Loops®", "Cereal")
    assert "Red 40" in loops.dyes
    assert loops.pho  # partially hydrogenated oil


def test_no_false_positives_on_clean_whole_food(food):
    chicken = food("Chipotle Lime Chicken", "Simply Prepared Griddle")
    assert chicken.dyes == () and chicken.red_flags == () and chicken.emulsifiers == ()
    assert chicken.processed_meat_g == 0
    assert chicken.upf == 0


def test_thiamine_mononitrate_is_not_a_cured_meat(food):
    waffle = food("Waffle", "Waffle Bar")  # enriched flour lists thiamine mononitrate
    assert waffle.processed_meat_g == 0


def test_processed_meat_grams(food):
    bacon = food("Bacon")
    assert bacon.processed_meat_g == 17  # "17 g" serving
    ham = food("Sliced Ham", "Deli")
    assert 40 <= ham.processed_meat_g <= 80


def test_implausible_labels_are_flagged(food):
    assert food("Swiss Cheese", "Deli").suspect  # 1,780 kcal per slice
    assert food("Baby Carrots", "Salad Bar").suspect  # 170 kcal per half cup
    assert not food("Chicken Shawarma", "Simply Prepared").suspect


def test_sanitize_clamps_impossible_saturated_fat(food):
    carrots = food("Roasted Harissa Carrots")  # label: 0 g fat, 27 g saturated fat
    assert carrots.nutrition.sat_fat == 0
    assert carrots.fixes


def test_sanitize_leaves_good_labels_alone():
    n = Nutrition(kcal=100, fat=5, sat_fat=2, carbs=10, fiber=2, protein=5)
    out, fixes = sanitize(n)
    assert out is n and fixes == []


def test_dairy_trans_fat_is_not_industrial(food):
    mash = food("Cheddar-Chive Mashed Potatoes")  # 1 g trans from cheese
    from heelfuel.classify import VI
    assert mash.nutrition.trans_fat == 1
    assert mash.vec[VI["trans_fat"]] < 0.2  # scored at a tenth


def test_processing_score_disaggregates_dishes():
    dish = ("CANNED BEAN BLACK [Black Beans, Water, Salt], WATER, TOMATO, ONION [Onions], JALAPENO [Hot Peppers], "
            "LIME JUICE [Lime Juice], BASE VEGETABLE [MALTODEXTRIN, HYDROLYZED CORN PROTEIN, YEAST EXTRACT, "
            "NATURAL FLAVORS, MODIFIED CORNSTARCH], KOSHER SALT [Salt]").lower()
    u, markers = _upf(dish)
    assert u < 0.15
    assert "glucose syrups" in markers  # still reported, just weighted by how much of the dish it is
    product = ("CHEESE COTTAGE [Cultured Nonfat Milk, Maltodextrin, Carrageenan, Mono and Diglycerides, "
               "Guar Gum, Natural Flavors]").lower()
    u2, _ = _upf(product)
    assert u2 == 1.0
    assert _upf("")[0] == 0


def test_portion_caps(food):
    assert food("Chipotle Lime Chicken").max_servings == 3  # 100 kcal portions
    assert food("Chicken Shawarma").max_servings == 2
    assert food("Classic Cheeseburger", "The Griddle").max_servings == 1
    assert food("Saffron Rice").max_servings == 3


def test_only_industrial_trans_fat_is_called_out(food):
    from heelfuel.builds import TEMPLATE_BY_KEY, Build
    from heelfuel.explain import build_payload
    from heelfuel.score import item_vec, score_meal, target_for, vec_sum
    mash = food("Cheddar-Chive Mashed Potatoes")
    chicken = food("Chicken Shawarma", "Simply Prepared")
    picks = (("protein", chicken, 2), ("starch", mash, 2), ("veg", food("Green Beans"), 1))
    vec = vec_sum(item_vec(f, s) for _, f, s in picks)
    b = Build(TEMPLATE_BY_KEY["power_plate"], picks, vec, score_meal(vec, target_for("lunch")))
    out = build_payload(b, 1, target_for("lunch"))
    assert not any("trans fat" in c.lower() for c in out["tradeoffs"])
    assert not mash.industrial_trans and food("Froot Loops\u00ae", "Cereal").industrial_trans


def _label(name, serving="1 each", station="X", **n):
    from heelfuel.classify import analyze
    from heelfuel.model import MenuItem, Nutrition, Recipe
    base = dict(kcal=100.0, protein=2.0, carbs=20.0, fat=1.0)
    base.update(n)
    return analyze(MenuItem("1", name, station), Recipe("1", name, serving=serving, nutrition=Nutrition(**base)))


def test_impossible_iron_is_replaced_with_a_typical_amount():
    salsa = _label("Salsa", "2 Tbsp", kcal=10, carbs=2, fat=0, protein=0, iron=93)
    assert salsa.nutrition.iron < 1 and any("93 mg iron" in x for x in salsa.fixes)
    cereal = _label("Frosted Mini Wheats", "1.45 oz", "Cereal", kcal=140, carbs=34, iron=11.3)
    assert cereal.nutrition.iron == 11.3  # fortified cereal really has that much


def test_vitamin_d_entered_as_iu_is_converted():
    ham = _label("Sliced Ham", "3 slices", "Deli", kcal=110, protein=16, carbs=2, fat=4, vit_d=13.9)
    assert ham.nutrition.vit_d < 1
    salmon = _label("Grilled Salmon", "4 oz", kcal=230, protein=25, carbs=0, fat=14, vit_d=12)
    assert salmon.nutrition.vit_d == 12


def test_fruit_label_with_impossible_calories_is_flagged():
    apples = _label("Roasted Cinnamon Apples", "\u00bc cup", kcal=560, carbs=133, fat=1.5, protein=4)
    assert "per cup of fruit" in apples.suspect
    grapes = _label("Red Grapes", "\u00bd cup", kcal=52, carbs=14, fat=0, protein=0.5)
    assert not grapes.suspect


def test_flavored_oatmeal_is_a_carb_not_fruit():
    oats = _label("Apple Cinnamon Oatmeal", "8 floz", kcal=160, carbs=30, fat=2.5, protein=5)
    assert oats.role == "carb" and oats.kind != "fruit"


def test_milk_and_yogurt_micros_use_the_real_portion():
    milk = _label("Skim Milk", "1 cup", "Beverages", kcal=80, protein=8, carbs=12, fat=0)
    assert milk.est["magnesium"] > 20 and milk.est["vit_a"] > 100
