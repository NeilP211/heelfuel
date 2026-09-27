"""Everything the page says about a build: steps by station, % Daily Values, highlights, tradeoffs."""

from __future__ import annotations

import re

from . import config as C
from .builds import Build, nice
from .classify import Food
from .score import score_meal

# Label rows in the order a Nutrition Facts panel shows them. "est" rows aren't on UNC's labels.
DV_ROWS = [
    # key, label, unit, indent, estimated
    ("fat", "Total Fat", "g", 0, False),
    ("sat_fat", "Saturated Fat", "g", 1, False),
    ("trans_fat", "Trans Fat", "g", 1, False),
    ("cholesterol", "Cholesterol", "mg", 0, False),
    ("sodium", "Sodium", "mg", 0, False),
    ("carbs", "Total Carbohydrate", "g", 0, False),
    ("fiber", "Dietary Fiber", "g", 1, False),
    ("sugars", "Total Sugars", "g", 1, False),
    ("added_sugar", "Added Sugars", "g", 2, False),
    ("protein", "Protein", "g", 0, False),
    ("vit_d", "Vitamin D", "mcg", 0, False),
    ("calcium", "Calcium", "mg", 0, False),
    ("iron", "Iron", "mg", 0, False),
    ("potassium", "Potassium", "mg", 0, False),
    ("magnesium", "Magnesium", "mg", 0, True),
    ("zinc", "Zinc", "mg", 0, True),
    ("vit_c", "Vitamin C", "mg", 0, True),
    ("vit_a", "Vitamin A", "mcg", 0, True),
    ("epa_dha", "Omega-3 (EPA+DHA)", "mg", 0, True),
]
CHIP_KEYS = ("fiber", "potassium", "iron", "calcium", "vit_d", "magnesium", "zinc", "vit_c", "vit_a", "epa_dha")
LABELS = {k: lab for k, lab, *_ in DV_ROWS}
SHORT = {"vit_c": "Vitamin C", "vit_a": "Vitamin A", "vit_d": "Vitamin D", "epa_dha": "Omega-3", "fiber": "Fiber"}
LOWER = {"vit_c": "vitamin C", "vit_a": "vitamin A", "vit_d": "vitamin D", "epa_dha": "omega-3", "fiber": "fiber"}

# The order you'd walk the line when building a plate: base first, sauces and sides last.
SLOT_ORDER = ("base", "wrap", "oats", "pasta", "greens", "starch", "yogurt", "protein", "egg", "burger", "beans", "carb",
              "potato", "veg", "sauce", "cheese", "topping", "crunch", "dressing", "fruit", "side", "milk")


def portion(f: Food, s: int) -> str:
    if f.unit == "slice":
        return f"{s} slice" + ("s" if s > 1 else "")
    if f.role == "protein" and s > 1:
        return f"{s} portions"
    if f.unit in ("cup", "tbsp", "tsp", "oz", "floz", "g"):
        return f"{s} scoop" + ("s" if s > 1 else "")
    return f"{s} serving" + ("s" if s > 1 else "")


def label_totals(build: Build) -> dict:
    """Nutrition Facts totals: label numbers summed as printed, plus the estimated micronutrients."""
    out = {k: 0.0 for k, *_ in DV_ROWS}
    out["kcal"] = 0.0
    for _, f, s in build.picks:
        n = f.nutrition
        out["kcal"] += n.kcal * s
        for k in ("fat", "sat_fat", "trans_fat", "cholesterol", "sodium", "carbs", "fiber", "protein", "calcium",
                  "iron", "potassium"):
            out[k] += (getattr(n, k) or 0.0) * s
        out["vit_d"] += (n.vit_d or 0.0) * s
        out["sugars"] += max(n.sugars or 0.0, f.added_sugar) * s
        out["added_sugar"] += f.added_sugar * s
        for k in ("magnesium", "zinc", "vit_c", "vit_a", "epa_dha"):
            out[k] += f.est.get(k, 0.0) * s
    return out


