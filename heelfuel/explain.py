"""Words for the page: meal titles, why a meal ranks, its tradeoffs, and how to make it taste good."""

from __future__ import annotations

import re
from typing import Iterable, Optional

from . import config as C
from .classify import Food
from .formats import EGGISH, designed_pairing, main_protein, meal_format
from .optimize import Combo, realism_points
from .score import IX, SlotTarget, score_vec

MICRO_META = [
    # key, label, unit, estimated?
    ("potassium", "Potassium", "mg", False),
    ("calcium", "Calcium", "mg", False),
    ("iron", "Iron", "mg", False),
    ("vit_d", "Vitamin D", "mcg", False),
    ("magnesium", "Magnesium", "mg", True),
    ("zinc", "Zinc", "mg", True),
    ("vit_c", "Vitamin C", "mg", True),
    ("vit_a", "Vitamin A", "mcg", True),
    ("epa_dha", "Omega-3 (EPA+DHA)", "mg", True),
]


def short_name(name: str) -> str:
    """'Bob's Red Mill(R) Gluten Free Oats' -> 'Bob's Red Mill Gluten Free Oats'; drop trademark marks."""
    s = re.sub(r"[®™]", "", name)
    s = re.sub(r"\s*\((?:made without gluten)\)", "", s, flags=re.I)
    return " ".join(s.split())


def lower_first(s: str) -> str:
    return s[:1].lower() + s[1:] if s and not s[:2].isupper() else s


def title_for(combo: Combo, slot: str) -> str:
    fmt = meal_format(combo.items, slot)
    main = main_protein(combo.items)
    if main is None:
        carb = next((f for f, _ in combo.items if f.role == "carb"), None)
        return short_name(carb.name) + " plate" if carb else "Build-your-own plate"
    servings = dict((f.rid, s) for f, s in combo.items).get(main.rid, 1)
    name = short_name(main.name)
    lead = {2: "Double ", 3: "Triple "}.get(servings, "") if main.role == "protein" and fmt != "sandwich" else ""
    if fmt == "yogurt bowl":
        return f"{name} bowl"
    if fmt == "breakfast plate":
        eggs = next((f for f, _ in combo.items if f.role == "protein" and EGGISH.search(f.name)), main)
        es = dict((f.rid, s) for f, s in combo.items).get(eggs.rid, 1)
        elead = {2: "Double ", 3: "Triple "}.get(es, "")
        carb = next((f for f, _ in combo.items if f.role == "carb"), None)
        return f"{elead}{short_name(eggs.name)} with {short_name(carb.name)}" if carb else f"{elead}{short_name(eggs.name)} plate"
    if fmt == "sandwich":
        if "sandwich" in main.tags:
            return name
        bread = next((f for f, _ in combo.items if "bread" in f.tags), None)
        what = "wrap" if bread and re.search(r"wrap|tortilla", bread.name, re.I) else "sandwich"
        return f"{name} {what}"
    if fmt == "salad":
        return f"{lead}{name} salad"
    if fmt == "pasta":
        return f"{lead}{name}" if "pasta" in main.tags else f"{lead}{name} pasta"
    if fmt == "bowl":
        return f"{lead}{name}" if re.search(r"\bbowl\b", name, re.I) else f"{lead}{name} bowl"
    if fmt == "pizza":
        return "Pizza night, balanced"
    return f"{lead}{name} plate"


# ---------------------------------------------------------------- flavor ideas

FLAVOR_PREFS = {
    "bowl": ["pico de gallo", "salsa verde", "salsa", "guacamole", "sriracha", "hot sauce", "texas pete", "scallion", "lime", "soy sauce"],
    "plate": ["tzatziki", "salsa", "pico de gallo", "hot sauce", "texas pete", "sriracha", "lemon", "mustard", "salsa verde"],
    "salad": ["red wine vinegar", "balsamic", "lite italian", "lemon", "oil and vinegar", "salsa"],
    "sandwich": ["spicy brown mustard", "yellow mustard", "mustard", "pickle", "banana pepper", "hot sauce"],
    "pasta": ["marinara", "roasted olive oil tomato sauce", "red pepper", "hot sauce"],
    "pizza": ["hot sauce", "red pepper"],
    "breakfast plate": ["salsa", "hot sauce", "texas pete", "sriracha", "pico de gallo"],
    "yogurt bowl": ["cinnamon", "honey"],
    None: ["hot sauce", "texas pete", "salsa", "sriracha", "mustard"],
}


