"""Meal builds: recognizable athlete meals assembled from anywhere on the line (RESEARCH.md section 5).

Each template is a dish you'd actually make (burrito bowl, poke bowl, loaded scramble...), described
as a sequence of slots. For every period the search fills each template with the best items on the
line that day, from whichever stations have them, and keeps the highest-scoring distinct builds.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from itertools import combinations
from typing import Callable, Iterable, Optional

from . import config as C
from .classify import Food
from .score import ZERO, item_vec, score_meal, target_for, vec_add

# ---------------------------------------------------------------- what counts as what

# Not what this site is for (the brief is meat, eggs, dairy, fruit and real carbs), in any slot.
NOT_ATHLETE = re.compile(r"\bvegan\b|tofu|tempeh|seitan|quinoa|impossible|beyond|plant[- ]based|meatless|falafel|chik'?n|edamame|lentil|chickpea", re.I)
PLANT = re.compile(r"tofu|tempeh|edamame|\bsoy\b|soymilk|vegan|impossible|beyond|seitan|black bean burger|chik'?n|falafel|plant[- ]based|meatless|veggie burger", re.I)
EGG = re.compile(r"\beggs?\b|omelet|scramble|frittata|quiche", re.I)
ANIMAL_TAGS = frozenset({"poultry", "red_meat", "pork", "fish", "fish_oily", "shellfish", "egg"})


def _n(f: Food) -> str:
    return f.name.lower()


def animal(f: Food) -> bool:
    """Meat, fish or eggs: the athlete proteins. Tofu, soy and vegan proteins are left out on purpose."""
    return f.usable and f.role == "protein" and f.kind != "dairy" and not PLANT.search(f.name) \
        and bool(f.tags & ANIMAL_TAGS)


def egg(f: Food) -> bool:
    return animal(f) and bool(EGG.search(f.name))


ASIAN = re.compile(r"teriyaki|general tso|orange chicken|sesame|beijing|szechuan|kung pao|sweet and sour|lo mein|stir[- ]?fr|curry|thai|mongolian|bulgogi|korean|tikka|masala|asian|hoisin", re.I)
BBQ = re.compile(r"\bbbq\b|barbecue|buffalo|\bwings?\b|honey|glazed|jerk", re.I)
MEX = re.compile(r"santa fe|chipotle|cilantro|carnitas|barbacoa|tinga|fajita|\btaco|southwest|mexican|al pastor|adobo|chorizo|lime|enchilada|quesadilla|burrito|nacho|tamale|empanada|taquito|pipian|verde", re.I)
MED = re.compile(r"shawarma|gyro|oregano|greek|mediterranean|kebab|souvlaki|lemon herb|za.?atar|harissa|\blamb\b|tzatziki", re.I)
ITAL = re.compile(r"italian|parm|marinara|meatball|pesto|piccata|marsala|alfredo|lasagna|bolognese|vodka|carbonara|scampi", re.I)
HEAVY = re.compile(r"enchilada|quesadilla|nacho|tamale|empanada|taquito|pot pie|alfredo|parm(?:esan|igiana)|scampi|vodka|carbonara|casserole|\bbake\b|\bmac\b|cheesy|fried|crispy|nugget|tender|\bwings?\b|chili|soup|stew", re.I)
SPREAD = re.compile(r"(?:tuna|chicken|egg|ham) salad", re.I)
DELI_STATION = re.compile(r"deli|sandwich", re.I)
TOPPING_STATION = re.compile(r"salad bar|deli|sushi|create|burrito|build your own|hummus|made-to-order|toppings|griddle", re.I)
COOKED = re.compile(r"roast|saut|steam|grill|braise|bake|mash|stew|char|seasoned|spicy|collard|green beans?|bok choy|brussels|squash|zucchini|cauliflower|asparagus|ratatouille|ragout|hash|\bvegetables\b|medley", re.I)
RAW = re.compile(r"lettuce|spring mix|salad mix|mixed greens|romaine|arugula|baby spinach|spinach|tomato|cucumber|onion|pepper|carrot|cabbage|slaw|radish|scallion|jalapeno|pico|olive|pickle|sprout|celery|mushroom|corn", re.I)


def unprocessed(f: Food) -> bool:
    """The brief asks for low-processed meals, so ham, salami, bacon and hot dogs never anchor a build."""
    return "processed_meat" not in f.tags and f.processed_meat_g == 0


def plain_meat(f: Food) -> bool:
    """Meat that isn't a deli spread, a soup, a composed salad or a saucy composed dish."""
    return animal(f) and unprocessed(f) and not EGG.search(f.name) and not (f.tags & {"sandwich", "pizza", "pasta", "soup"}) \
        and f.nutrition.kcal < 450 and not SPREAD.search(f.name) and not HEAVY.search(f.name) \
        and not re.search(r"\bsalad\b|grits", f.name, re.I)


def hot_meat(f: Food) -> bool:
    """Cooked meat from a hot line (deli slices belong in sandwiches and salads)."""
    return plain_meat(f) and not DELI_STATION.search(f.station)


def entree(f: Food) -> bool:
    """Any animal-protein hot dish from a hot line, including chili and stir-fries (not soups or pasta dishes)."""
    soup = "soup" in f.tags and not re.search(r"chili|stew|gumbo|jambalaya|curry", f.name, re.I)
    return animal(f) and unprocessed(f) and not EGG.search(f.name) and not (f.tags & {"sandwich", "pizza", "pasta"}) \
        and not soup and not SPREAD.search(f.name) and not re.search(r"\bsalad\b|spaghetti|penne|noodle|lo mein|\bmac\b", f.name, re.I) \
        and not re.search(r"salad bar|deli|sushi|create|hummus", f.station, re.I)


