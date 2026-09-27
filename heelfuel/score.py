"""Scoring one meal on its own (RESEARCH.md section 3).

score (0-100) = MACROS (35) + MICROS (35) + CLEAN (30)

A meal is scored from one summed vector: the per-serving `Food.vec` fields times servings, plus
additive "points" that don't scale linearly with servings. Keeping everything in one flat tuple lets
the build search add candidate items with a single zip.
"""

from __future__ import annotations

from typing import Iterable

from . import config as C
from .classify import V_FIELDS, Food

# Extra fields appended after V_FIELDS: additive penalty points (already dose-scaled by servings),
# plus a partially-hydrogenated-oil count.
ADD_FIELDS = ("dye_pts", "red_pts", "emul_pts", "sweet_pts", "phos_pts", "caramel_pts", "pho")
FIELDS = V_FIELDS + ADD_FIELDS
IX = {k: i for i, k in enumerate(FIELDS)}
ZERO = (0.0,) * len(FIELDS)


def dose_factor(servings: float) -> float:
    """Second and third servings of the same additive-bearing item count, but less than the first."""
    return 1.0 + 0.5 * max(0.0, servings - 1.0)


def item_vec(food: Food, servings: float) -> tuple:
    base = tuple(v * servings for v in food.vec)
    d = dose_factor(servings)
    extra = (
        len(food.dyes) * C.DYE_PTS * d,
        len(food.red_flags) * C.RED_FLAG_PTS * d,
        sum(p for _, p in food.emulsifiers) * d,
        len(food.sweeteners) * 2.0 * d,
        (C.PHOSPHATE_PTS * d) if food.phosphates else 0.0,
        (C.CARAMEL_PTS * d) if food.caramel else 0.0,
        1.0 if food.pho else 0.0,
    )
    return base + extra


def vec_add(a: tuple, b: tuple) -> tuple:
    return tuple(x + y for x, y in zip(a, b))


def vec_sum(parts: Iterable[tuple]) -> tuple:
    out = ZERO
    for p in parts:
        out = vec_add(out, p)
    return out


def target_for(slot: str) -> C.MealTarget:
    return C.MEAL_TARGETS[C.SLOT_KIND.get(slot, "main")]


def _g(grade: str) -> float:
    return C.GRADE[grade]


def _band(value: float, lo: float, hi: float, pts: float, low_curve: float = 1.2) -> float:
    if value < lo:
        return pts * max(0.0, value / lo) ** low_curve if lo else pts
    if value > hi:
        return pts * max(0.0, 1.0 - (value - hi) / hi)
    return pts


def penalties(v: tuple, t: C.MealTarget) -> dict:
    """Evidence-weighted, dose-scaled deductions (each already capped). Keys match RESEARCH.md."""
    kcal = v[0]
    P = C.PENALTY

    def pen(key: str, raw: float) -> float:
        grade, cap = P[key]
        return min(cap, max(0.0, raw)) * _g(grade)

    sodium = v[IX["sodium"]]
    refined = max(0.0, v[IX["carbs"]] - v[IX["quality_carbs"]])
    return {
        "added_sugar": pen("added_sugar", (v[IX["added_sugar"]] - C.ADDED_SUGAR_PER_MEAL) * C.ADDED_SUGAR_PTS_PER_G),
        "sodium": pen("sodium", (sodium - t.sodium_allowance - C.SODIUM_GRACE_MG) / 200.0 * C.SODIUM_PTS_PER_200MG),
        "sat_fat": pen("sat_fat", (v[IX["sat_fat"]] - C.SAT_FAT_PCT * kcal / 9.0) * C.SAT_FAT_PTS_PER_G),
        "trans_fat": pen("trans_fat", v[IX["trans_fat"]] * C.TRANS_PTS_PER_G + (C.PHO_PTS if v[IX["pho"]] > 0 else 0.0)),
        "processed_meat": pen("processed_meat", v[IX["processed_meat_g"]] / 50.0 * C.PROCESSED_MEAT_PTS_PER_50G),
        "fried": pen("fried", (v[IX["fried_kcal"]] / kcal if kcal > 0 else 0.0) * C.FRIED_PTS),
        "dyes": pen("dyes", v[IX["dye_pts"]]),
        "red_flag_additives": pen("red_flag_additives", v[IX["red_pts"]]),
        "emulsifiers": pen("emulsifiers", v[IX["emul_pts"]]),
        "sweeteners": pen("sweeteners", v[IX["sweet_pts"]]),
        "seed_oils": pen("seed_oils", (v[IX["seed_oil_kcal"]] / kcal if kcal > 0 else 0.0) * C.SEED_OIL_PTS),
        "glycemic_load": pen("glycemic_load", (refined - t.refined_carb_free) / 15.0 * C.REFINED_CARB_PTS_PER_15G),
        "dairy_acne": pen("dairy_acne", v[IX["dairy_cups"]] * C.DAIRY_PTS_PER_CUP),
        "phosphates": pen("phosphates", v[IX["phos_pts"]]),
        "cosmetic_color": pen("cosmetic_color", v[IX["caramel_pts"]]),
        "bloat": pen("bloat", (sodium - C.BLOAT_SODIUM_MG) / 300.0 * C.BLOAT_PTS_PER_300MG),
    }