def pick_flavor(fmt: Optional[str], condiments: Iterable[Food], combo: Combo) -> Optional[Food]:
    """A low-calorie flavor from what's actually on the line in this period."""
    have = {f.rid for f, _ in combo.items}
    ok = [f for f in condiments if f.rid not in have and not f.suspect and f.nutrition.kcal <= 45
          and f.added_sugar <= 4 and not f.dyes and not f.red_flags]
    text = " ".join(short_name(f.name).lower() for f, _ in combo.items)
    prefs = list(FLAVOR_PREFS.get(fmt, FLAVOR_PREFS[None]))
    if re.search(r"tofu|sushi|edamame|teriyaki|soy|poke|asian", text) and fmt in ("bowl", "plate", "salad", None):
        prefs = ["sriracha", "siracha", "scallion", "hot sauce", "texas pete"] + prefs
    if fmt == "plate" and re.search(r"shawarma|greek|mediterranean|falafel|gyro|lamb", text):
        prefs = ["tzatziki", "lemon", "hot sauce"] + prefs
    for want in prefs:
        for f in ok:
            if want in f.name.lower():
                return f
    return None


def _join(names: list[str]) -> str:
    names = [n for n in names if n]
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " and " + names[-1]


def _portion(f: Food, s: int) -> str:
    """Natural phrasing for a portion, keeping the name as it appears on the station sign."""
    n = short_name(f.name)
    if s <= 1:
        return n
    if "leafy" in f.tags:
        return f"a double handful of {n}" if s == 2 else f"{s} handfuls of {n}"
    if f.role == "protein" and f.unit not in ("slice",):
        return {2: "a double portion of ", 3: "a triple portion of "}.get(s, f"{s} portions of ") + n
    if f.unit == "slice":
        return f"{s} slices of {n}"
    if f.unit in ("cup", "tbsp", "tsp", "oz", "floz", "g"):
        return f"{s} scoops of {n}"
    return f"{s} servings of {n}"