def burger(f: Food) -> bool:
    return animal(f) and unprocessed(f) and "sandwich" in f.tags


def yogurt(f: Food) -> bool:
    return f.usable and f.kind == "dairy" and bool(re.search(r"yogurt|cottage|parfait|skyr", _n(f)))


def milk(f: Food) -> bool:
    return f.usable and f.kind == "milk" and not re.search(r"oat|almond|coconut|soy|pea", _n(f))


def rice(f: Food) -> bool:
    return f.usable and f.role == "carb" and "rice" in f.tags and "soup" not in f.tags \
        and not re.search(r"roll|pudding|krispies|fried rice|soup|salad", _n(f))


def potato(f: Food) -> bool:
    return f.usable and f.role == "carb" and ("potato" in f.tags or bool(re.search(r"sweet potato|\byams?\b", _n(f)))) \
        and not re.search(r"chips|salad", _n(f))


def pasta(f: Food) -> bool:
    return f.usable and f.role == "carb" and "pasta" in f.tags and not re.search(r"salad|bake|ravioli|\bmac\b|lasagna", _n(f)) \
        and not re.search(r"salad bar|deli|hummus", f.station, re.I)


def tortilla(f: Food) -> bool:
    return f.usable and f.role == "carb" and bool(re.search(r"tortilla|\bwraps?\b", _n(f))) and "chips" not in _n(f)


def bread(f: Food) -> bool:
    return f.usable and f.role == "carb" and "bread" in f.tags and not re.search(
        r"garlic bread|cheese bread|biscuit|croissant|french toast|sweet|cinnamon|blueberry|muffin|donut", _n(f))


def pita(f: Food) -> bool:
    return bread(f) and bool(re.search(r"pita|naan|flatbread", _n(f)))


def oats(f: Food) -> bool:
    return f.usable and f.role == "carb" and bool(re.search(r"oatmeal|\boats\b|\bgrits\b", _n(f))) \
        and not re.search(r"\bbars?\b|cookie|square|granola|cereal|crisp", _n(f))


def corn(f: Food) -> bool:
    return f.usable and f.role == "carb" and bool(re.search(r"\bcorn\b", _n(f))) and not re.search(r"chip|bread|muffin|tortilla", _n(f))


def veg(f: Food) -> bool:
    return f.usable and f.role == "produce" and f.kind == "veg"


def cooked_veg(f: Food) -> bool:
    """A hot vegetable side."""
    return veg(f) and "leafy" not in f.tags and (bool(COOKED.search(f.name)) or not TOPPING_STATION.search(f.station))


def raw_veg(f: Food) -> bool:
    """A cold topping: lettuce, tomato, onion, peppers, cucumber, cabbage..."""
    return veg(f) and "leafy" not in f.tags and bool(RAW.search(f.name)) and not re.search(
        r"roast|saut|braise|mash|stew|ragout|hash|collard", f.name, re.I)


def salad_topping(f: Food) -> bool:
    return raw_veg(f) or (veg(f) and "leafy" not in f.tags and bool(re.search(r"roast|grill", f.name, re.I)))


def egg_veg(f: Food) -> bool:
    return veg(f) and bool(re.search(r"spinach|pepper|onion|mushroom|tomato|kale|salsa|pico|jalapeno", f.name, re.I)) \
        and not re.search(r"ragout|collard|slaw|cabbage", f.name, re.I)


def sandwich_veg(f: Food) -> bool:
    return veg(f) and bool(re.search(r"lettuce|tomato|onion|spinach|pepper|cucumber|pickle|sprout|romaine|arugula|greens|jalapeno|olive|mixed greens|spring mix", f.name, re.I)) \
        and not re.search(r"roast|saut|braise|mash|stew|ragout|collard|slaw|cabbage|grilled|steam", f.name, re.I)


def burrito_veg(f: Food) -> bool:
    return veg(f) and bool(re.search(r"pepper|onion|corn|fajita|lettuce|tomato|jalapeno|pico|cabbage|slaw|romaine|salsa", f.name, re.I)) \
        and not re.search(r"ragout|collard|kale", f.name, re.I)


def poke_veg(f: Food) -> bool:
    return veg(f) and bool(re.search(r"cucumber|carrot|cabbage|scallion|radish|onion|pepper|seaweed|slaw|spinach|lettuce|mushroom|sprout", f.name, re.I)) \
        and not re.search(r"roast|saut|braise|mash|stew|ragout|collard", f.name, re.I)


def med_veg(f: Food) -> bool:
    return veg(f) and bool(re.search(r"cucumber|tomato|pepper|onion|olive|spinach|lettuce|eggplant|zucchini|squash|cauliflower|carrot|romaine|greens|roasted vegetables|chickpea", f.name, re.I)) \
        and not re.search(r"ragout|collard|slaw", f.name, re.I)


def pasta_veg(f: Food) -> bool:
    return veg(f) and bool(re.search(r"spinach|broccoli|zucchini|squash|mushroom|pepper|onion|tomato|kale|asparagus|eggplant|\bpeas\b", f.name, re.I)) \
        and not re.search(r"salad|cucumber|slaw|lettuce|carrot|cabbage|pico|salsa|jalapeno|raw", f.name, re.I)


def greens(f: Food) -> bool:
    return veg(f) and "leafy" in f.tags


def fruit(f: Food) -> bool:
    return f.usable and f.role == "produce" and f.kind == "fruit" and "juice" not in _n(f)


def beans(f: Food) -> bool:
    return f.usable and f.role == "carb" and f.kind == "legume" and bool(re.search(r"black|pinto|refried|red beans", _n(f))) \
        and "salad" not in _n(f)


