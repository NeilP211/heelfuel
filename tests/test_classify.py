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