def tasty_idea(combo: Combo, slot: str, condiments: Iterable[Food]) -> str:
    fmt = meal_format(combo.items, slot)
    items = combo.items
    main = main_protein(items)
    side_dairy = slot in ("lunch", "dinner") or fmt not in ("yogurt bowl",)
    prots = [(f, s) for f, s in items if f.role == "protein" and not (f.kind == "dairy" and side_dairy and f is not main)]
    carbs = [(f, s) for f, s in items if f.role == "carb"]
    veg = [(f, s) for f, s in items if f.role == "produce" and f.kind != "fruit"]
    fruit = [(f, s) for f, s in items if f.role == "produce" and f.kind == "fruit"]
    extras = [(f, s) for f, s in items if f.role == "extra" or (f.role == "protein" and (f, s) not in prots)]
    flavor = pick_flavor(fmt, condiments, combo)
    flavor_name = short_name(flavor.name) if flavor else ""
    p_txt = _join([_portion(f, s) for f, s in prots]) or (short_name(main.name) if main else "")
    c_txt = _join([_portion(f, s) for f, s in carbs])
    v_txt = _join([_portion(f, s) for f, s in veg])
    fr_txt = _join([short_name(f.name) for f, _ in fruit])
    x_txt = _join([short_name(f.name) for f, _ in extras if f.kind != "sauce"])

    if fmt == "yogurt bowl":
        base = f"Stir {fr_txt or 'the fruit'} into {p_txt}"
        base += f", then top with {c_txt}." if c_txt else "."
        return base + " Want it sweeter? A drizzle of honey adds about 5 g sugar, still under the 10 g meal cap."
    if fmt == "breakfast plate":
        eggs = [(f, s) for f, s in prots if EGGISH.search(f.name)] or prots[:1]
        sides = [(f, s) for f, s in prots if (f, s) not in eggs]
        e_txt = _join([_portion(f, s) for f, s in eggs])
        s = e_txt[:1].upper() + e_txt[1:]
        if flavor:
            s += f" with {flavor_name} on top"
        if c_txt:
            s += f", plus {c_txt}"
        s += "."
        side_txt = _join([_portion(f, s2) for f, s2 in sides] + ([fr_txt] if fr_txt else []) + ([x_txt] if x_txt else []))
        if side_txt:
            s += f" On the side: {side_txt}."
        return s
    if fmt == "bowl":
        s = f"Build a bowl: {c_txt or 'rice'} on the bottom, {p_txt} on top"
        if veg:
            s += f", then {v_txt}"
        s += "."
        if flavor:
            s += f" Finish with {flavor_name} for flavor without many calories."
        if fruit:
            s += f" {fr_txt} on the side."
        if x_txt:
            s += f" Add {x_txt}."
        return s
    if fmt == "salad":
        greens = [_portion(f, s) for f, s in veg if "leafy" in f.tags]
        toppings = [_portion(f, s) for f, s in veg if "leafy" not in f.tags]
        s = f"Start with {_join(greens) or 'greens'}, pile on {p_txt}"
        if c_txt:
            s += f" and {c_txt}"
        if toppings:
            s += f", then add {_join(toppings)}"
        s += "."
        if flavor:
            s += f" Dress it with {flavor_name} (about {flavor.nutrition.kcal:.0f} kcal)."
        else:
            s += " Keep dressing to about 2 tablespoons, or use vinegar with a splash of oil."
        if fruit:
            s += f" {fr_txt} on the side."
        if x_txt:
            s += f" Add {x_txt}."
        return s
    if fmt == "sandwich":
        if main is not None and "sandwich" in main.tags:
            s = f"Grab the {short_name(main.name)}"
            if veg or fruit:
                s += f" with {_join([v_txt, fr_txt])} on the side"
            return s + "."
        bread = _join([short_name(f.name) for f, _ in carbs])
        s = f"Ask for {p_txt} on {bread or 'your bread'}"
        if veg:
            s += f", loaded with {v_txt}"
        s += "."
        if flavor:
            s += f" {flavor_name} instead of mayo saves about 90 kcal."
        if fruit:
            s += f" {fr_txt} on the side."
        return s
    if fmt == "pasta":
        sauce = [short_name(f.name) for f, _ in extras if f.kind == "sauce"]
        pasta_carbs = [(f, s) for f, s in carbs if "pasta" in f.tags]
        other_carbs = [(f, s) for f, s in carbs if "pasta" not in f.tags]
        greens = [(f, s) for f, s in veg if "leafy" in f.tags]
        cooked = [(f, s) for f, s in veg if "leafy" not in f.tags]
        if pasta_carbs:
            pc = _join([_portion(f, s) for f, s in pasta_carbs])
            s = pc[:1].upper() + pc[1:]
            s += f" with {_join(sauce)}" if sauce else ""
            s += f", topped with {p_txt}" if p_txt else ""
            if cooked:
                s += f" and {_join([_portion(f, s2) for f, s2 in cooked])} mixed in"
            s += "."
            if not sauce:
                s += " Choose the tomato sauce over Alfredo to keep saturated fat down."
        else:
            s = f"Get {p_txt}"
            if other_carbs:
                s += f" with {_join([_portion(f, s2) for f, s2 in other_carbs])}"
            if cooked:
                s += f" and {_join([_portion(f, s2) for f, s2 in cooked])}"
            s += "."
        if greens:
            s += f" Add a side salad of {_join([_portion(f, s2) for f, s2 in greens])}"
            s += f" with {flavor_name}." if flavor and fmt == "pasta" and "vinegar" in flavor_name.lower() else "."
        if fruit:
            s += f" {fr_txt} for dessert."
        return s
    s = f"Plate {p_txt}"
    if c_txt:
        s += f" with {c_txt}"
    if veg:
        s += f", with {v_txt} on the side"
    s += "."
    if flavor:
        s += f" Add {flavor_name} for flavor."
    if fruit:
        s += f" {fr_txt} for dessert."
    if x_txt:
        s += f" Grab {x_txt} too."
    if designed_pairing(items) and main is not None:
        here = [short_name(f.name) for f, _ in items if f.station == main.station]
        if len(here) >= 2:
            s += f" {_join(here)} are all at {main.station}."
    return s


# ---------------------------------------------------------------- why it ranks / tradeoffs


def _fmt_int(x: float) -> str:
    return f"{x:,.0f}"


def _culprit(items, pred) -> str:
    names = [short_name(f.name) for f, _ in items if pred(f)]
    return _join(names[:2])