def dv_percent(tot: dict) -> dict:
    return {k: round(100.0 * tot.get(k, 0.0) / C.DV[k]) for k, *_ in DV_ROWS if k in C.DV}


def nice_item(f: Food) -> str:
    s = re.sub("[" + chr(0x00AE) + chr(0x2122) + "]", "", f.name)
    return " ".join(s.split())


def badges(f: Food) -> list:
    out = []
    if "halal" in f.props:
        out.append("H")
    if "made_without_gluten" in f.props:
        out.append("GF")
    return out


def steps(build: Build) -> list:
    order = {k: i for i, k in enumerate(SLOT_ORDER)}
    picks = sorted(build.picks, key=lambda p: order.get(p[0], 99))
    groups: list = []
    for _, f, s in picks:
        grp = next((g for g in groups if g["station"] == f.station), None)
        if grp is None:
            grp = {"station": f.station, "items": []}
            groups.append(grp)
        grp["items"].append({"rid": f.rid, "name": nice_item(f), "servings": s, "portion": portion(f, s),
                             "serving": f.serving.lower(), "tags": badges(f)})
    return groups


def _j(names: list) -> str:
    names = [n for n in names if n]
    if len(names) <= 1:
        return names[0] if names else ""
    return ", ".join(names[:-1]) + " and " + names[-1]


def _who(build: Build, pred) -> str:
    return _j([nice(f) for _, f, _ in build.picks if pred(f)][:2])


def highlights(build: Build, tot: dict, parts: dict) -> list:
    out = [f"{tot['protein']:.0f} g protein"]
    pct = dv_percent(tot)
    tops = sorted(((pct[k], k) for k in CHIP_KEYS if k in pct), reverse=True)
    best = [(p, k) for p, k in tops if p >= 25][:2]
    if best:
        out.append(_j([f"{p}% of your daily {LOWER.get(k, LABELS[k].lower())}" for p, k in best]))
    whole = 1.0 - parts["upf_share"]
    if whole >= 0.85:
        out.append(f"{100 * whole:.0f}% minimally processed")
    fruit = [nice(f) for _, f, _ in build.picks if f.kind == "fruit"]
    if fruit:
        out.append(f"Fruit: {_j(fruit)}")
    return out


def tradeoffs(build: Build, tot: dict, parts: dict, target: C.MealTarget) -> list:
    pens = parts["penalties"]
    out: list = []
    if tot["protein"] < 0.9 * target.protein:
        out.append((9, f"Protein runs a little light ({tot['protein']:.0f} g); grab a second scoop of the protein"))
    if tot["kcal"] > target.kcal_hi * 1.05:
        out.append((4, f"Big plate ({tot['kcal']:.0f} kcal); skip a side if you're not that hungry"))
    elif tot["kcal"] < target.kcal_lo * 0.95:
        out.append((4, f"On the lighter side ({tot['kcal']:.0f} kcal); add fruit or milk if you trained"))
    if pens["sodium"] > 0.3:
        out.append((pens["sodium"] + 2, f"Salty: {tot['sodium']:,.0f} mg sodium ({100 * tot['sodium'] / 2300:.0f}% of a day); drink water"))
    if pens["added_sugar"] > 0.1:
        who = _who(build, lambda f: f.added_sugar >= 3)
        out.append((pens["added_sugar"] + 2, f"{tot['added_sugar']:.0f} g added sugar" + (f", mostly from {who}" if who else "")))
    if pens["processed_meat"] > 0:
        out.append((pens["processed_meat"] + 1, f"Processed meat ({_who(build, lambda f: f.processed_meat_g > 0)})"))
    if parts["fried_share"] > 0.05:
        out.append((pens["fried"] + 1, f"{_who(build, lambda f: f.fried)} is fried"))
    if pens["sat_fat"] > 0.5:
        out.append((pens["sat_fat"], f"{tot['sat_fat']:.0f} g saturated fat"))
    dyed = [(f, d) for _, f, _ in build.picks for d in f.dyes]
    if dyed:
        out.append((pens["dyes"] + 0.5, "Dyes: " + "; ".join(f"{d} in {nice(f)}" for f, d in dyed[:3]) + " (small deduction)"))
    reds = [(f, r) for _, f, _ in build.picks for r in f.red_flags]
    if reds:
        out.append((pens["red_flag_additives"] + 0.6, "; ".join(f"{r} in {nice(f)}" for f, r in reds[:2]) + " (restricted in the EU or California)"))
    emul = [(f, e) for _, f, _ in build.picks for e, _ in f.emulsifiers]
    if emul:
        out.append((pens["emulsifiers"], "Emulsifiers: " + "; ".join(f"{e} in {nice(f)}" for f, e in emul[:2]) + " (minor)"))
    if parts["upf_share"] >= 0.35:
        out.append((2, f"{100 * parts['upf_share']:.0f}% of the calories are ultra-processed ({_who(build, lambda f: f.upf >= 0.6)})"))
    out.sort(key=lambda x: -x[0])
    return [t for _, t in out[:3]]