def cheese(f: Food) -> bool:
    return f.usable and f.kind == "cheese" and "vegan" not in _n(f)


def _flavor(f: Food) -> bool:
    return not f.suspect and not f.dyes and not f.red_flags


def guac(f: Food) -> bool:
    return _flavor(f) and bool(re.search(r"guacamole|avocado", _n(f)))


def salsa(f: Food) -> bool:
    return _flavor(f) and bool(re.search(r"salsa|pico", _n(f)))


def hot_sauce(f: Food) -> bool:
    return _flavor(f) and bool(re.search(r"hot sauce|texas pete|sriracha|siracha|tabasco|buffalo", _n(f)))


def med_sauce(f: Food) -> bool:
    return _flavor(f) and bool(re.search(r"tzatziki|hummus", _n(f)))


def asian_sauce(f: Food) -> bool:
    return _flavor(f) and bool(re.search(r"sriracha|siracha|soy sauce|poke|teriyaki|sweet chili|sesame", _n(f)))


def pasta_sauce(f: Food) -> bool:
    return _flavor(f) and (f.kind == "sauce" or bool(re.search(r"marinara|pomodoro|tomato sauce", _n(f)))) \
        and not re.search(r"pasta|penne|spaghetti|noodle", _n(f))


def dressing(f: Food) -> bool:
    return _flavor(f) and bool(re.search(r"vinaigrette|italian|balsamic|oil and vinegar|red wine vinegar|lemon|greek dressing", _n(f)))


def mustard(f: Food) -> bool:
    return _flavor(f) and bool(re.search(r"mustard|hummus", _n(f)))


def crunch(f: Food) -> bool:
    """Seeds and nuts: on a salad, a bowl of oats or a parfait."""
    return _flavor(f) and bool(re.search(r"sunflower|pumpkin seed|seeds|almond|walnut|pecan|\bnuts\b", _n(f))) and "granola" not in _n(f)


def granola(f: Food) -> bool:
    return _flavor(f) and "granola" in _n(f) and not re.search(r"\bbars?\b", _n(f))


# ---------------------------------------------------------------- ranking candidates


def quality(f: Food) -> float:
    """Rough 0-1 quality used only to shortlist candidates before real scoring."""
    n = f.nutrition
    kcal = max(n.kcal, 1.0)
    q = 1.0 - 0.45 * f.upf
    q -= min(0.3, 0.03 * f.added_sugar * 100.0 / kcal)
    q -= min(0.25, (n.sodium * 100.0 / kcal) / 1600.0)
    q -= 0.25 if f.processed_meat_g > 0 else 0.0
    q -= 0.15 if f.fried else 0.0
    q -= 0.03 * len(f.dyes) + 0.04 * len(f.red_flags)
    q += min(0.15, 0.05 * n.fiber * 100.0 / kcal)
    return max(0.05, min(1.0, q))


def micro_density(f: Food) -> float:
    e, n = f.est, f.nutrition
    return (e.get("vit_c", 0) / 90 + e.get("vit_a", 0) / 900 + e.get("magnesium", 0) / 420
            + n.potassium / 4700 + n.fiber / 28 + n.iron / 18 + f.produce_cups / 2)


def _protein_rank(f: Food) -> float:
    return quality(f) * f.nutrition.protein * 100.0 / max(f.nutrition.kcal, 1.0) + f.nutrition.protein / 10.0


RANK: dict = {
    "protein": _protein_rank, "egg": _protein_rank, "burger": _protein_rank, "yogurt": _protein_rank,
    "veg": lambda f: quality(f) * (0.2 + micro_density(f)),
    "greens": lambda f: quality(f) * (0.2 + micro_density(f)),
    "fruit": lambda f: quality(f) * (0.2 + micro_density(f)),
    "sauce": lambda f: -(f.nutrition.kcal + f.nutrition.sodium / 40.0 + f.added_sugar * 6.0),
    "dressing": lambda f: -(f.nutrition.kcal + f.nutrition.sodium / 40.0 + f.added_sugar * 6.0),
    "side": lambda f: quality(f) * f.nutrition.protein,
    "milk": lambda f: quality(f) * f.nutrition.protein * 100.0 / max(f.nutrition.kcal, 1.0),
    "topping": lambda f: quality(f) * (1.0 + micro_density(f)),
    "cheese": lambda f: quality(f) * f.nutrition.protein,
    "crunch": lambda f: quality(f) * (1.0 + micro_density(f)),
}


def _carb_rank(f: Food) -> float:
    n = f.nutrition
    return quality(f) * (1.0 + n.fiber / 5.0) * (1.0 + n.potassium / 800.0) * (1.0 + f.carb_quality)


# ---------------------------------------------------------------- templates


@dataclass(frozen=True)
class Slot:
    key: str
    pick: Callable[[Food], bool]
    min_n: int = 0
    max_n: int = 1
    servings: tuple = (1,)
    top: int = 4


@dataclass(frozen=True)
class Template:
    key: str
    kinds: frozenset          # breakfast / main / late
    slots: tuple
    title: Callable[[dict], str]
    how: Callable[[dict], str]
    theme: Optional[re.Pattern] = None
    chef_plate: bool = False  # reward sides from the protein's own station
    blurb: str = ""
    clash: Optional[Callable[[dict], bool]] = None  # picks that don't belong together (fish in meat sauce)


def nice(f: Food) -> str:
    s = re.sub(r"[®™]", "", f.name)
    s = re.sub(r"\s*\((?:made without gluten)\)", "", s, flags=re.I)
    s = re.sub(r"^(?:halal|cage-free|hot|sliced|diced|chopped|deli)\s+", "", s.strip(), flags=re.I)
    s = re.sub(r"\s+(?:bowl|station)$", "", s, flags=re.I)
    return " ".join(s.split())