def pros_cons(combo: Combo, target: SlotTarget, slot: str, period: str = "") -> tuple[list[str], list[str]]:
    v = combo.vec
    sc, parts = score_vec(v, target, realism_points(combo.items, slot), explain=True)
    kcal, protein, carbs, fat = v[0], v[1], v[2], v[3]
    fiber, sodium = v[IX["fiber"]], v[IX["sodium"]]
    slot_word = (period or C.SLOT_LABELS.get(slot, slot)).lower()
    pros: list[tuple[float, str]] = []
    cons: list[tuple[float, str]] = []
    items = combo.items

    # Protein first: it's the top priority.
    if protein >= target.protein:
        pros.append((10, f"{protein:.0f} g protein covers the {target.protein:.0f} g {slot_word} target"))
    elif protein >= 0.95 * target.protein:
        pros.append((10, f"{protein:.0f} g protein, right at the {target.protein:.0f} g {slot_word} target"))
    else:
        cons.append((9, f"Protein is short: {protein:.0f} g of the {target.protein:.0f} g target, the best this line allows"))

    cq = parts["_cq"]
    if carbs >= 0.7 * target.carbs and cq >= 0.75:
        srcs = []
        if any(f.kind == "legume" for f, _ in items):
            srcs.append("beans")
        if any("whole_grain" in f.tags for f, _ in items):
            srcs.append("whole grains")
        if any(f.kind == "fruit" for f, _ in items):
            srcs.append("fruit")
        if any(f.kind == "starchy_veg" for f, _ in items):
            srcs.append("potatoes or corn")
        pros.append((6, f"{carbs:.0f} g carbs, mostly from {_join(srcs) or 'whole foods'}"))
    elif carbs >= 0.7 * target.carbs:
        pros.append((3, f"{carbs:.0f} g carbs to fuel training"))
    else:
        cons.append((5, f"Light on carbs for a training day ({carbs:.0f} g vs about {target.carbs:.0f} g); add fruit or a roll if you lifted"))

    cups = v[IX["produce_cups"]]
    if cups >= max(1.0, 0.8 * target.produce_cups):
        pros.append((5, f"About {cups:.1f} cups of fruit and veg"))
    if fiber >= max(8.0, target.fiber):
        pros.append((4, f"{fiber:.0f} g fiber"))
    epa = v[IX["epa_dha"]]
    if epa >= 400:
        fish = _culprit(items, lambda f: "fish_oily" in f.tags) or "the fish"
        pros.append((6, f"About {epa:,.0f} mg omega-3s from {lower_first(fish)}"))
    upf = parts["_upf_share"]
    if upf <= 0.15:
        pros.append((4, f"{100 * (1 - upf):.0f}% of calories from minimally processed food"))
    if sodium <= 0.6 * target.sodium_allowance:
        pros.append((2, f"Low sodium ({_fmt_int(sodium)} mg), less water retention"))
    if slot == "late_night" and v[IX["slow_protein"]] >= 10:
        src = _culprit(items, lambda f: f.slow_protein > 0)
        pros.append((5, f"Slow-digesting protein from {lower_first(src)} for overnight recovery"))
    if designed_pairing(items) >= 1:
        main = main_protein(items)
        pros.append((3, f"A chef-built plate: everything but the extras is at {main.station}"))
    for key, label, unit, est in MICRO_META[:4]:
        dv = C.DV[key]
        if v[IX[key]] >= 0.4 * dv:
            pros.append((2, f"{100 * v[IX[key]] / dv:.0f}% of a day's {label.lower()}"))

    # Tradeoffs, biggest point losses first.
    def lost(key):
        return -parts.get(key, 0.0)

    if kcal < target.kcal_lo:
        cons.append((6, f"On the light side ({kcal:.0f} kcal vs about {target.kcal:.0f}); a fruit, milk or extra scoop closes the gap"))
    elif kcal > target.kcal_hi:
        cons.append((4, f"A big plate ({kcal:.0f} kcal vs about {target.kcal:.0f}); go lighter at your next meal"))
    if lost("sodium") > 0.2:
        cons.append((lost("sodium") + 2, f"Sodium {_fmt_int(sodium)} mg ({100 * sodium / C.DAILY.sodium_ref:.0f}% of the 2,300 mg daily reference); fine if you sweat a lot, just drink water"))
    if lost("added_sugar") > 0.1:
        src = _culprit(items, lambda f: f.added_sugar >= 3)
        cons.append((lost("added_sugar") + 2, f"{v[IX['added_sugar']]:.0f} g added sugar, over the 10 g per-meal guideline" + (f" (from {src})" if src else "")))
    if v[IX["processed_meat_g"]] > 0:
        src = _culprit(items, lambda f: f.processed_meat_g > 0)
        cons.append((lost("processed_meat") + 1.5, f"Processed meat ({src}), about {v[IX['processed_meat_g']]:.0f} g"))
    if parts["_fried_share"] > 0.05:
        src = _culprit(items, lambda f: f.fried)
        cons.append((lost("fried") + 1, f"{src} is fried"))
    if lost("trans_fat") > 0.2:
        src = _culprit(items, lambda f: f.pho) or _culprit(items, lambda f: f.nutrition.trans_fat > 0)
        cons.append((lost("trans_fat") + 1, f"Industrial trans fat in {src}"))
    if lost("sat_fat") > 0.5:
        cons.append((lost("sat_fat"), f"{v[IX['sat_fat']]:.0f} g saturated fat, over 10% of this meal's calories"))
    dyed = [(f, d) for f, _ in items for d in f.dyes]
    if dyed:
        by_item: dict = {}
        for f, d in dyed:
            by_item.setdefault(short_name(f.name), []).append(d)
        txt = "; ".join(f"{' + '.join(ds)} in {n}" for n, ds in by_item.items())
        cons.append((lost("dyes") + 0.5, f"Synthetic dyes ({txt}): a small deduction, the evidence in adults is weak"))
    reds = [(f, r) for f, _ in items for r in f.red_flags]
    if reds:
        txt = "; ".join(f"{r} in {short_name(f.name)}" for f, r in reds)
        cons.append((lost("red_flag_additives") + 0.6, f"{txt} (restricted in the EU or California; small deduction)"))
    emul = [(f, e) for f, _ in items for e, _ in f.emulsifiers]
    if emul:
        txt = "; ".join(f"{e} in {short_name(f.name)}" for f, e in emul[:3])
        cons.append((lost("emulsifiers"), f"{txt} (gut-health evidence is early; minor)"))
    sw = [(f, s) for f, _ in items for s in f.sweeteners]
    if sw:
        txt = "; ".join(f"{s} in {short_name(f.name)}" for f, s in sw)
        cons.append((lost("sweeteners") + 0.3, f"{txt} (minor)"))
    if upf >= 0.4:
        src = _culprit(items, lambda f: f.upf >= 0.6)
        cons.append((lost("whole_food") if "whole_food" in parts else 1.0, f"{100 * upf:.0f}% of calories are ultra-processed" + (f" ({src})" if src else "")))
    if v[IX["dairy_cups"]] >= 1.5:
        cons.append((0.4, "A lot of dairy; if you're acne-prone, water instead of milk is an easy swap"))
    est_sugar = [f for f, _ in items if f.added_sugar_estimated and f.added_sugar >= 3]
    if est_sugar:
        cons.append((0.2, f"Added sugar for {_join([short_name(f.name) for f in est_sugar[:2]])} is estimated (the label has no added-sugar row)"))

    pros.sort(key=lambda x: -x[0])
    cons.sort(key=lambda x: -x[0])
    return [p for _, p in pros[:4]], [c for _, c in cons[:4]]


