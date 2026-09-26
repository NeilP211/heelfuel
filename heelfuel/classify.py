"""Turn a menu item plus its nutrition label into a Food: role, flags, additives and estimates.

Everything the scorer needs per serving is precomputed here into `Food.vec` so the optimizer
can sum thousands of candidate meals quickly.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from .foods import FoodRef, match_foods
from .model import MenuItem, Nutrition, Recipe

# ---------------------------------------------------------------- serving sizes

_UNICODE_FRACTIONS = {
    chr(0x00BD): 0.5, chr(0x00BC): 0.25, chr(0x00BE): 0.75,
    chr(0x2153): 1 / 3, chr(0x2154): 2 / 3, chr(0x215B): 0.125,
}
_UNITS = [
    ("floz", r"fl\.?\s*oz|floz|fluid ounces?"),
    ("cup", r"cups?\b"),
    ("tbsp", r"tbsp|tbs\b|tablespoons?"),
    ("tsp", r"tsp|teaspoons?"),
    ("oz", r"oz\b|ounces?"),
    ("lb", r"lbs?\b|pounds?"),
    ("g", r"g\b|grams?"),
    ("slice", r"slices?"),
    ("serving", r"servings?"),
    ("each", r"each|ea\b|pieces?|patty|patties|container|sandwich|roll|bar|link|links|scoops?"),
]
UNIT_GRAMS = {"oz": 28.35, "g": 1.0, "lb": 453.6}
UNIT_CUPS = {"cup": 1.0, "tbsp": 1 / 16, "tsp": 1 / 48, "floz": 1 / 8}


def parse_serving(text: str) -> tuple[float, str]:
    """'½ cup' -> (0.5, 'cup'); '3 slices' -> (3, 'slice'); '1 Serving' -> (1, 'serving')."""
    s = (text or "").strip().lower()
    for ch, val in _UNICODE_FRACTIONS.items():
        s = s.replace(ch, f" {val} ")
    qty = 0.0
    rest = s
    while True:
        m = re.match(r"\s*(\d+/\d+|\d*\.\d+|\d+)", rest)
        if not m:
            break
        tok = m.group(1)
        if "/" in tok:
            a, b = tok.split("/")
            qty += float(a) / float(b) if float(b) else 0.0
        else:
            qty += float(tok)
        rest = rest[m.end():]
    rest = rest.strip()
    unit = "other"
    for name, rx in _UNITS:
        if re.match(rx, rest):
            unit = name
            break
    return (qty if qty > 0 else 1.0), unit


# ---------------------------------------------------------------- ingredient scans


def _rx(p: str) -> re.Pattern:
    return re.compile(p, re.I)


DYES = {
    "Red 40": _rx(r"\bred\s*(?:no\.?\s*|#\s*)?40\b|allura red"),
    "Yellow 5": _rx(r"\byellow\s*(?:no\.?\s*|#\s*)?5\b|tartrazine"),
    "Yellow 6": _rx(r"\byellow\s*(?:no\.?\s*|#\s*)?6\b|sunset yellow"),
    "Blue 1": _rx(r"\bblue\s*(?:no\.?\s*|#\s*)?1\b|brilliant blue"),
    "Blue 2": _rx(r"\bblue\s*(?:no\.?\s*|#\s*)?2\b|indigo carmine|indigotine"),
    "Green 3": _rx(r"\bgreen\s*(?:no\.?\s*|#\s*)?3\b|fast green"),
    "Citrus Red 2": _rx(r"citrus red"),
    "Orange B": _rx(r"\borange b\b"),
}
ARTIFICIAL_COLOR = _rx(r"artificial colou?r(s|ing)?\b|colou?rs? added|\bfd&c\b")
RED_FLAGS = {
    "Red 3": _rx(r"\bred\s*(?:no\.?\s*|#\s*)?3\b|erythrosine"),
    "Titanium dioxide": _rx(r"titanium dioxide"),
    "Potassium bromate": _rx(r"potassium bromate|bromated"),
    "BHA": _rx(r"\bbha\b|butylated hydroxyanisole"),
    "Propylparaben": _rx(r"propyl ?paraben"),
    "Azodicarbonamide": _rx(r"azodicarbonamide"),
    "Brominated vegetable oil": _rx(r"brominated vegetable oil"),
}
EMULSIFIERS = {
    "CMC (cellulose gum)": (_rx(r"cellulose gum|carboxymethyl ?cellulose|carboxymethylcellulose"), 2.0),
    "Polysorbate 80": (_rx(r"polysorbate"), 2.0),
    "Carrageenan": (_rx(r"carrageenan"), 2.0),
    "Mono- and diglycerides": (_rx(r"mono-?\s*(?:and|&)\s*-?\s*di-?\s*glycerides|monoglycerides|diglycerides"), 1.0),
    "DATEM": (_rx(r"\bdatem\b|diacetyl tartaric"), 1.0),
}
SWEETENERS = {
    "Sucralose": _rx(r"sucralose"),
    "Aspartame": _rx(r"aspartame"),
    "Acesulfame K": _rx(r"acesulfame"),
    "Saccharin": _rx(r"saccharin"),
    "Neotame": _rx(r"neotame|advantame"),
}
PHO = _rx(r"partially hydrogenated")
PHOSPHATE = _rx(r"phosphate")
CARAMEL = _rx(r"caramel colou?r")
SEED_OIL = _rx(r"soybean oil|canola oil|corn oil|cottonseed oil|sunflower oil|safflower oil|vegetable oil|rapeseed oil|grapeseed oil|rice bran oil|vegetable shortening|soybean and/or|canola and/or")
SUGAR_INGREDIENT = _rx(r"\bsugar\b|cane sugar|brown sugar|corn syrup|high fructose|\bsyrup\b|\bhoney\b|molasses|dextrose|agave|juice concentrate|\bsucrose\b|invert sugar|maltose|caramel\b(?! colou?r)|evaporated cane")

# NOVA ultra-processing markers (Monteiro 2019): class -> [(pattern, weight)]
UPF_MARKERS = {
    "flavorings": [(_rx(r"natural flavou?r"), 0.5), (_rx(r"artificial flavou?r"), 1.0)],
    "flavor enhancers": [(_rx(r"monosodium glutamate|\bmsg\b|disodium (?:inosinate|guanylate)|yeast extract|autolyzed yeast"), 1.0)],
    "colors": [(ARTIFICIAL_COLOR, 1.0), (CARAMEL, 1.0), (_rx(r"titanium dioxide"), 1.0)] + [(rx, 1.0) for rx in DYES.values()],
    "emulsifiers": [(_rx(r"mono-?\s*(?:and|&)\s*-?\s*di-?\s*glycerides|monoglycerides|diglycerides|polysorbate|\bdatem\b|stearoyl lactylate"), 1.0), (_rx(r"lecithin"), 0.5)],
    "thickeners": [(_rx(r"carrageenan|cellulose gum|carboxymethyl|methylcellulose"), 1.0), (_rx(r"modified (?:food |corn |tapioca |potato |wheat )?starch|xanthan|guar gum|locust bean|gellan"), 0.5)],
    "non-sugar sweeteners": [(rx, 1.0) for rx in SWEETENERS.values()],
    "glucose syrups": [(_rx(r"high fructose corn syrup|corn syrup|glucose syrup|maltodextrin|dextrose|invert sugar|\bfructose\b"), 1.0)],
    "modified fats": [(_rx(r"hydrogenated|interesterified"), 1.0)],
    "protein isolates": [(_rx(r"protein isolate|isolated soy|soy protein concentrate|textured (?:vegetable|soy|wheat) protein|mechanically separated|hydrolyzed (?:soy|corn|wheat|vegetable|plant) protein"), 1.0)],
    "preservatives": [(_rx(r"sodium benzoate|potassium benzoate|potassium sorbate|sorbic acid|calcium propionate|sodium propionate|\bbha\b|\bbht\b|tbhq|sodium nitrite|potassium nitrite|sodium erythorbate|propyl ?paraben|sodium diacetate"), 0.5)],
}
UPF_FULL = 3.0  # weighted marker total that counts as fully ultra-processed


def top_level_ingredients(ing: str, n: int = 3) -> list[str]:
    """First n comma-separated ingredients, ignoring commas inside () or []."""
    out, depth, cur = [], 0, []
    for ch in ing:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth = max(0, depth - 1)
        if ch == "," and depth == 0:
            out.append("".join(cur).strip())
            cur = []
            if len(out) >= n:
                break
        else:
            cur.append(ch)
    if len(out) < n and "".join(cur).strip():
        out.append("".join(cur).strip())
    return out[:n]


# ---------------------------------------------------------------- name patterns

FRIED = _rx(r"\bfried\b|\bfries\b|tater tots?|\btots\b|crispy|\bchips\b|nuggets?|\btenders?\b|popcorn chicken|\bwings?\b|hash ?browns?|onion rings?|tempura|battered|breaded|fritters?|egg ?rolls?|spring rolls?|churros?|donuts?|doughnuts?|funnel cake")
NOT_FRIED = _rx(r"stir[- ]?fr|fried rice|refried|air[- ]fried|oven[- ]fried")
FRIED_INGREDIENT = _rx(r"par[- ]?fried|pre[- ]?fried|fried in|oil for frying")

PROCESSED_MEAT = _rx(r"bacon|\bham\b|salami|pepperoni|sausage|hot ?dogs?|frankfurters?|bratwurst|kielbasa|chorizo|pastrami|corned beef|bologna|prosciutto|capicola|roast beef|jerky|\bspam\b|andouille|pancetta|lunch ?meat|cold cuts?")
PROCESSED_POULTRY = _rx(r"sliced turkey|deli turkey|smoked turkey|turkey (?:bacon|sausage|ham|pastrami)|chicken sausage")
PLANT_BASED = _rx(r"vegan|impossible|beyond|plant[- ]based|meatless|\bsoy\b|tofu")
MIXED_DISH = _rx(r"pizza|omelet|penne|pasta|biscuit|quesadilla|flatbread|calzone|\bbowl\b|salad|soup|gravy|fried rice|\bmac\b|casserole|bake\b")
PROCESSED_MEAT_KCAL100 = {
    "bacon": 541, "ham": 145, "salami": 336, "pepperoni": 504, "sausage": 300, "bratwurst": 297,
    "chorizo": 455, "hot dog": 290, "roast beef": 120, "turkey": 104, "bologna": 310,
}

CONDIMENT = _rx(r"\bsauce\b|dressing|vinaigrette|\bmayo|mayonnaise|ketchup|mustard(?! greens)|\branch\b|syrup|\bhoney\b(?! (?:bbq|barbecue|glazed|garlic|lime|sriracha|mustard chicken|chicken))|jelly|\bjam\b|preserves|compote|\bspread\b|butter(?!milk|nut)|cream cheese|creamer|gravy|\bsalsa\b|pico de gallo|sour cream|\bqueso\b|whipped topping|sprinkles|crumbs|soy sauce|wasabi|pickled|pickles?\b|hot sauce|sriracha|siracha|vinegar|\boils?\b|olives?\b|banana peppers|jalapeno|croutons|bacon pieces|brown sugar|tzatziki|chutney|relish|aioli|\bglaze\b|\bdip\b|seasoning|lemon wedges?|lime wedges?|raisins|dried cranberries|craisins|\bpesto\b")
PASTA_SAUCE = _rx(r"marinara|meat sauce|tomato sauce|pomodoro|arrabbiata|bolognese")
FAT_EXTRA = _rx(r"guacamole|avocado|hummus|sunflower seeds?|pumpkin seeds?|almonds?|peanut butter|sun ?butter|walnuts?|pecans?|cashews?|\bnuts\b|olives?\b|trail mix")
CHEESE = _rx(r"cheese|cheddar|mozzarella|parmesan|feta|provolone|monterey|pepper jack|swiss|\bbrie\b|gouda")
DESSERT = _rx(r"cookie|brownie|\bcakes?\b|cupcake|\bpies?\b|donut|doughnut|muffin|scone|croissant|danish|pastry|pastries|pudding|ice cream|sorbet|gelato|frozen yogurt|candy|gummy|m&m|\btreats?\b|crinkle|fudge|churro|cobbler|\bcrisp\b|\bbars?\b|squares|\bloaf\b|banana bread|coffee cake|cinnamon roll|sweet roll|macaron|\btarts?\b|cheesecake|marshmallow|snickerdoodle|red velvet|chocolate chip")
BEVERAGE = _rx(r"juice|lemonade|\bsoda\b|\bcola\b|pepsi|coke|dr\.? pepper|mountain dew|mtn dew|sprite|root beer|ginger ale|cheerwine|starry|sunkist|gatorade|powerade|\btea\b|coffee|cocoa|cider|\bwater\b|bubbly|seltzer|energy drink|kombucha|fruit punch")
MILK = _rx(r"\bmilk\b|soymilk|soy milk|peamilk|pea milk|oatmilk|oat milk")
SMOOTHIE = _rx(r"smoothie")
JUICE = _rx(r"juice|lemonade|fruit punch|cider")

VEG = _rx(r"broccoli|green beans?|cauliflower|spinach|kale|collards?|brussels|squash|zucchini|carrots?|peppers?|mushrooms?|bok choy|cabbage|slaw|salad mix|spring mix|lettuce|greens|tomato(?:es)?|cucumbers?|onions?|asparagus|eggplant|okra|beets?|radish|celery|arugula|romaine|vegetables?|veggies?|ratatouille|scallions?|sprouts|jalapeno slaw")
FRUIT = _rx(r"apples?(?! jack)|applesauce|bananas?|berries|strawberr|blueberr|raspberr|blackberr|melon|cantaloupe|honeydew|watermelon|grapes?(?!fruit)|grapefruit|oranges?|clementine|pineapples?|mango|peach|pears?\b|plums?\b|kiwi|cherr(?:y|ies)|fruit|pomegranate|apricot|papaya")
STARCHY_VEG = _rx(r"sweet potato|potato|\bcorn\b(?! syrup| tortilla| chip| bread|bread)|\bpeas\b|plantain|\byams?\b|hash|\btots\b|fries")
LEGUME = _rx(r"black beans?|kidney beans?|pinto|white beans?|cannellini|navy beans?|refried|red beans|(?<!green )(?<!string )\bbeans\b|lentils?|chickpeas?|garbanzo|edamame")
WHOLE_GRAIN = _rx(r"whole wheat|whole grain|brown rice|wild rice|quinoa|farro|barley|bulgur|\boats?\b|oatmeal|popcorn|steel cut|multigrain|whole-wheat|freekeh")
BREAD = _rx(r"\bbread\b|bagel|\brolls?\b|\bbuns?\b|\bwraps?\b|tortilla(?! chips)|\bpita\b|biscuit|croissant|\btoast\b|english muffin|\bnaan\b|flatbread|sourdough|hoagie")
SANDWICH = _rx(r"(?<!bean )(?<!veggie )burger(?! bun| patty)|sandwich|\bsub\b|\bmelt\b|panini|quesadilla|burrito(?! bowl)|\btacos?\b|hot ?dog|bratwurst.*roll|cheeseburger")
PIZZA = _rx(r"pizza|cheese bread|flatbread")
PASTA = _rx(r"pasta|penne|spaghetti|noodles?|macaroni|ravioli|linguine|rotini|lo mein|\bziti\b|lasagna|tortellini")
RICE = _rx(r"\brice\b")
SOUP = _rx(r"soup|chili|stew|chowder|bisque")
POTATO = _rx(r"potato|hash ?brown|\btots\b|fries")
RAW_TOPPING = _rx(r"salad bar|sushi|create|deli|burrito|build your own|made-to-order|toppings")
LEAFY = _rx(r"lettuce|spring mix|salad mix|mixed greens|romaine|arugula|baby spinach|field greens|kale salad")
SUSHI = _rx(r"sushi|maki|(?:cucumber|avocado|california|tuna|salmon|shrimp|spicy|veggie|vegetable) roll")
BREAKFAST_ONLY = _rx(r"waffle|pancake|french toast|syrup|oatmeal|\boats\b|\bgrits\b|granola|overnight|breakfast|hash ?browns?|\bbiscuit|sausage gravy|cereal")
CEREAL_NAMES = _rx(r"cheerios|flakes|loops|krispies|puffs|charms|apple jacks|crunch|grahams|mini wheats|chex|granola|cereal")

FISH_OILY = _rx(r"salmon|\btuna\b|sardine|mackerel|trout|herring")
FISH = _rx(r"tilapia|\bcod\b|pollock|catfish|\bfish\b|mahi|swordfish|haddock|flounder|swai")
SHELLFISH = _rx(r"shrimp|crab|lobster|scallop|clam|mussel|oyster|calamari|scampi")
EGG = _rx(r"\beggs?\b|omelet|frittata|quiche")
POULTRY = _rx(r"chicken|turkey")
RED_MEAT = _rx(r"beef|steak|\blamb\b|(?<!bean )(?<!veggie )(?<!turkey )burger(?! bun| patty)|brisket|meatball|gyro|meat sauce|chili con carne|barbacoa|veal|cheeseburger")
PORK = _rx(r"pork|\bham\b|bacon|sausage|carnitas|bratwurst|salami|pepperoni|chorizo")
DAIRY_PROTEIN = _rx(r"greek yogurt|cottage cheese|\byogurt\b|skyr|\bmilk\b")
SOY = _rx(r"tofu|edamame|tempeh|\bsoy\b(?! sauce)|soymilk")
PLANT_MEAT = _rx(r"impossible|beyond|vegan (?:chorizo|sausage|burger|chicken|nuggets|meatballs?)|plant[- ]based|soy nuggets|soy bites|black bean burger|veggie burger")


# ---------------------------------------------------------------- the Food record

# Order of the per-serving vector every candidate meal sums over.
V_FIELDS = (
    "kcal", "protein", "carbs", "fat", "fiber", "sodium", "sat_fat", "trans_fat", "added_sugar",
    "calcium", "iron", "potassium", "vit_d", "magnesium", "zinc", "vit_c", "vit_a", "epa_dha",
    "produce_cups", "upf_kcal", "fried_kcal", "seed_oil_kcal", "processed_meat_g", "quality_carbs",
    "pq_protein", "dairy_cups", "slow_protein", "sugars", "cholesterol",
)
VI = {k: i for i, k in enumerate(V_FIELDS)}


@dataclass(eq=False)
class Food:
    rid: str
    name: str
    station: str
    serving: str
    nutrition: Nutrition
    role: str                 # protein / carb / produce / extra / excluded
    kind: str                 # finer type, e.g. poultry, whole_grain, veg, fruit, milk, cheese, fat, sauce
    tags: frozenset = frozenset()
    qty: float = 1.0
    unit: str = "each"
    added_sugar: float = 0.0
    added_sugar_estimated: bool = False
    dyes: tuple = ()
    red_flags: tuple = ()
    emulsifiers: tuple = ()   # ((name, raw points), ...)
    sweeteners: tuple = ()
    pho: bool = False
    phosphates: bool = False
    caramel: bool = False
    seed_oil: bool = False
    upf: float = 0.0
    upf_markers: tuple = ()
    fried: bool = False
    processed_meat_g: float = 0.0
    produce_cups: float = 0.0
    protein_quality: float = 0.75
    carb_quality: float = 0.5
    dairy_cups: float = 0.0
    slow_protein: float = 0.0
    est: dict = field(default_factory=dict)
    suspect: str = ""
    exclude_reason: str = ""
    fixes: tuple = ()
    base: str = ""            # main food it is made of ("chicken", "black beans"...), for spotting doubles
    max_servings: int = 1
    allergens: tuple = ()
    props: tuple = ()
    vec: tuple = ()

    @property
    def usable(self) -> bool:
        return self.role != "excluded" and not self.suspect


def _grams_for(ref: FoodRef, qty: float, unit: str, kcal_share: float, low_density: bool,
               protein_share: float = 0.0) -> float:
    """Best guess at grams of `ref` in one serving."""
    by_serving: Optional[float] = None
    if unit in UNIT_GRAMS:
        by_serving = qty * UNIT_GRAMS[unit]
    elif unit in UNIT_CUPS and ref.g_per_cup:
        by_serving = qty * UNIT_CUPS[unit] * ref.g_per_cup
    by_kcal = kcal_share / (ref.kcal / 100.0) if ref.kcal else None
    if ref.protein and protein_share > 0:
        # Meat, fish, eggs, tofu: the label's protein is the most reliable portion signal,
        # since sauces and sides inflate calories but add little protein.
        by_protein = protein_share / (ref.protein / 100.0)
        return min(by_protein, by_kcal) if by_kcal else by_protein
    if low_density:
        # Cooking oil inflates a vegetable's calories, so trust the stated volume when there is one.
        if by_serving is not None:
            return by_serving
        return (by_kcal or 0.0) * 0.6
    if by_kcal is None:
        return by_serving or 0.0
    if by_serving is not None and 0.5 * by_kcal <= by_serving <= 2 * by_kcal:
        return (by_serving + by_kcal) / 2
    return by_kcal * 0.85


def estimate_micros(name: str, qty: float, unit: str, kcal: float, mixed: bool,
                    produce: bool = True, protein: float = 0.0) -> tuple[dict, list[FoodRef], float]:
    """(estimated micronutrients per serving, matched foods, grams of the main food)."""
    refs = match_foods(name)
    est = {"magnesium": 0.0, "zinc": 0.0, "vit_c": 0.0, "vit_a": 0.0, "epa_dha": 0.0}
    if not refs or kcal <= 0:
        return est, refs, 0.0
    shares = [1.0] if len(refs) == 1 else [0.6, 0.4]
    frac = 0.6 if mixed else 0.85
    main_grams = 0.0
    for ref, share in zip(refs, shares):
        grams = _grams_for(ref, qty * (share if len(refs) > 1 else 1.0), unit, kcal * share * frac / 0.85, ref.kcal < 60,
                           protein_share=protein * (0.9 if ref is refs[0] else 0.3) * (0.8 if mixed else 1.0))
        grams = min(grams, 450.0)
        if ref.kcal < 60 and not produce:
            grams = min(grams, 40.0)  # "Spinach Wrap" is flour with a little spinach in it
        if ref is refs[0]:
            main_grams = grams
        for k in est:
            est[k] += grams / 100.0 * getattr(ref, k)
    return {k: round(v, 2) for k, v in est.items()}, refs, main_grams


def produce_cups_for(refs: list[FoodRef], qty: float, unit: str, kcal: float, half: bool) -> float:
    ref = refs[0] if refs else None
    g_per_cup = (ref.g_per_cup if ref and ref.g_per_cup else 150.0)
    if unit in UNIT_CUPS:
        cups = qty * UNIT_CUPS[unit]
    elif unit in UNIT_GRAMS:
        cups = qty * UNIT_GRAMS[unit] / g_per_cup
    elif ref and ref.kcal:
        grams = kcal / (ref.kcal / 100.0) * (0.6 if ref.kcal < 60 else 0.9)
        cups = grams / g_per_cup
    else:
        cups = max(0.05, min(0.5, kcal / 50.0))
    if ref and ref.leafy_raw:
        cups = min(cups, 2.0) * 0.5  # 1 cup of raw leafy greens counts as half a cup-equivalent
    if half:
        cups *= 0.5  # starchy vegetables and beans get half credit
    return round(max(0.0, min(cups, 2.0)), 3)


def suspect_reason(n: Nutrition, qty: float, unit: str, name: str, kind: str, role: str) -> str:
    kcal = n.kcal
    if kcal > 1500:
        return f"{kcal:.0f} kcal in one serving"
    if unit == "tbsp" and qty and kcal / qty > 130:
        return f"{kcal / qty:.0f} kcal per tablespoon"
    if unit == "slice" and CHEESE.search(name) and kcal > 400:
        return f"{kcal:.0f} kcal in one cheese slice"
    est = 4 * n.protein + 4 * n.carbs + 9 * n.fat
    top = max(kcal, est)
    if top >= 60 and abs(kcal - est) / top > 0.5:
        return f"label says {kcal:.0f} kcal but its macros add up to {est:.0f}"
    if n.protein * 4 > kcal * 1.1 + 5:
        return "more protein than the calories allow"
    if role in ("produce", "carb") and VEG.search(name) and not STARCHY_VEG.search(name) \
            and not NOT_PRODUCE.search(name) and not LEGUME.search(name) and unit in UNIT_CUPS:
        cups = qty * UNIT_CUPS[unit]
        if cups > 0 and (n.carbs / cups > 30 or kcal / cups > 500):
            return f"{n.carbs / cups:.0f} g carbs and {kcal / cups:.0f} kcal per cup for a vegetable"
    if kcal == 0 and role in ("protein", "carb", "extra") and kind not in ("sauce",):
        return "zero calories listed"
    return ""


def split_components(text: str) -> list[str]:
    """Top-level comma-separated components, ignoring commas inside () or []."""
    out, depth, cur = [], 0, []
    for ch in text:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth = max(0, depth - 1)
        if ch == "," and depth == 0:
            if "".join(cur).strip():
                out.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    if "".join(cur).strip():
        out.append("".join(cur).strip())
    return out


def _inner(component: str) -> str:
    i = component.find("[")
    if i < 0:
        return component
    j = component.rfind("]")
    return component[i + 1:(j if j > i else len(component))]


def unwrap_product(text: str) -> Optional[str]:
    """If the text is one purchased product ('CHEESE COTTAGE LOW FAT [milk, ...]'), return its inner list."""
    comps = split_components(text)
    if len(comps) == 1 and "[" in comps[0]:
        return _inner(comps[0])
    if len(comps) == 2 and "[" not in comps[0] and len(comps[0].split()) <= 2 and "[" in comps[1]:
        return _inner(comps[1])
    return None


def _marker_total(text: str) -> tuple[float, list[str]]:
    total, found = 0.0, []
    for cls, pats in UPF_MARKERS.items():
        w = max((wt for rx, wt in pats if rx.search(text)), default=0.0)
        if w:
            total += w
            found.append(cls)
    return total, found


def _upf(ing: str) -> tuple[float, tuple]:
    """0-1 ultra-processing score (RESEARCH.md 3.11).

    A single purchased product is scored on its own marker count. A dish cooked on site is
    disaggregated the way NOVA studies do it: each component is scored on its own, weighted by its
    place in the descending-by-weight ingredient list, so a 2% flavor base doesn't make a pot of
    black beans ultra-processed.
    """
    if not ing.strip():
        return 0.0, ()
    product = unwrap_product(ing)
    if product is not None:
        total, found = _marker_total(product)
        return min(1.0, total / UPF_FULL), tuple(found)
    comps = split_components(ing)
    bracketed = sum("[" in c for c in comps)
    if len(comps) <= 1 or not (bracketed >= 2 or (bracketed >= 1 and len(comps) >= 3)):
        total, found = _marker_total(ing)
        return min(1.0, total / UPF_FULL), tuple(found)
    weights = [0.6 ** i for i in range(len(comps))]
    norm = sum(weights)
    score, found_all = 0.0, []
    for w, comp in zip(weights, comps):
        total, found = _marker_total(comp)
        score += (w / norm) * min(1.0, total / 2.0)
        for f in found:
            if f not in found_all:
                found_all.append(f)
    return min(1.0, score), tuple(found_all)


FOODISH = _rx(r"oats?\b|chicken|beef|pork|\bcake\b|bread|\brice\b|tofu|pudding|salad|glazed|marinated|crusted|rubbed|smoked|braised|roasted|grilled|baked|wings?\b|\bribs?\b|strawberry overnight")
CEREAL_BRANDS = _rx(r"cheerios|froot loops|rice krispies|cocoa puffs|lucky charms|apple jacks|golden grahams|mini wheats|\bchex\b|frosted flakes|corn flakes|raisin bran|special k|cinnamon toast crunch|granola|\bcereal\b")
TOPPING = _rx(r"pieces|\bbits\b|crumbles|croutons|sprinkles|crumbs")
SNACK = _rx(r"\bchips\b|pretzels?|crackers?|popcorn|goldfish")
CHEESE_ITEM = _rx(r"^(?:shredded |sliced |grated |vegan |vegan sliced |vegan american sliced |fresh )?(?:cheddar |mozzarella |parmesan |feta |provolone |monterey jack |pepper jack |swiss |american |colby |gouda |brie |blue |jack )?(?:cheese)(?: crumbles| slices?)?$|^(?:shredded|sliced) (?:cheddar|mozzarella|swiss|provolone)$")
NOT_PRODUCE = _rx(r"soup|chowder|bisque|\broll\b|sushi|parmesan|parmigiana|casserole|bake\b|lasagna|fried|tempura|pizza|pasta|\brice\b|bread|wrap|melt|sandwich|burger|quesadilla|taco|burrito")


def _classify_role(name: str, station: str, n: Nutrition, low: str) -> tuple[str, str, str]:
    """(role, kind, exclude reason). Checks run from most to least specific."""
    st = station.lower()
    kcal = max(n.kcal, 1.0)
    p_share = n.protein * 4 / kcal
    c_share = n.carbs * 4 / kcal
    f_share = n.fat * 9 / kcal
    animal_or_soy = bool(FISH_OILY.search(low) or FISH.search(low) or SHELLFISH.search(low) or EGG.search(low)
                         or POULTRY.search(low) or RED_MEAT.search(low) or PORK.search(low) or SOY.search(low)
                         or PLANT_MEAT.search(low))
    sandwich_or_pizza = bool(SANDWICH.search(low) or PIZZA.search(low))

    # A zero-calorie row on something that is obviously food is a data error, not a free lunch:
    # give it a real role so the plausibility check flags it.
    if n.kcal == 0 and n.protein == 0 and n.carbs == 0 and (BREAD.search(low) or PASTA.search(low) or RICE.search(low)):
        return "carb", "grain", ""
    if n.kcal == 0 and n.protein == 0 and animal_or_soy and not CONDIMENT.search(low):
        return "protein", "protein", ""

    if "cereal" in st or (CEREAL_BRANDS.search(low) and not DESSERT.search(low)):
        return "carb", "cereal", ""
    if "beverage" in st or (not FOODISH.search(low) and (BEVERAGE.search(low) or (MILK.search(low) and "creamer" not in low))):
        if MILK.search(low) and "creamer" not in low and n.protein >= 6:
            return "extra", "milk", ""
        if SMOOTHIE.search(low):
            return "extra", "smoothie", ""
        return "excluded", "drink", "drink"
    if SMOOTHIE.search(low):
        return "extra", "smoothie", ""
    if "ice cream" in st:
        return "excluded", "dessert", "dessert"
    if DESSERT.search(low) and not (re.search(r"oatmeal|\boats\b|parfait|yogurt", low) and not re.search(r"\bbars?\b|squares|cookie", low)):
        return "excluded", "dessert", "dessert"
    if SNACK.search(low):
        return "excluded", "snack", "snack food"
    if TOPPING.search(low):
        return "excluded", "condiment", "topping"
    if PASTA_SAUCE.search(low):
        return "extra", "sauce", ""
    if FAT_EXTRA.search(low) and f_share >= 0.5:
        return "extra", "fat", ""
    if "condiment" in st or (CONDIMENT.search(low) and not (n.protein >= 10 and p_share >= 0.25)):
        return "excluded", "condiment", "condiment"
    if "bakery" in st and not re.search(r"oatmeal|\boats\b|parfait|yogurt|bagel", low):
        return "excluded", "dessert", "dessert"

    if DAIRY_PROTEIN.search(low):
        if n.protein >= 10 and p_share >= 0.3:
            return "protein", "dairy", ""
        return "extra", "dairy", ""
    if CHEESE_ITEM.search(low.replace(chr(0x00AE), "").replace(chr(0x2122), "").strip()):
        return "extra", "cheese", ""

    # Protein anchors, including big mixed dishes that bring 20 g or more.
    starchy_dish = sandwich_or_pizza or bool(PASTA.search(low))
    if (n.protein >= 6 and p_share >= 0.28) or (n.protein >= 15 and p_share >= 0.18) or n.protein >= 20 \
            or (animal_or_soy and n.protein >= 7 and not starchy_dish):
        return "protein", "protein", ""

    starchy = bool(STARCHY_VEG.search(low))
    if LEGUME.search(low) and (n.carbs >= 5 or n.protein >= 3):
        return "carb", "legume", ""
    is_fruit = bool(FRUIT.search(low))
    is_veg = bool(VEG.search(low))
    if (is_veg or is_fruit) and not starchy and not NOT_PRODUCE.search(low) and kcal <= 220 \
            and (is_fruit or n.carbs <= 20):
        return "produce", ("fruit" if is_fruit and not is_veg else "veg"), ""
    if sandwich_or_pizza and kcal >= 120:
        return "carb", "mixed", ""
    if n.carbs >= 12 and c_share >= 0.4:
        return "carb", ("starchy_veg" if starchy else "grain"), ""
    if kcal >= 120:
        if c_share >= 0.35:
            return "carb", "mixed", ""
        if f_share >= 0.5:
            return "extra", "fat", ""
        return "extra", "side", ""
    if (is_veg or is_fruit) and not NOT_PRODUCE.search(low):
        return "produce", ("fruit" if is_fruit and not is_veg else "veg"), ""
    if n.protein >= 3:
        return "extra", "side", ""
    return "excluded", "other", "not a meal component"


def sanitize(n: Nutrition) -> tuple[Nutrition, list[str]]:
    """Clamp label fields that contradict each other (27 g saturated fat in a 0 g fat item)."""
    fixes = []
    fat = n.fat or 0.0
    sat, trans = n.sat_fat or 0.0, n.trans_fat or 0.0
    if sat > fat + 0.5:
        fixes.append(f"label listed {sat:g} g saturated fat but {fat:g} g total fat")
        sat = fat
    if trans > fat + 0.5:
        fixes.append(f"label listed {trans:g} g trans fat but {fat:g} g total fat")
        trans = fat
    fiber = n.fiber or 0.0
    if fiber > (n.carbs or 0.0) + 0.5:
        fixes.append(f"label listed {fiber:g} g fiber but {n.carbs:g} g carbs")
        fiber = n.carbs or 0.0
    added = n.added_sugar
    if added is not None and added > (n.carbs or 0.0) + 0.5:
        fixes.append(f"label listed {added:g} g added sugar but {n.carbs:g} g carbs")
        added = n.carbs or 0.0
    if not fixes:
        return n, fixes
    return Nutrition(**{**n.to_dict(), "sat_fat": sat, "trans_fat": trans, "fiber": fiber, "added_sugar": added}), fixes


def analyze(item: MenuItem, recipe: Recipe) -> Food:
    n, fixes = sanitize(recipe.nutrition)
    name = item.name or recipe.name
    low = name.lower()
    ing = (recipe.ingredients or item.searchable or "").lower()
    qty, unit = parse_serving(recipe.serving)

    role, kind, why = _classify_role(name, item.station, n, low)

    tags: set[str] = set()
    fried = bool((FRIED.search(low) and not NOT_FRIED.search(low)) or FRIED_INGREDIENT.search(ing))
    if fried:
        tags.add("fried")
    for tag, rx in (("sandwich", SANDWICH), ("bread", BREAD), ("pizza", PIZZA), ("pasta", PASTA), ("rice", RICE),
                    ("soup", SOUP), ("breakfast_only", BREAKFAST_ONLY), ("whole_grain", WHOLE_GRAIN),
                    ("legume", LEGUME), ("fish_oily", FISH_OILY), ("fish", FISH), ("shellfish", SHELLFISH),
                    ("egg", EGG), ("poultry", POULTRY), ("red_meat", RED_MEAT), ("pork", PORK), ("soy", SOY),
                    ("plant_meat", PLANT_MEAT), ("dairy", DAIRY_PROTEIN), ("potato", POTATO)):
        if rx.search(low):
            tags.add(tag)
    if kind == "cereal":
        tags.add("breakfast_only")
    if role == "produce" and (LEAFY.search(low) or (refs_hint := match_foods(name)) and refs_hint[0].leafy_raw):
        tags.add("leafy")
    if top_level_ingredients(ing, 1) and re.search(r"whole (wheat|grain)", top_level_ingredients(ing, 1)[0]):
        tags.add("whole_grain")
    if role == "carb" and "sandwich" in tags:
        tags.discard("bread")
    if "sandwich" in tags:
        tags.discard("bread")
    if SUSHI.search(low):
        tags.discard("bread")
        tags.add("rice")

    # Additives from the ingredient text.
    dyes = tuple(k for k, rx in DYES.items() if rx.search(ing))
    if not dyes and ARTIFICIAL_COLOR.search(ing) and not re.search(r"no artificial colou?r", ing):
        dyes = ("Artificial color",)
    red_flags = tuple(k for k, rx in RED_FLAGS.items() if rx.search(ing))
    emulsifiers = tuple((k, pts) for k, (rx, pts) in EMULSIFIERS.items() if rx.search(ing))
    sweeteners = tuple(k for k, rx in SWEETENERS.items() if rx.search(ing))
    pho = bool(PHO.search(ing))
    phosphates = bool(PHOSPHATE.search(ing))
    caramel = bool(CARAMEL.search(ing))
    seed_oil = fried or any(SEED_OIL.search(x) for x in top_level_ingredients(unwrap_product(ing) or ing, 3))
    upf, markers = _upf(ing)

    # Sugar: trust the label, estimate when the added-sugar row is missing.
    sugars = max(n.sugars or 0.0, n.added_sugar or 0.0)
    if JUICE.search(low) or kind == "smoothie":
        added, est_flag = sugars, n.added_sugar is None
    elif n.added_sugar is not None:
        added, est_flag = n.added_sugar, False
    elif SUGAR_INGREDIENT.search(ing):
        added, est_flag = round(0.75 * sugars, 1), True
    else:
        added, est_flag = 0.0, True

    mixed = bool(MIXED_DISH.search(low)) or kind in ("mixed",)
    est, refs, main_grams = estimate_micros(name, qty, unit, n.kcal, mixed, produce=(role == "produce"), protein=n.protein)
    if role in ("excluded",) and kind in ("condiment", "drink", "dessert"):
        est = {k: 0.0 for k in est}

    # Processed meat, in grams per serving.
    pm_g = 0.0
    if not PLANT_BASED.search(low) and (PROCESSED_MEAT.search(low) or PROCESSED_POULTRY.search(low) or
                                         re.search(r"sodium nitrite|potassium nitrite", ing)):
        m = PROCESSED_MEAT.search(low) or PROCESSED_POULTRY.search(low)
        word = m.group(0) if m else "sausage"
        kcal100 = next((v for k, v in PROCESSED_MEAT_KCAL100.items() if k in word), 250)
        if unit in UNIT_GRAMS and not MIXED_DISH.search(low):
            pm_g = qty * UNIT_GRAMS[unit]
        elif MIXED_DISH.search(low) or role not in ("protein",):
            pm_g = 10.0 if "gravy" in low else 20.0
        else:
            meat_kcal = n.protein * 4 + n.fat * 9
            pm_g = meat_kcal / (kcal100 / 100.0) * 0.85
        if PROCESSED_POULTRY.search(low) and not PROCESSED_MEAT.search(low):
            pm_g *= 0.5  # deli poultry counts at half weight (RESEARCH.md 3.15)
        tags.add("processed_meat")
        pm_g = round(pm_g, 1)

    # Produce credit.
    cups = 0.0
    if role == "produce" or kind in ("legume", "starchy_veg") or (kind == "fat" and re.search(r"avocado|guacamole", low)):
        half = kind in ("legume", "starchy_veg")
        cups = produce_cups_for(refs, qty, unit, n.kcal, half)
        if fried:
            cups *= 0.5
    elif refs and any(r.kcal < 60 for r in refs[1:]) and role in ("protein", "carb"):
        cups = 0.25  # a mixed dish with a vegetable in it

    # Protein quality (DIAAS-style proxy).
    if tags & {"fish_oily", "fish", "shellfish", "egg", "poultry", "red_meat", "pork", "dairy"} or kind in ("dairy", "milk", "cheese"):
        pq = 1.0
    elif "plant_meat" in tags:
        pq = 0.85
    elif "soy" in tags:
        pq = 0.9
    elif "legume" in tags or kind == "legume":
        pq = 0.7
    elif kind in ("grain", "cereal", "mixed") or tags & {"bread", "pasta", "rice", "pizza"}:
        pq = 0.6
    else:
        pq = 0.75

    # Carb quality: whole grains, legumes, produce, potatoes and dairy count as quality carbs.
    if kind == "cereal":
        cq = 0.6 if "whole_grain" in tags else 0.15
    elif kind in ("legume",) or "whole_grain" in tags:
        cq = 1.0
    elif role == "produce" or kind in ("starchy_veg",):
        cq = 0.5 if fried else 0.9
    elif kind in ("dairy", "milk") or "dairy" in tags:
        cq = 0.9
    elif "rice" in tags or "pasta" in tags:
        cq = 0.45
    elif tags & {"bread", "pizza", "sandwich", "breakfast_only"}:
        cq = 0.3
    else:
        cq = 0.5
    quality_carbs = max(0.0, n.carbs - added) * cq

    # Dairy for the acne nudge, and slow protein for the late-night bonus.
    dairy_cups = 0.0
    slow_protein = 0.0
    if kind in ("milk",) or re.search(r"\byogurt\b|parfait", low):
        dairy_cups = qty * UNIT_CUPS.get(unit, 0.0) if unit in UNIT_CUPS else 0.75
        slow_protein = n.protein
    elif "cottage cheese" in low:
        dairy_cups = 0.5 * (qty * UNIT_CUPS.get(unit, 0.5) if unit in UNIT_CUPS else 0.5)
        slow_protein = n.protein
    elif kind == "cheese":
        dairy_cups = 0.25
    if kind == "milk" and re.search(r"soy|pea|oat", low):
        dairy_cups = 0.0  # plant milks aren't in the dairy-acne data

    # Portion caps (RESEARCH.md 5.1).
    if role == "protein":
        max_s = 3 if (n.kcal <= 130 and "processed_meat" not in tags and kind != "dairy") else 2
        if n.kcal >= 450 or "sandwich" in tags:
            max_s = 1
    elif role == "carb":
        big = unit in UNIT_CUPS and qty * UNIT_CUPS[unit] >= 1.0
        if "bread" in tags or "pizza" in tags:
            max_s = 2
        elif kind == "legume":
            max_s = 1 if big else 2
        else:
            max_s = 3 if (n.kcal <= 110 and not big) else 2
        if n.kcal >= 400 or "sandwich" in tags:
            max_s = 1
    elif role == "produce":
        per_cup = qty * UNIT_CUPS[unit] if unit in UNIT_CUPS else (qty * UNIT_GRAMS[unit] / 150.0 if unit in UNIT_GRAMS else 0.5)
        if per_cup >= 1.5:
            max_s = 1
        elif refs and refs[0].leafy_raw:
            max_s = 2
        elif RAW_TOPPING.search(item.station) and n.kcal < 30:
            max_s = 1
        else:
            max_s = 2
    else:
        max_s = 1

    suspect = suspect_reason(n, qty, unit, low, kind, role)

    food = Food(
        rid=recipe.id, name=name, station=item.station, serving=recipe.serving, nutrition=n,
        role=role, kind=kind, tags=frozenset(tags), qty=qty, unit=unit,
        added_sugar=round(added, 2), added_sugar_estimated=est_flag,
        dyes=dyes, red_flags=red_flags, emulsifiers=emulsifiers, sweeteners=sweeteners,
        pho=pho, phosphates=phosphates, caramel=caramel, seed_oil=seed_oil,
        upf=round(upf, 3), upf_markers=markers, fried=fried, processed_meat_g=pm_g,
        produce_cups=cups, protein_quality=pq, carb_quality=cq,
        dairy_cups=round(dairy_cups, 3), slow_protein=slow_protein, est=est,
        suspect=suspect, exclude_reason=why, max_servings=max_s, fixes=tuple(fixes),
        base=(max(refs, key=lambda r: r.kcal).key if refs else re.sub(r"[^a-z ]", "", low).strip()),
        allergens=tuple(item.allergens), props=tuple(item.props),
    )
    industrial_trans = pho or bool(re.search(r"(?<!non-)(?<!non )hydrogenated|interesterified|shortening", ing))
    trans_scored = n.trans_fat if industrial_trans else n.trans_fat * 0.1
    food.vec = (
        n.kcal, n.protein, n.carbs, n.fat, n.fiber, n.sodium, n.sat_fat, trans_scored, added,
        n.calcium, n.iron, n.potassium, n.vit_d or 0.0,
        est["magnesium"], est["zinc"], est["vit_c"], est["vit_a"], est["epa_dha"],
        cups, n.kcal * upf, n.kcal if fried else 0.0, n.kcal if seed_oil else 0.0, pm_g, quality_carbs,
        n.protein * pq, dairy_cups, slow_protein, sugars, n.cholesterol,
    )
    return food