def _first(p: dict, key: str) -> Optional[Food]:
    items = p.get(key) or []
    return items[0][0] if items else None


def _names(p: dict, key: str) -> str:
    return _join([nice(f) for f, _ in p.get(key) or []])


def _join(names: list) -> str:
    names = [n for n in names if n]
    if len(names) <= 1:
        return names[0] if names else ""
    return ", ".join(names[:-1]) + " and " + names[-1]


def _fin(p: dict, *keys: str) -> str:
    return _join([nice(f) for k in keys for f, _ in p.get(k) or []])


def _dbl(p: dict, key: str) -> str:
    """'a double portion of Chicken' when the build takes two or more servings."""
    return _join([("a double portion of " if s == 2 else "a triple portion of " if s >= 3 else "") + nice(f)
                  for f, s in p.get(key) or []])


MAIN, BFAST, LATE = "main", "breakfast", "late"
RESERVED_STATION = re.compile(r"stress less", re.I)  # UNC's allergy-friendly pantry: leave it for people who need it
MAX_ITEMS = 8           # more components than this and it stops being a meal you'd actually assemble
WEAK_GAP = 12.0         # don't pad the list with builds far below the best one
NEAR_DUPLICATE = 0.7    # two builds sharing this share of their items are the same meal


def _t(key, kinds, slots, title, how, theme=None, chef_plate=False, blurb="", clash=None):
    return Template(key, frozenset(kinds), tuple(slots), title, how,
                    re.compile(theme, re.I) if theme else None, chef_plate, blurb, clash)


def _odd_sandwich(p: dict) -> bool:
    """Taco meat on a bagel, curry in a sandwich: fine in a tortilla or pita, odd on sliced bread."""
    w = _first(p, "wrap")
    if w is None or tortilla(w):
        return False
    pita_ok = bool(re.search(r"pita|naan|flatbread", w.name, re.I))
    for f, _ in p.get("protein", []):
        if MEX.search(f.name) or ASIAN.search(f.name) or re.search(r"ground|crumble|taco|santa fe|carnitas|barbacoa|tinga|bbq|pulled", f.name, re.I):
            return True
        if MED.search(f.name) and not pita_ok:
            return True
    return False


CUISINE_SLOTS = frozenset({"protein", "base", "starch", "pasta", "carb", "potato", "beans", "veg", "sauce", "topping", "crunch", "egg"})


def cuisines(f: Food) -> frozenset:
    """Which cuisine an item's name commits it to, if any. Plain rice, chicken or spinach go with anything."""
    if f.kind in ("dairy", "milk", "fruit", "cheese"):
        return frozenset()
    out = set()
    for tag, rx in (("mex", MEX), ("asian", ASIAN), ("med", MED), ("ital", ITAL)):
        if rx.search(f.name):
            out.add(tag)
    if not out and "pasta" in f.tags:
        out.add("ital")
    return frozenset(out)


def cuisine_clash(items: Iterable[Food]) -> bool:
    """Santa Fe beef over penne with Szechuan green beans: two items that commit to different cuisines."""
    sets = [c for c in (cuisines(f) for f in items) if c]
    return any(not (a & b) for a, b in combinations(sets, 2))


def _fish_in_meat_sauce(p: dict) -> bool:
    meaty = any(re.search(r"meat|bolognese|sausage|beef|pork", f.name, re.I) for f, _ in p.get("sauce", []))
    fishy = any(f.tags & {"fish", "fish_oily", "shellfish"} for f, _ in p.get("protein", []))
    return meaty and fishy