def compare_to(best: Combo, other: Combo) -> str:
    """One line on how a runner-up differs from #1."""
    b, o = best.vec, other.vec
    bits = []
    dp = o[1] - b[1]
    if abs(dp) >= 5:
        bits.append(f"{abs(dp):.0f} g {'more' if dp > 0 else 'less'} protein")
    dk = o[0] - b[0]
    if abs(dk) >= 100:
        bits.append(f"{abs(dk):.0f} kcal {'more' if dk > 0 else 'less'}")
    dn = o[IX["sodium"]] - b[IX["sodium"]]
    if abs(dn) >= 300:
        bits.append(f"{abs(dn):,.0f} mg {'more' if dn > 0 else 'less'} sodium")
    df = o[IX["fiber"]] - b[IX["fiber"]]
    if abs(df) >= 4:
        bits.append(f"{abs(df):.0f} g {'more' if df > 0 else 'less'} fiber")
    if not bits:
        return "Close to #1 on the numbers; pick whichever sounds better."
    return "Compared with #1: " + _join(bits) + "."


def micros(v: tuple) -> list[dict]:
    out = []
    for key, label, unit, est in MICRO_META:
        amt = v[IX[key]]
        pct = 100.0 * amt / C.DV[key]
        out.append({"key": key, "label": label, "amount": round(amt, 1 if amt < 10 else 0), "unit": unit,
                    "pct": round(pct), "est": est})
    return out
