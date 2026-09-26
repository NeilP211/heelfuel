"""Meal scoring (RESEARCH.md section 3).

A meal is scored from one summed vector: the per-serving `Food.vec` fields times servings, plus
additive "points" that don't scale linearly with servings. Keeping everything in one flat tuple lets
the optimizer add candidate items with a single zip instead of re-walking the whole meal.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional

from . import config as C
from .classify import V_FIELDS, Food

# Extra fields appended after V_FIELDS: additive penalty points (already dose-scaled by servings),
# plus a partially-hydrogenated-oil count.
ADD_FIELDS = ("dye_pts", "red_pts", "emul_pts", "sweet_pts", "phos_pts", "caramel_pts", "pho")
FIELDS = V_FIELDS + ADD_FIELDS
IX = {k: i for i, k in enumerate(FIELDS)}
_N = len(FIELDS)
ZERO = (0.0,) * _N

LABEL_MICROS = (("potassium", 0.35), ("calcium", 0.25), ("iron", 0.2), ("vit_d", 0.2))
EST_MICROS = (("magnesium", 0.3), ("zinc", 0.2), ("vit_c", 0.2), ("vit_a", 0.15), ("epa_dha", 0.15))


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


@dataclass(frozen=True)
class SlotTarget:
    slot: str
    share: float          # share of the day's calories
    kcal: float
    protein: float
    carbs: float
    fat: float
    fiber: float
    produce_cups: float
    sodium_allowance: float
    added_sugar_allowance: float
    micros: dict = field(default_factory=dict, hash=False, compare=False)

    @property
    def kcal_lo(self) -> float:
        return self.kcal * (1 - C.KCAL_BAND)

    @property
    def kcal_hi(self) -> float:
        return self.kcal * (1 + C.KCAL_BAND)


def slot_targets(present: Iterable[str]) -> dict[str, SlotTarget]:
    """Per-meal targets. Shares are renormalized over the main slots that exist that day."""
    present = set(present)
    main = [s for s in C.MAIN_SLOTS if s in present] or list(C.MAIN_SLOTS)
    k_total = sum(C.SLOT_SHARES[s][0] for s in main)
    p_total = sum(C.SLOT_SHARES[s][1] for s in main)
    d = C.DAILY
    out = {}
    for s in C.MAIN_SLOTS:
        ks = C.SLOT_SHARES[s][0] / (k_total if s in main else 1.0)
        ps = C.SLOT_SHARES[s][1] / (p_total if s in main else 1.0)
        out[s] = SlotTarget(
            slot=s, share=ks, kcal=d.kcal * ks, protein=d.protein * ps, carbs=d.carbs * ks, fat=d.fat * ks,
            fiber=d.fiber * ks, produce_cups=d.produce_cups * ks, sodium_allowance=d.sodium_allowance * ks,
            added_sugar_allowance=d.added_sugar_per_meal,
            micros={k: v * ks for k, v in C.DV.items()},
        )
    return out


def _g(grade: str) -> float:
    return C.GRADE[grade]


def score_vec(v: tuple, t: SlotTarget, realism: float = 0.0, explain: bool = False):
    """Score a summed meal vector against a slot target. Returns score, or (score, parts) if explain."""
    kcal = v[0]
    protein = v[1]
    carbs = v[2]
    fat = v[3]
    parts: Optional[dict] = {} if explain else None

    # ---- FIT: your targets (not evidence-discounted)
    r = protein / t.protein if t.protein else 1.0
    p_pts = C.FIT_POINTS["protein"] * min(1.0, r / 0.95) ** 1.6
    if r > C.PROTEIN_SOFT_CAP:
        # Past the soft cap extra protein is crowding out the carbs that fuel training.
        p_pts -= min(6.0, (r - C.PROTEIN_SOFT_CAP) * C.PROTEIN_OVER_PTS)
    if kcal < t.kcal_lo:
        d = (t.kcal_lo - kcal) / t.kcal
    elif kcal > t.kcal_hi:
        d = (kcal - t.kcal_hi) / t.kcal
    else:
        d = 0.0
    k_pts = C.FIT_POINTS["kcal"] * max(0.0, 1.0 - d / C.KCAL_TAPER)
    rc = carbs / t.carbs if t.carbs else 1.0
    if rc < C.CARB_BAND[0]:
        c_pts = C.FIT_POINTS["carbs"] * (rc / C.CARB_BAND[0]) ** 1.3
    elif rc > C.CARB_BAND[1]:
        c_pts = C.FIT_POINTS["carbs"] * max(0.0, 1.0 - (rc - C.CARB_BAND[1]) / 0.9)
    else:
        c_pts = C.FIT_POINTS["carbs"]
    rf = fat / t.fat if t.fat else 1.0
    if rf < 0.6:
        f_pts = C.FIT_POINTS["fat"] * rf / 0.6
    elif rf > 1.4:
        f_pts = C.FIT_POINTS["fat"] * max(0.0, 1.0 - (rf - 1.4) / 1.0)
    else:
        f_pts = C.FIT_POINTS["fat"]

    # ---- QUALITY (evidence-weighted)
    Q = C.QUALITY
    fiber_pts = Q["fiber"][0] * _g(Q["fiber"][1]) * min(1.0, v[IX["fiber"]] / t.fiber)
    produce_pts = Q["produce"][0] * _g(Q["produce"][1]) * min(1.0, v[IX["produce_cups"]] / t.produce_cups)
    upf_share = v[IX["upf_kcal"]] / kcal if kcal > 0 else 0.0
    whole_pts = Q["whole_food"][0] * _g(Q["whole_food"][1]) * max(0.0, 1.0 - upf_share)
    m = t.micros
    label = sum(w * min(1.0, v[IX[k]] / m[k]) for k, w in LABEL_MICROS if m.get(k))
    label_pts = Q["label_micros"][0] * _g(Q["label_micros"][1]) * label
    est = sum(w * min(1.0, v[IX[k]] / m[k]) for k, w in EST_MICROS if m.get(k))
    est_pts = Q["est_micros"][0] * _g(Q["est_micros"][1]) * est
    pq = v[IX["pq_protein"]] / protein if protein > 0 else 0.0
    pq_pts = Q["protein_quality"][0] * _g(Q["protein_quality"][1]) * min(1.0, pq / 0.9)
    cq = v[IX["quality_carbs"]] / carbs if carbs >= 5 else 0.5
    cq_pts = Q["carb_quality"][0] * _g(Q["carb_quality"][1]) * min(1.0, cq)

    # ---- BONUSES
    B = C.BONUS
    epa = v[IX["epa_dha"]]
    fish_pts = B["oily_fish"][0] * _g(B["oily_fish"][1]) * min(1.0, max(0.0, epa - 200.0) / (C.OMEGA3_FULL_MG - 200.0))
    sleep_pts = 0.0
    if t.slot == "late_night" and v[IX["slow_protein"]] >= 10:
        sleep_pts = B["presleep_protein"][0] * _g(B["presleep_protein"][1])

    # ---- PENALTIES (dose-scaled, capped, evidence-weighted)
    P = C.PENALTY

    def pen(key: str, raw: float) -> float:
        grade, cap = P[key]
        return min(cap, max(0.0, raw)) * _g(grade)

    sugar_pen = pen("added_sugar", (v[IX["added_sugar"]] - t.added_sugar_allowance) * C.ADDED_SUGAR_PTS_PER_G)
    sodium = v[IX["sodium"]]
    sodium_pen = pen("sodium", (sodium - t.sodium_allowance - C.SODIUM_GRACE_MG) / 200.0 * C.SODIUM_PTS_PER_200MG)
    sat_pen = pen("sat_fat", (v[IX["sat_fat"]] - C.DAILY.satfat_pct * kcal / 9.0) * C.SAT_FAT_PTS_PER_G)
    trans_pen = pen("trans_fat", v[IX["trans_fat"]] * C.TRANS_PTS_PER_G + (C.PHO_PTS if v[IX["pho"]] > 0 else 0.0))
    pm_pen = pen("processed_meat", v[IX["processed_meat_g"]] / 50.0 * C.PROCESSED_MEAT_PTS_PER_50G)
    fried_share = v[IX["fried_kcal"]] / kcal if kcal > 0 else 0.0
    fried_pen = pen("fried", fried_share * C.FRIED_PTS)
    dye_pen = pen("dyes", v[IX["dye_pts"]])
    red_pen = pen("red_flag_additives", v[IX["red_pts"]])
    emul_pen = pen("emulsifiers", v[IX["emul_pts"]])
    sweet_pen = pen("sweeteners", v[IX["sweet_pts"]])
    seed_share = v[IX["seed_oil_kcal"]] / kcal if kcal > 0 else 0.0
    seed_pen = pen("seed_oils", seed_share * C.SEED_OIL_PTS)
    refined = max(0.0, carbs - v[IX["quality_carbs"]])
    free_refined = C.REFINED_CARB_FREE_G * (t.kcal / (C.DAILY.kcal * 0.33))
    gl_pen = pen("glycemic_load", (refined - free_refined) / 15.0 * C.REFINED_CARB_PTS_PER_15G)
    dairy_pen = pen("dairy_acne", v[IX["dairy_cups"]] * C.DAIRY_PTS_PER_CUP)
    phos_pen = pen("phosphates", v[IX["phos_pts"]])
    caramel_pen = pen("cosmetic_color", v[IX["caramel_pts"]])
    bloat_pen = pen("bloat", (sodium - C.BLOAT_SODIUM_MG) / 300.0 * C.BLOAT_PTS_PER_300MG)
    station_pen = realism

    raw = (p_pts + k_pts + c_pts + f_pts
           + fiber_pts + produce_pts + whole_pts + label_pts + est_pts + pq_pts + cq_pts
           + fish_pts + sleep_pts
           - sugar_pen - sodium_pen - sat_pen - trans_pen - pm_pen - fried_pen - dye_pen - red_pen
           - emul_pen - sweet_pen - seed_pen - gl_pen - dairy_pen - phos_pen - caramel_pen - bloat_pen
           - station_pen)
    score = max(0.0, 100.0 * raw / C.SCORE_SCALE)
    if not explain:
        return score
    parts.update({
        "protein": p_pts, "kcal": k_pts, "carbs": c_pts, "fat": f_pts,
        "fiber": fiber_pts, "produce": produce_pts, "whole_food": whole_pts, "label_micros": label_pts,
        "est_micros": est_pts, "protein_quality": pq_pts, "carb_quality": cq_pts,
        "oily_fish": fish_pts, "presleep_protein": sleep_pts,
        "added_sugar": -sugar_pen, "sodium": -sodium_pen, "sat_fat": -sat_pen, "trans_fat": -trans_pen,
        "processed_meat": -pm_pen, "fried": -fried_pen, "dyes": -dye_pen, "red_flag_additives": -red_pen,
        "emulsifiers": -emul_pen, "sweeteners": -sweet_pen, "seed_oils": -seed_pen, "glycemic_load": -gl_pen,
        "dairy_acne": -dairy_pen, "phosphates": -phos_pen, "cosmetic_color": -caramel_pen, "bloat": -bloat_pen,
        "realism": -station_pen,
        "_upf_share": upf_share, "_fried_share": fried_share, "_refined_carbs": refined, "_pq": pq, "_cq": cq,
    })
    return score, parts


def totals(v: tuple) -> dict:
    """Human-facing nutrient totals from a summed vector."""
    return {k: v[IX[k]] for k in V_FIELDS + ADD_FIELDS}