TEMPLATES = [
    # ---------------- breakfast
    _t("scramble", (BFAST, LATE), [
        Slot("egg", egg, 1, 1, (1, 2, 3), 3),
        Slot("base", lambda f: potato(f) or bread(f) or oats(f), 0, 1, (1, 2), 4),
        Slot("veg", egg_veg, 0, 2, (1,), 5),
        Slot("sauce", lambda f: salsa(f) or hot_sauce(f), 0, 1, (1,), 2),
        Slot("fruit", fruit, 0, 2, (1, 2), 4),
        Slot("side", lambda f: yogurt(f) or milk(f), 0, 1, (1,), 3),
    ],
        lambda p: ("Loaded " if p.get("veg") else "") + ("Scramble Plate" if "scrambl" in _names(p, "egg").lower() else f"{_names(p, 'egg')} Plate"),
        lambda p: (f"Pile {_fin(p, 'veg')} on {_dbl(p, 'egg')}" if p.get("veg") else f"Take {_dbl(p, 'egg')}")
        + (f", hit it with {_names(p, 'sauce')}" if p.get("sauce") else "")
        + (f", {_names(p, 'base')} on the side" if p.get("base") else "") + (f", {_names(p, 'fruit')} to finish" if p.get("fruit") else "")
        + (f", {_names(p, 'side')} with it" if p.get("side") else "") + ".",
        blurb="Eggs, veggies, a real carb and fruit."),
    _t("parfait", (BFAST, LATE), [
        Slot("yogurt", yogurt, 1, 1, (1, 2), 3),
        Slot("fruit", fruit, 1, 2, (1, 2), 5),
        Slot("crunch", lambda f: crunch(f) or granola(f), 0, 1, (1,), 3),
        Slot("side", lambda f: egg(f) or milk(f), 0, 1, (1, 2), 3),
    ],
        lambda p: ("Greek Yogurt" if "greek" in _names(p, "yogurt").lower() else "Cottage Cheese" if "cottage" in _names(p, "yogurt").lower() else "Yogurt") + " Power Parfait",
        lambda p: f"Layer {_dbl(p, 'yogurt')} with {_names(p, 'fruit')}" + (f", {_names(p, 'crunch')} on top" if p.get("crunch") else "")
        + (f". {_names(p, 'side')} on the side for more protein" if p.get("side") else "") + ".",
        blurb="Slow protein, fruit and crunch. Great before bed too."),
    _t("breakfast_burrito", (BFAST, LATE), [
        Slot("wrap", tortilla, 1, 1, (1,), 3),
        Slot("egg", egg, 1, 1, (1, 2), 3),
        Slot("potato", potato, 0, 1, (1,), 3),
        Slot("veg", egg_veg, 0, 2, (1,), 4),
        Slot("cheese", cheese, 0, 1, (1,), 2),
        Slot("sauce", lambda f: salsa(f) or hot_sauce(f), 0, 1, (1,), 2),
        Slot("fruit", fruit, 0, 1, (1,), 3),
    ],
        lambda p: "Breakfast Burrito",
        lambda p: f"Fill the {_names(p, 'wrap')} with {_fin(p, 'egg', 'potato', 'veg', 'cheese')}, roll it tight"
        + (f", {_names(p, 'sauce')} inside" if p.get("sauce") else "") + ".",
        blurb="Eggs and potatoes rolled up with whatever veggies are out."),
    _t("oat_bowl", (BFAST, LATE), [
        Slot("oats", oats, 1, 1, (1, 2), 3),
        Slot("fruit", fruit, 1, 2, (1,), 5),
        Slot("protein", lambda f: egg(f) or yogurt(f), 1, 2, (1, 2), 4),
        Slot("crunch", crunch, 0, 1, (1,), 2),
        Slot("milk", milk, 0, 1, (1,), 2),
    ],
        lambda p: ("Grits" if "grits" in _names(p, "oats").lower() else "Oatmeal") + " Power Bowl",
        lambda p: f"Top {_dbl(p, 'oats')} with {_names(p, 'fruit')}" + (f" and {_names(p, 'crunch')}" if p.get("crunch") else "")
        + f"; {_dbl(p, 'protein')} on the side for the protein" + (f", {_names(p, 'milk')} to drink" if p.get("milk") else "") + ".",
        blurb="Oats and fruit for fuel, eggs or yogurt for protein."),
    # ---------------- lunch and dinner
    _t("burrito_bowl", (MAIN, LATE), [
        Slot("base", rice, 1, 1, (1, 2), 3),
        Slot("protein", lambda f: hot_meat(f) and not (ASIAN.search(f.name) or BBQ.search(f.name) or MED.search(f.name) or ITAL.search(f.name)), 1, 1, (1, 2, 3), 5),
        Slot("beans", beans, 0, 1, (1,), 2),
        Slot("veg", burrito_veg, 1, 3, (1,), 5),
        Slot("sauce", salsa, 0, 1, (1,), 2),
        Slot("topping", lambda f: guac(f) or cheese(f), 0, 1, (1,), 3),
        Slot("fruit", fruit, 0, 1, (1,), 3),
    ],
        lambda p: f"{nice(_first(p, 'protein'))} Burrito Bowl",
        lambda p: f"{_names(p, 'base')} on the bottom, {_dbl(p, 'protein')} on top, then {_fin(p, 'beans', 'veg')}"
        + (f"; finish with {_fin(p, 'sauce', 'topping')}" if p.get("sauce") or p.get("topping") else "") + ".",
        theme=r"burrito|build your own|santa fe|chipotle|cilantro|lime|carnitas|tinga|barbacoa|fajita|southwest|pico|salsa|guac|pinto|black bean|corn|pepper onion|jalapeno",
        blurb="Chipotle at home: rice, meat, beans and fresh toppings."),
    _t("med_bowl", (MAIN, LATE), [
        Slot("protein", lambda f: hot_meat(f) and not (ASIAN.search(f.name) or BBQ.search(f.name) or ITAL.search(f.name)
                                                       or re.search(r"santa fe|carnitas|barbacoa|tinga|taco|fajita|chorizo|blackened|cajun|jerk", f.name, re.I)), 1, 1, (1, 2, 3), 5),
        Slot("base", lambda f: rice(f) or pita(f) or (potato(f) and re.search(r"roast|lemon|herb|greek|wedge", f.name, re.I) is not None), 1, 1, (1, 2), 4),
        Slot("veg", med_veg, 1, 3, (1,), 5),
        Slot("sauce", med_sauce, 0, 1, (1,), 2),
        Slot("cheese", lambda f: cheese(f) and "feta" in _n(f), 0, 1, (1,), 1),
        Slot("fruit", fruit, 0, 1, (1,), 3),
    ],
        lambda p: f"{nice(_first(p, 'protein'))} " + ("Bowl" if re.search(r"shawarma|gyro|kebab", _first(p, 'protein').name, re.I) else "Mediterranean Bowl"),
        lambda p: f"{_names(p, 'base')} first, {_dbl(p, 'protein')} on top, {_fin(p, 'veg')} around it"
        + (f", a scoop of {_names(p, 'sauce')}" if p.get("sauce") else "") + (f" and {_names(p, 'cheese')}" if p.get("cheese") else "") + ".",
        theme=r"shawarma|greek|oregano|mediterranean|gyro|lamb|kebab|tzatziki|hummus|feta|pita|cucumber|tomato|saffron|basmati|lemon|harissa|olive",
        blurb="Greek-style: grilled meat, rice or pita, crunchy veg, tzatziki."),
    _t("poke_bowl", (MAIN, LATE), [
        Slot("base", rice, 1, 1, (1, 2), 3),
        Slot("protein", lambda f: hot_meat(f) and bool(f.tags & {"poultry", "fish", "fish_oily", "shellfish"})
             and not (BBQ.search(f.name) or MED.search(f.name) or ITAL.search(f.name) or re.search(r"santa fe|carnitas|tinga|taco|fajita|chipotle", f.name, re.I)), 1, 1, (1, 2, 3), 4),
        Slot("veg", poke_veg, 2, 3, (1,), 6),
        Slot("sauce", asian_sauce, 0, 1, (1,), 2),
        Slot("topping", guac, 0, 1, (1,), 1),
        Slot("fruit", fruit, 0, 1, (1,), 3),
    ],
        lambda p: f"{nice(_first(p, 'protein'))} Poke Bowl",
        lambda p: f"{_names(p, 'base')}, {_dbl(p, 'protein')}, then {_fin(p, 'veg')}"
        + (f"; {_names(p, 'sauce')} over the top" if p.get("sauce") else "") + (f" with {_names(p, 'topping')}" if p.get("topping") else "") + ".",
        theme=r"sushi|create|poke|cucumber|cabbage|carrot|scallion|pineapple|sriracha|siracha|avocado|ginger|radish|mango|sesame",
        blurb="Sushi-bar bowl: rice, lean protein, crunchy raw veg."),
    _t("power_plate", (MAIN, LATE), [
        Slot("protein", entree, 1, 1, (1, 2), 5),
        Slot("starch", lambda f: rice(f) or potato(f) or pasta(f) or corn(f) or (bread(f) and re.search(r"roll|bun|cornbread|pita|naan", f.name, re.I) is not None), 1, 1, (1, 2), 4),
        Slot("veg", cooked_veg, 1, 2, (1, 2), 5),
        Slot("fruit", fruit, 0, 1, (1,), 3),
        Slot("milk", milk, 0, 1, (1,), 2),
    ],
        lambda p: f"{nice(_first(p, 'protein'))} Power Plate",
        lambda p: f"{_names(p, 'protein')} over {_names(p, 'starch')}, {_names(p, 'veg')} on the side"
        + (f", {_names(p, 'fruit')} for dessert" if p.get("fruit") else "") + (f", {_names(p, 'milk')} to drink" if p.get("milk") else "") + ".",
        chef_plate=True,
        blurb="Meat, a real starch and two veg: the classic athlete plate."),
    _t("pasta_bowl", (MAIN, LATE), [
        Slot("pasta", pasta, 1, 1, (1, 2), 3),
        Slot("sauce", pasta_sauce, 1, 1, (1,), 3),
        Slot("protein", lambda f: hot_meat(f) and not (ASIAN.search(f.name) or BBQ.search(f.name) or MED.search(f.name)
                                                       or re.search(r"santa fe|carnitas|barbacoa|tinga|taco|fajita|chipotle", f.name, re.I)), 1, 1, (1, 2), 4),
        Slot("veg", pasta_veg, 0, 2, (1,), 5),
        Slot("cheese", lambda f: cheese(f) and "parmesan" in _n(f), 0, 1, (1,), 1),
        Slot("fruit", fruit, 0, 1, (1,), 3),
    ],
        lambda p: f"{nice(_first(p, 'protein'))} Pasta",
        lambda p: f"{_names(p, 'pasta')} with {_names(p, 'sauce')}, topped with {_dbl(p, 'protein')}"
        + (f" and {_fin(p, 'veg')}" if p.get("veg") else "") + (f". {_names(p, 'fruit')} on the side" if p.get("fruit") else "") + ".",
        theme=r"pasta|penne|spaghetti|noodle|marinara|meat sauce|italian|made-to-order|parm|spinach|mushroom|pepper|zucchini|squash|broccoli|onion",
        blurb="Red-sauce pasta with a double portion of meat.", clash=_fish_in_meat_sauce),
    _t("power_salad", (MAIN, LATE), [
        Slot("greens", greens, 1, 1, (1, 2), 3),
        Slot("protein", lambda f: plain_meat(f) and not ASIAN.search(f.name), 1, 1, (1, 2), 5),
        Slot("egg", lambda f: egg(f) and re.search(r"boiled|hard cooked|chopped", f.name, re.I) is not None, 0, 1, (1, 2), 2),
        Slot("veg", salad_topping, 1, 3, (1,), 6),
        Slot("carb", lambda f: rice(f) or potato(f) or bread(f) or corn(f) or beans(f), 0, 1, (1, 2), 4),
        Slot("fruit", fruit, 0, 1, (1,), 3),
        Slot("crunch", crunch, 0, 1, (1,), 2),
        Slot("dressing", dressing, 0, 1, (1,), 2),
    ],
        lambda p: f"{nice(_first(p, 'protein'))} Power Salad",
        lambda p: f"Big bowl of {_names(p, 'greens')}, {_dbl(p, 'protein')}" + (f" and {_names(p, 'egg')}" if p.get("egg") else "")
        + f" on top, then {_fin(p, 'veg', *(['carb'] if _first(p, 'carb') is not None and not bread(_first(p, 'carb')) else []), 'crunch')}"
        + (f"; {_names(p, 'dressing')} on the side" if p.get("dressing") else "")
        + (f". {_names(p, 'carb')} on the side makes it a full meal" if _first(p, 'carb') is not None and bread(_first(p, 'carb')) else "")
        + (f". {_names(p, 'fruit')} for dessert" if p.get("fruit") else "") + ".",
        theme=r"salad bar|spinach|spring|romaine|greens|cucumber|tomato|carrot|pepper|onion|vinaigrette|sunflower|egg|strawberr|orange",
        blurb="Greens loaded with meat, eggs and color, plus a carb so it's a meal."),
    _t("wrap", (MAIN, LATE), [
        Slot("wrap", lambda f: tortilla(f) or bread(f), 1, 1, (1,), 3),
        Slot("protein", plain_meat, 1, 1, (1, 2), 5),
        Slot("veg", sandwich_veg, 1, 3, (1,), 5),
        Slot("cheese", cheese, 0, 1, (1,), 2),
        Slot("sauce", lambda f: mustard(f) or med_sauce(f) or hot_sauce(f), 0, 1, (1,), 2),
        Slot("fruit", fruit, 0, 1, (1,), 3),
    ],
        lambda p: ("Double " if sum(s for _, s in p.get("protein", [])) >= 2 else "") + f"{nice(_first(p, 'protein'))} "
        + ("Wrap" if tortilla(_first(p, 'wrap')) else "Pita" if re.search(r"pita|naan|flatbread", _first(p, 'wrap').name, re.I)
           else "Bagel Sandwich" if "bagel" in _first(p, 'wrap').name.lower() else "Sandwich"),
        lambda p: f"Stack {_dbl(p, 'protein')} on {_names(p, 'wrap')} with {_fin(p, 'veg', 'cheese')}"
        + (f"; {_names(p, 'sauce')} instead of mayo" if p.get("sauce") else "") + (f". {_names(p, 'fruit')} on the side" if p.get("fruit") else "") + ".",
        theme=r"deli|sandwich|wrap|turkey|chicken breast|roast beef|lettuce|tomato|onion|pickle|mustard|provolone|swiss|cheddar|spinach",
        blurb="Stacked with double meat and real veg.", clash=_odd_sandwich),
    _t("rice_bowl", (MAIN, LATE), [
        Slot("base", rice, 1, 1, (1, 2), 3),
        Slot("protein", lambda f: entree(f) and not (f.tags & {"pasta"}) and not ITAL.search(f.name), 1, 1, (1, 2), 5),
        Slot("veg", cooked_veg, 1, 2, (1, 2), 5),
        Slot("sauce", lambda f: asian_sauce(f) or hot_sauce(f), 0, 1, (1,), 2),
        Slot("fruit", fruit, 0, 1, (1,), 3),
    ],
        lambda p: f"{nice(_first(p, 'protein'))} Rice Bowl",
        lambda p: f"Spoon {_dbl(p, 'protein')} over {_names(p, 'base')}, {_fin(p, 'veg')} alongside"
        + (f", {_names(p, 'sauce')} to taste" if p.get("sauce") else "") + (f". {_names(p, 'fruit')} on the side" if p.get("fruit") else "") + ".",
        theme=r"beijing|teriyaki|general tso|stir|sesame|ginger|soy|asian|jasmine|broccoli|bok choy|green bean|curry|cajun|international|chili|pepper",
        blurb="Rice and a saucy protein with veg, stir-fry style."),
    _t("burger_plate", (MAIN, LATE), [
        Slot("burger", burger, 1, 1, (1,), 3),
        Slot("veg", raw_veg, 0, 2, (1,), 4),
        Slot("fruit", fruit, 0, 2, (1,), 3),
        Slot("milk", milk, 0, 1, (1,), 2),
    ],
        lambda p: f"{nice(_first(p, 'burger'))} + Sides",
        lambda p: f"Grab the {_names(p, 'burger')}" + (f", load it with {_names(p, 'veg')}" if p.get("veg") else "")
        + (f" and take {_names(p, 'fruit')} instead of fries" if p.get("fruit") else "") + ".",
        blurb="The burger, but with fruit instead of fries."),
]
TEMPLATE_BY_KEY = {t.key: t for t in TEMPLATES}