def chips(tot: dict) -> list:
    pct = dv_percent(tot)
    rows = sorted(((pct[k], k) for k in CHIP_KEYS if k in pct), reverse=True)
    return [{"key": k, "label": SHORT.get(k, LABELS[k]), "pct": p, "est": k in C.ESTIMATED} for p, k in rows[:6]]


def build_payload(build: Build, rank: int, target: C.MealTarget) -> dict:
    sc, parts = score_meal(build.vec, target, build.bonus, explain=True)
    tot = label_totals(build)
    return {
        "rank": rank,
        "key": build.template.key,
        "name": build.name,
        "blurb": build.template.blurb,
        "score": int(round(min(100.0, sc))),
        "sub": {"macros": round(parts["macros"], 1), "micros": round(parts["micros"], 1), "clean": round(parts["clean"], 1)},
        "totals": {k: round(v, 1) for k, v in tot.items()},
        "dv": dv_percent(tot),
        "chips": chips(tot),
        "steps": steps(build),
        "how": build.template.how(build.by_slot()),
        "why": highlights(build, tot, parts),
        "tradeoffs": tradeoffs(build, tot, parts, target),
    }


def processing_label(f: Food) -> str:
    if f.upf < 0.15:
        return "Minimally processed"
    if f.upf < 0.5:
        return "Processed"
    return "Ultra-processed"


def item_payload(f: Food, ingredients: str) -> dict:
    n = f.nutrition
    label = {k: getattr(n, k) for k in ("kcal", "fat", "sat_fat", "trans_fat", "cholesterol", "sodium", "carbs", "fiber",
                                         "sugars", "protein", "calcium", "iron", "potassium")}
    label["vit_d"] = n.vit_d
    label["added_sugar"] = n.added_sugar
    notes = []
    if f.dyes:
        notes.append("Dyes: " + ", ".join(f.dyes))
    if f.red_flags:
        notes.append("Restricted additives: " + ", ".join(f.red_flags))
    if f.emulsifiers:
        notes.append("Emulsifiers: " + ", ".join(e for e, _ in f.emulsifiers))
    if f.sweeteners:
        notes.append("Sweeteners: " + ", ".join(f.sweeteners))
    if f.processed_meat_g:
        notes.append("Processed meat")
    if f.fried:
        notes.append("Fried")
    if f.added_sugar_estimated and f.added_sugar:
        notes.append("Added sugar estimated from the ingredients")
    notes += [f"Label corrected: {x}" for x in f.fixes]
    return {
        "name": nice_item(f), "station": f.station, "serving": f.serving, "label": label,
        "est": {k: round(v, 1) for k, v in f.est.items()},
        "allergens": [a.replace("_", " ").title() for a in f.allergens],
        "badges": badges(f), "processing": processing_label(f), "notes": notes,
        "ingredients": (ingredients[:700] + ("..." if len(ingredients) > 700 else "")) if ingredients else "",
    }