def coverage(v: tuple, t: C.MealTarget) -> dict:
    """Share (0-1) of each nutrient's per-meal slice of the Daily Value that the meal covers."""
    return {k: min(1.0, v[IX[k]] / (C.DV[k] * t.dv_share)) for k in C.MICRO_WEIGHTS}


def score_meal(v: tuple, t: C.MealTarget, bonus: float = 0.0, explain: bool = False):
    kcal, protein, carbs, fat = v[0], v[1], v[2], v[3]

    # MACROS: protein first, then a sensible plate size.
    r = protein / t.protein if t.protein else 1.0
    p_pts = C.MACRO_POINTS["protein"] * min(1.0, r) ** 1.3
    if r > C.PROTEIN_SOFT_CAP:
        p_pts -= min(5.0, (r - C.PROTEIN_SOFT_CAP) * C.PROTEIN_OVER_PTS)
    if kcal < t.kcal_lo:
        d = (t.kcal_lo - kcal) / t.kcal_mid
    elif kcal > t.kcal_hi:
        d = (kcal - t.kcal_hi) / t.kcal_mid
    else:
        d = 0.0
    k_pts = C.MACRO_POINTS["kcal"] * max(0.0, 1.0 - d / C.KCAL_TAPER)
    c_pts = _band(carbs, t.carbs_lo, t.carbs_hi, C.MACRO_POINTS["carbs"])
    f_pts = _band(fat, t.fat_lo, t.fat_hi, C.MACRO_POINTS["fat"], low_curve=1.0)
    macros = p_pts + k_pts + c_pts + f_pts

    # MICROS: Daily Value coverage across ten nutrients, plus fruit and vegetables.
    cov = coverage(v, t)
    wsum = sum(C.MICRO_WEIGHTS.values())
    micro_dv = C.MICRO_DV_POINTS * sum(C.MICRO_WEIGHTS[k] * cov[k] for k in cov) / wsum
    produce = C.PRODUCE_POINTS * min(1.0, v[IX["produce_cups"]] / t.produce_cups)
    micros = micro_dv + produce

    # CLEAN: how much of the meal is minimally processed, minus evidence-weighted deductions.
    upf_share = v[IX["upf_kcal"]] / kcal if kcal > 0 else 0.0
    whole = C.WHOLE_FOOD_POINTS * max(0.0, 1.0 - upf_share)
    pens = penalties(v, t)
    clean = whole + max(0.0, C.CLEAN_BASE_POINTS - sum(pens.values()))

    total = macros + micros + clean + bonus
    if not explain:
        return total
    return total, {
        "macros": macros, "micros": micros, "clean": clean, "bonus": bonus,
        "protein": p_pts, "kcal": k_pts, "carbs": c_pts, "fat": f_pts,
        "micro_dv": micro_dv, "produce": produce, "whole_food": whole,
        "coverage": cov, "penalties": pens, "upf_share": upf_share,
        "fried_share": v[IX["fried_kcal"]] / kcal if kcal > 0 else 0.0,
    }


def totals(v: tuple) -> dict:
    return {k: v[IX[k]] for k in FIELDS}