def templates_for(slot: str, label: str = "") -> list:
    kind = C.SLOT_KIND.get(slot, "main")
    out = [t for t in TEMPLATES if kind in t.kinds]
    if label.lower() == "brunch":  # brunch lines serve breakfast and lunch food
        out += [t for t in TEMPLATES if BFAST in t.kinds and t not in out]
    return out


# ---------------------------------------------------------------- search


@dataclass
class Build:
    template: Template
    picks: tuple              # ((slot key, Food, servings), ...)
    vec: tuple
    score: float
    bonus: float = 0.0

    @property
    def main(self) -> Optional[Food]:
        for key in ("protein", "egg", "burger", "yogurt"):
            for k, f, _ in self.picks:
                if k == key:
                    return f
        return None

    def by_slot(self) -> dict:
        out: dict = {}
        for k, f, s in self.picks:
            out.setdefault(k, []).append((f, s))
        return out

    @property
    def name(self) -> str:
        return self.template.title(self.by_slot())

    @property
    def rids(self) -> frozenset:
        return frozenset(f.rid for _, f, _ in self.picks)


@dataclass
class _State:
    picks: tuple = ()
    vec: tuple = ZERO
    rids: frozenset = frozenset()
    bases: frozenset = frozenset()
    main_rid: Optional[str] = None


