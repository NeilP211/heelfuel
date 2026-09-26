"""Approximate composition of common whole foods, for nutrients the dining labels don't report.

Values are typical USDA FoodData Central (SR Legacy) figures per 100 g of the cooked or
ready-to-eat food. They feed the "est." micronutrients on the page (magnesium, zinc, vitamin C,
vitamin A, EPA+DHA) and nothing else, which is why that score term is graded C.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class FoodRef:
    key: str
    pattern: str
    kcal: float        # per 100 g
    g_per_cup: float   # grams in one cup (0 when a cup makes no sense)
    magnesium: float   # mg
    zinc: float        # mg
    vit_c: float       # mg
    vit_a: float       # mcg RAE
    epa_dha: float     # mg
    leafy_raw: bool = False
    starchy: bool = False
    meat: bool = False
    protein: float = 0.0  # g per 100 g, set for protein-dense foods so portions can be sized from label protein


# Specific before general: a match blanks out the words it used, so "Green Beans" never
# also counts as "beans" and "Sweet Potato" never also counts as "potato".
_TABLE = [
    FoodRef("salmon", r"salmon", 206, 140, 30, 0.4, 3.7, 50, 2150, meat=True, protein=25),
    FoodRef("tuna", r"\btuna\b", 116, 150, 27, 0.8, 0, 17, 270, meat=True, protein=26),
    FoodRef("oily fish", r"sardine|mackerel|trout|herring", 200, 140, 35, 1.3, 0, 30, 1500, meat=True, protein=24),
    FoodRef("tilapia", r"tilapia", 128, 140, 34, 0.4, 0, 0, 135, meat=True, protein=26),
    FoodRef("white fish", r"\bcod\b|pollock|haddock|flounder|catfish|swai|whitefish|mahi|swordfish|\bfish\b", 110, 140, 35, 0.5, 0.5, 15, 180, meat=True, protein=23),
    FoodRef("shrimp", r"shrimp|prawn|scampi", 110, 145, 37, 1.6, 0, 0, 270, meat=True, protein=24),
    FoodRef("shellfish", r"crab|lobster|scallop|clam|mussel|oyster|calamari", 100, 140, 45, 3.5, 3, 5, 300, meat=True, protein=20),
    FoodRef("egg", r"\beggs?\b|omelet|frittata|quiche", 155, 220, 10, 1.1, 0, 149, 40, protein=13),
    FoodRef("chicken", r"chicken", 165, 140, 29, 1.0, 0, 6, 30, meat=True, protein=31),
    FoodRef("turkey", r"turkey", 150, 140, 27, 1.8, 0, 0, 20, meat=True, protein=29),
    FoodRef("lamb", r"\blamb\b|gyro", 258, 140, 23, 4.5, 0, 0, 50, meat=True, protein=26),
    FoodRef("beef", r"beef|steak|brisket|(?<!bean )(?<!veggie )burger(?! bun)|barbacoa|meatball|meat sauce|chili con carne|meatloaf|bolognese", 250, 140, 21, 6.3, 0, 0, 20, meat=True, protein=26),
    FoodRef("pork", r"pork|\bham\b|bacon|sausage|carnitas|bratwurst|salami|pepperoni|chorizo|prosciutto", 250, 140, 20, 2.5, 0.5, 2, 10, meat=True, protein=24),
    FoodRef("tofu", r"tofu", 144, 250, 58, 1.6, 0.2, 0, 0, protein=17),
    FoodRef("edamame", r"edamame", 121, 155, 64, 1.4, 6, 9, 0, protein=12),
    FoodRef("hummus", r"hummus", 166, 246, 71, 1.8, 0, 1, 0),
    FoodRef("chickpea", r"chickpea|garbanzo|falafel", 164, 164, 48, 1.5, 1.3, 1, 0),
    FoodRef("lentil", r"lentil|\bdal\b|dhal", 116, 198, 36, 1.3, 1.5, 0, 0),
    FoodRef("green beans", r"green beans?|string beans?|haricot", 35, 125, 18, 0.2, 10, 35, 0),
    FoodRef("beans", r"black beans?|kidney beans?|pinto|white beans?|cannellini|navy beans?|refried|red beans|\bbeans\b", 130, 172, 60, 1.0, 0, 0, 0),
    FoodRef("spinach raw", r"baby spinach|spinach salad|raw spinach", 23, 30, 79, 0.5, 28, 469, 0, leafy_raw=True),
    FoodRef("spinach", r"spinach", 23, 180, 87, 0.8, 10, 524, 0),
    FoodRef("kale", r"\bkale\b", 36, 130, 18, 0.2, 41, 681, 0),
    FoodRef("collards", r"collards?|mustard greens|turnip greens", 33, 190, 27, 0.2, 18, 380, 0),
    FoodRef("broccoli", r"broccoli", 35, 156, 21, 0.4, 65, 77, 0),
    FoodRef("brussels", r"brussels( sprouts)?", 36, 156, 20, 0.3, 62, 38, 0),
    FoodRef("cauliflower", r"cauliflower", 23, 124, 9, 0.2, 44, 1, 0),
    FoodRef("red cabbage", r"red cabbage|purple cabbage", 31, 89, 16, 0.2, 57, 56, 0),
    FoodRef("cabbage", r"bok choy|cabbage|slaw", 22, 110, 12, 0.2, 30, 60, 0),
    FoodRef("sweet potato", r"sweet potato(es)?|\byams?\b", 90, 200, 27, 0.3, 20, 961, 0, starchy=True),
    FoodRef("carrot", r"carrots?", 35, 156, 10, 0.2, 3.6, 852, 0),
    FoodRef("bell pepper", r"bell peppers?|mixed peppers|red peppers?|green peppers?|roasted peppers?|grilled peppers?|peppers and onions?|pepper onion|\bpeppers\b", 26, 150, 11, 0.2, 100, 90, 0),
    FoodRef("tomato", r"tomato(es)?|pico de gallo|salsa", 18, 180, 11, 0.2, 14, 42, 0),
    FoodRef("mushroom", r"mushrooms?", 22, 156, 9, 0.5, 2, 0, 0),
    FoodRef("squash", r"zucchini|squash", 18, 180, 17, 0.3, 13, 30, 0),
    FoodRef("eggplant", r"eggplant", 35, 99, 11, 0.1, 1, 2, 0),
    FoodRef("asparagus", r"asparagus", 22, 180, 14, 0.6, 7.7, 50, 0),
    FoodRef("okra", r"okra", 22, 160, 36, 0.4, 16, 14, 0),
    FoodRef("beets", r"\bbeets?\b", 44, 170, 23, 0.4, 3.6, 2, 0),
    FoodRef("corn", r"\bcorn\b(?! syrup| tortilla| chip)", 96, 164, 26, 0.6, 5.5, 9, 0, starchy=True),
    FoodRef("peas", r"\bpeas\b|green peas?", 84, 160, 39, 1.2, 14, 40, 0, starchy=True),
    FoodRef("onion", r"onions?|scallions?|leeks?", 40, 160, 10, 0.2, 7, 0, 0),
    FoodRef("lettuce", r"lettuce|spring mix|salad mix|mixed greens|romaine|arugula|field greens", 15, 50, 13, 0.2, 9, 370, 0, leafy_raw=True),
    FoodRef("cucumber", r"cucumbers?", 15, 120, 13, 0.2, 2.8, 5, 0),
    FoodRef("avocado", r"avocado|guacamole", 160, 150, 29, 0.6, 10, 7, 0),
    FoodRef("orange", r"oranges?|clementine|mandarin|tangerine|citrus", 47, 180, 10, 0.1, 53, 11, 0),
    FoodRef("strawberry", r"strawberr(y|ies)", 32, 150, 13, 0.1, 59, 1, 0),
    FoodRef("blueberry", r"blueberr(y|ies)", 57, 148, 6, 0.2, 10, 3, 0),
    FoodRef("berries", r"berries|raspberr(y|ies)|blackberr(y|ies)", 45, 145, 15, 0.3, 25, 2, 0),
    FoodRef("pineapple", r"pineapples?", 50, 165, 12, 0.1, 48, 3, 0),
    FoodRef("cantaloupe", r"cantaloupe", 34, 160, 12, 0.2, 37, 169, 0),
    FoodRef("melon", r"honeydew|melon", 36, 170, 10, 0.1, 18, 3, 0),
    FoodRef("grapes", r"grapes?(?!fruit)", 69, 150, 7, 0.1, 3.2, 3, 0),
    FoodRef("banana", r"bananas?", 89, 150, 27, 0.2, 8.7, 3, 0),
    FoodRef("mango", r"mangos?|mangoes", 60, 165, 10, 0.1, 36, 54, 0),
    FoodRef("kiwi", r"kiwis?", 61, 180, 17, 0.1, 93, 4, 0),
    FoodRef("apple", r"apples?(?! jack)", 52, 125, 5, 0.0, 4.6, 3, 0),
    FoodRef("oats", r"oatmeal|\boats\b|steel cut", 71, 234, 27, 1.0, 0, 0, 0),
    FoodRef("quinoa", r"quinoa", 120, 185, 64, 1.1, 0, 1, 0),
    FoodRef("brown rice", r"brown rice|wild rice|farro|barley|bulgur", 123, 195, 39, 0.6, 0, 0, 0),
    FoodRef("rice", r"\brice\b", 130, 158, 12, 0.5, 0, 0, 0),
    FoodRef("whole wheat", r"whole wheat|whole grain|multigrain", 250, 0, 60, 1.6, 0, 0, 0),
    FoodRef("pasta", r"pasta|penne|spaghetti|noodles?|macaroni|ravioli|linguine|rotini|lo mein", 158, 140, 18, 0.5, 0, 0, 0),
    FoodRef("potato", r"potato(es)?|hash ?browns?|\btots\b|fries|home fries", 93, 210, 28, 0.4, 9.6, 1, 0, starchy=True),
    FoodRef("plantain", r"plantains?", 116, 200, 32, 0.1, 10, 45, 0, starchy=True),
    FoodRef("sunflower seeds", r"sunflower seeds?|sun ?butter", 590, 140, 200, 5.0, 1.4, 3, 0),
    FoodRef("pumpkin seeds", r"pumpkin seeds?|pepitas?", 559, 130, 592, 7.8, 1.9, 16, 0),
    FoodRef("almonds", r"almonds?", 579, 140, 270, 3.1, 0, 0, 0),
    FoodRef("peanuts", r"peanuts?", 588, 258, 168, 2.5, 0, 0, 0),
    FoodRef("greek yogurt", r"greek yogurt", 59, 245, 11, 0.5, 0, 0, 0, protein=10),
    FoodRef("yogurt", r"yogurt|parfait", 63, 245, 12, 0.6, 0.5, 14, 0),
    FoodRef("cottage cheese", r"cottage cheese", 98, 225, 8, 0.4, 0, 37, 0, protein=11),
    FoodRef("milk", r"\bmilk\b|soymilk|soy milk", 50, 244, 11, 0.4, 0, 46, 0),
    FoodRef("cheese", r"cheese|cheddar|mozzarella|parmesan|feta|provolone|monterey|pepper jack|swiss|queso", 380, 113, 25, 3.0, 0, 250, 0, protein=25),
    FoodRef("mixed vegetables", r"vegetables?|veggies?|primavera|ratatouille|stir ?fry", 50, 150, 15, 0.3, 15, 150, 0),
    FoodRef("fruit", r"fruit", 50, 160, 10, 0.1, 20, 20, 0),
]
_COMPILED = [(f, re.compile(f.pattern, re.I)) for f in _TABLE]
_PLANT_BASED = re.compile(r"vegan|impossible|beyond|plant[- ]based|meatless|veggie burger|black bean burger|soy ", re.I)


def match_foods(name: str, limit: int = 2) -> list[FoodRef]:
    """Foods named in an item name, most specific first ("Sauteed Kale & Brussels Sprouts" -> kale, brussels)."""
    text = name
    plant = bool(_PLANT_BASED.search(name))
    found: list[FoodRef] = []
    for ref, rx in _COMPILED:
        m = rx.search(text)
        if not m:
            continue
        text = text[:m.start()] + " " * (m.end() - m.start()) + text[m.end():]
        if plant and ref.meat:
            continue  # "Impossible Sausage" is not pork
        found.append(ref)
        if len(found) >= limit:
            break
    return found
