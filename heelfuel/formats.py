"""Recognize what kind of meal a set of items adds up to (plate, bowl, salad, sandwich...).

Used twice: the optimizer gives recognizable meals a small coherence bonus, and the page uses the
format to name the meal and write the "make it tasty" idea.
"""

from __future__ import annotations

import re
from typing import Optional

BOWL_STATION = re.compile(r"burrito|bowl|sushi|create|build your own|made-to-order|mongolian|stir ?fry|wok|poke", re.I)
DELI_STATION = re.compile(r"deli|sandwich|\bsub\b", re.I)
SIDE_LINE = re.compile(r"salad bar|hummus|fruit", re.I)
EGGISH = re.compile(r"\begg|omelet|scramble|frittata|quiche", re.I)

FORMATS = ("yogurt bowl", "breakfast plate", "sandwich", "pizza", "pasta", "salad", "bowl", "plate")


def main_protein(items: tuple):
    """The dish the meal is built around: the biggest protein source, preferring real protein items
    over sides like a cup of Greek yogurt or milk at lunch."""
    for roles in (("protein",), ("protein", "extra")):
        best, grams = None, 0.0
        for f, s in items:
            if f.role not in roles:
                continue
            if roles == ("protein",) and f.kind == "dairy" and any(
                    g.role == "protein" and g.kind != "dairy" for g, _ in items):
                continue
            g = f.nutrition.protein * s
            if g > grams:
                best, grams = f, g
        if best is not None:
            return best
    return None


def meal_format(items: tuple, slot: str) -> Optional[str]:
    carbs = [f for f, _ in items if f.role == "carb"]
    produce = [f for f, _ in items if f.role == "produce"]
    main = main_protein(items)
    tags = set().union(*(f.tags for f, _ in items)) if items else set()
    breads = [c for c in carbs if "bread" in c.tags]

    if slot in ("breakfast", "late_night") and main is not None:
        if main.kind == "dairy" and any(f.kind == "fruit" for f in produce):
            return "yogurt bowl"
        breakfast_sides = [c for c in carbs if "breakfast_only" in c.tags or "bread" in c.tags
                           or "potato" in c.tags or c.kind == "starchy_veg"]
        if EGGISH.search(main.name) and (breakfast_sides or (not carbs and any(f.kind == "fruit" for f in produce))):
            return "breakfast plate"
    if "sandwich" in tags:
        return "sandwich"
    if main is not None and breads and (DELI_STATION.search(main.station)
                                        or any(DELI_STATION.search(b.station) for b in breads)):
        return "sandwich"
    if any("pizza" in f.tags for f in carbs):
        return "pizza"
    if main is not None and (any("pasta" in f.tags for f in carbs) or "pasta" in main.tags):
        return "pasta"
    greens = sum(f.produce_cups * s for f, s in items if f.role == "produce" and "leafy" in f.tags)
    if main is not None and greens >= 0.4 and not breads:
        return "salad"
    if main is not None and carbs and not breads:
        same_line = any(c.station == main.station for c in carbs)
        rice_or_grain = any(("rice" in c.tags or c.kind == "grain") for c in carbs)
        beans = any(c.kind == "legume" for c in carbs)
        if same_line and BOWL_STATION.search(main.station):
            return "bowl"
        if rice_or_grain and beans and len({f.station for f in carbs} | {main.station}) <= 2:
            return "bowl"
        if same_line:
            return "plate"
    return None


def designed_pairing(items: tuple) -> int:
    """How many parts of the meal come from the main protein's own station (a chef-built plate)."""
    main = main_protein(items)
    if main is None or re.search(r"salad|hummus|deli|bread|bagel", main.station, re.I):
        return 0
    n = 0
    if any(f.role == "carb" and f.station == main.station for f, _ in items):
        n += 1
    if any(f.role == "produce" and f.station == main.station for f, _ in items):
        n += 1
    return n


def protein_mix(items: tuple) -> bool:
    """Two protein dishes pulled from two different hot lines (tofu from one, chili from another)."""
    lines = {f.station for f, _ in items if f.role == "protein" and not SIDE_LINE.search(f.station)}
    return len(lines) > 1


def sweet_savory_clash(items: tuple) -> bool:
    """A yogurt or oatmeal base next to beans, rice, chicken or raw onions is not a meal anyone builds."""
    if any(EGGISH.search(f.name) for f, _ in items):
        return False  # eggs with oatmeal and fruit is a normal breakfast
    main = main_protein(items)
    sweet_base = (main is not None and main.kind == "dairy") or any(
        f.role == "carb" and ("breakfast_only" in f.tags or f.kind == "cereal") for f, _ in items)
    if not sweet_base:
        return False
    for f, _ in items:
        if f.role == "produce" and f.kind == "veg":
            return True
        if f.role == "carb" and (f.kind in ("legume", "starchy_veg") or f.tags & {"rice", "pasta", "sandwich"}):
            return True
        if f.role == "protein" and f.kind != "dairy":
            return True
    return False


PLANT_PROTEIN = re.compile(r"tofu|tempeh|edamame|soy|vegan|impossible|beyond|seitan|black bean burger|chik'?n", re.I)


def plant_meat_mix(items: tuple) -> bool:
    """Tofu cubes next to a beef roast: fine nutritionally, not a plate anyone assembles."""
    prots = [f for f, _ in items if f.role == "protein" and f.kind != "dairy"]
    plant = any(PLANT_PROTEIN.search(f.name) for f in prots)
    meat = any(f.tags & {"poultry", "red_meat", "pork", "fish", "fish_oily", "shellfish"} and not PLANT_PROTEIN.search(f.name)
               for f in prots)
    return plant and meat