def _servings(slot: Slot, f: Food) -> list:
    if slot.key == "wrap" and f.unit == "slice":
        return [2]  # a sandwich takes two slices
    if re.search(r"bagel", f.name, re.I):
        return [1]
    out = [s for s in slot.servings if s <= max(1, f.max_servings)]
    return out or [1]


def _slot_options(slot: Slot, cands: list) -> list:
    opts: list = [()] if slot.min_n == 0 else []
    for r in range(max(1, slot.min_n), slot.max_n + 1):
        for combo in combinations(cands, r):
            if len({f.base for f in combo}) < len(combo):
                continue  # two dishes of the same food is one food, not variety
            if r == 1:
                f = combo[0]
                opts += [((f, s),) for s in _servings(slot, f)]
            else:
                opts.append(tuple((f, 1) for f in combo))
    return opts


def _bonus(tpl: Template, st: _State) -> float:
    foods = [f for _, f, _ in st.picks]
    if tpl.chef_plate:
        main = next((f for k, f, _ in st.picks if k == "protein"), None)
        hits = sum(1 for k, f, _ in st.picks if main is not None and k != "protein" and f.station == main.station)
    elif tpl.theme is not None:
        hits = sum(1 for f in foods if tpl.theme.search(f.name) or tpl.theme.search(f.station))
    else:
        hits = 0
    return min(C.THEME_BONUS_CAP, hits * C.THEME_BONUS_PER_ITEM)


def _prune(scored: list, width: int) -> list:
    scored.sort(key=lambda x: -x[0])
    out, per = [], {}
    for sc, st in scored:
        k = st.main_rid
        if k is not None and per.get(k, 0) >= 3:  # keep several different proteins alive in the beam
            continue
        per[k] = per.get(k, 0) + 1
        out.append((sc, st))
        if len(out) >= width:
            break
    return out


def run_template(tpl: Template, foods: list, target: C.MealTarget, vec_cache: Optional[dict] = None) -> list:
    """All finished builds for one template, best first (at most a few per main protein)."""
    cache = vec_cache if vec_cache is not None else {}
    cands = {}
    for slot in tpl.slots:
        seen, pool = set(), []
        for f in foods:
            if f.rid in seen or not slot.pick(f):
                continue
            seen.add(f.rid)
            pool.append(f)
        rank = RANK.get(slot.key, _carb_rank)
        cands[slot.key] = sorted(pool, key=rank, reverse=True)[:slot.top]
        if slot.min_n > 0 and len(cands[slot.key]) < slot.min_n:
            return []

    def vec_of(f: Food, s: int) -> tuple:
        k = (f.rid, s)
        if k not in cache:
            cache[k] = item_vec(f, s)
        return cache[k]

    beam = [(0.0, _State())]
    for slot in tpl.slots:
        scored = []
        for _, st in beam:
            for opt in _slot_options(slot, cands[slot.key]):
                if any(f.rid in st.rids for f, _ in opt) or len(st.picks) + len(opt) > MAX_ITEMS:
                    continue
                if any((f.role, f.base) in st.bases for f, _ in opt if f.role in ("protein", "carb")):
                    continue
                picks = st.picks + tuple((slot.key, f, s) for f, s in opt)
                if opt and slot.key in CUISINE_SLOTS and cuisine_clash(f for k, f, _ in picks if k in CUISINE_SLOTS):
                    continue
                if tpl.clash is not None and opt:
                    grouped: dict = {}
                    for k, f, s in picks:
                        grouped.setdefault(k, []).append((f, s))
                    if tpl.clash(grouped):
                        continue
                v = st.vec
                for f, s in opt:
                    v = vec_add(v, vec_of(f, s))
                main_rid = st.main_rid
                if main_rid is None and slot.key in ("protein", "egg", "burger", "yogurt") and opt:
                    main_rid = opt[0][0].rid
                ns = _State(
                    picks=picks,
                    vec=v,
                    rids=st.rids | {f.rid for f, _ in opt},
                    bases=st.bases | {(f.role, f.base) for f, _ in opt},
                    main_rid=main_rid,
                )
                scored.append((score_meal(v, target, _bonus(tpl, ns)), ns))
        beam = _prune(scored, C.BEAM_WIDTH)
        if not beam:
            return []
    return [Build(tpl, st.picks, st.vec, sc, _bonus(tpl, st)) for sc, st in beam if st.picks]


def _overlap(a: Build, b: Build) -> float:
    return len(a.rids & b.rids) / len(a.rids | b.rids) if (a.rids or b.rids) else 1.0


def best_builds(foods: Iterable[Food], slot: str, label: str = "", n: int = C.BUILDS_PER_PERIOD) -> list:
    """The top distinct builds for one period: different dishes first, different proteins second."""
    foods = [f for f in foods if not RESERVED_STATION.search(f.station) and not NOT_ATHLETE.search(f.name)]
    target = target_for(slot)
    cache: dict = {}
    pool: list = []
    for tpl in templates_for(slot, label):
        pool += run_template(tpl, foods, target, cache)
    pool.sort(key=lambda b: -b.score)
    picks: list = []

    def taken(b: Build, mode: str) -> bool:
        for p in picks:
            if p.rids == b.rids or _overlap(p, b) >= NEAR_DUPLICATE:
                return True  # the same plate under a different name
            same_main = p.main is not None and b.main is not None and (
                p.main.rid == b.main.rid or (bool(p.main.base) and p.main.base == b.main.base))
            if mode == "strict":
                # Different dishes and different proteins first. Reusing yogurt or eggs in another dish is fine.
                shared_staple = same_main and (p.main.kind == "dairy" or EGG.search(p.main.name))
                if p.template.key == b.template.key or (same_main and not shared_staple):
                    return True
                continue
            if p.template.key == b.template.key and (same_main or _overlap(p, b) > 0.5):
                return True  # a second chicken salad, or a second oatmeal bowl with the same toppings
        if sum(1 for q in picks if q.template.key == b.template.key) >= 2:
            return True
        uses = sum(1 for q in picks if q.main is not None and b.main is not None and q.main.rid == b.main.rid)
        # Spread the builds across the line's proteins; a thin late menu may reuse one a third time.
        return uses >= (2 if mode == "relaxed" else 3)

    floor = (pool[0].score - WEAK_GAP) if pool else 0.0
    for mode in ("strict", "relaxed", "loose"):
        if mode == "loose" and len(picks) >= 3:
            break
        for b in pool:
            if len(picks) >= n or b.score < floor:
                break
            if not taken(b, mode):
                picks.append(b)
    return sorted(picks, key=lambda b: -b.score)
