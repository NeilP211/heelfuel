"""The daily total: what the day adds up to if you follow the top pick at every meal."""

from __future__ import annotations

from typing import Optional

from . import config as C
from .formats import main_protein
from .score import IX, ZERO, vec_add

VARIANTS = {"best": None, **{k: [k] for k in C.HALLS}}
VARIANT_LABELS = {"best": "Best of both halls", **{k: f"{v['name']} only" for k, v in C.HALLS.items()}}


def _status(value: float, lo: float, hi: float) -> str:
    if value < lo:
        return "low"
    if value > hi:
        return "high"
    return "ok"


def _verdict(tot: dict, n_meals: int) -> list[str]:
    d = C.DAILY
    notes = []
    p, k = tot["protein"], tot["kcal"]
    if p >= d.protein * 0.95:
        notes.append(f"Protein on target: {p:.0f} g of {d.protein:.0f} g.")
    else:
        gap = d.protein - p
        notes.append(f"{gap:.0f} g protein short of {d.protein:.0f} g. A cup of Greek yogurt (17 g) or a second protein scoop at dinner closes it.")
    if k < d.kcal_lo:
        notes.append(f"{k:,.0f} kcal is under the {d.kcal_lo:,.0f} to {d.kcal_hi:,.0f} range; add a snack (fruit, milk, a bagel) to stay out of a deficit.")
    elif k > d.kcal_hi:
        notes.append(f"{k:,.0f} kcal is over the {d.kcal_lo:,.0f} to {d.kcal_hi:,.0f} range; that's a bulk, not a maingain.")
    else:
        notes.append(f"{k:,.0f} kcal sits inside the {d.kcal_lo:,.0f} to {d.kcal_hi:,.0f} maingain range.")
    if tot["fiber"] < d.fiber * 0.75:
        notes.append(f"Fiber is {tot['fiber']:.0f} g; aim for about {d.fiber:.0f} g with an extra fruit or beans.")
    if tot["sodium"] > d.sodium_allowance * 1.2:
        notes.append(f"Sodium totals {tot['sodium']:,.0f} mg; drink plenty of water, especially if you want to look lean tomorrow.")
    if n_meals < 3:
        notes.append("Fewer than three meals are posted, so this total covers only part of the day.")
    return notes


def daily_plans(periods: list[dict]) -> dict:
    """periods: [{hall, key, label, slot, counts, combos: [Combo], titles: [str]}] for one day."""
    slots_present = [s for s in C.MAIN_SLOTS if any(p["slot"] == s and p["counts"] and p["combos"] for p in periods)]
    out = {}
    for variant, halls in VARIANTS.items():
        picks = []
        used_mains: set = set()
        vec = ZERO
        for slot in slots_present:
            options = []
            for p in periods:
                if p["slot"] != slot or not p["counts"] or not p["combos"]:
                    continue
                if halls is not None and p["hall"] not in halls:
                    continue
                for rank, combo in enumerate(p["combos"][:2]):
                    options.append((combo.score - (0.0 if rank == 0 else 1.0), rank, p, combo))
            if not options:
                continue
            options.sort(key=lambda x: -x[0])
            choice = options[0]
            # Don't eat the same main dish twice in one day if a near-equal alternative exists.
            mp = main_protein(choice[3].items)
            if mp is not None and mp.name in used_mains:
                alt = next((o for o in options[1:] if (main_protein(o[3].items) or mp).name not in used_mains
                            and o[0] >= choice[0] - 5), None)
                if alt:
                    choice = alt
            _, rank, p, combo = choice
            mp = main_protein(combo.items)
            if mp is not None:
                used_mains.add(mp.name)
            vec = vec_add(vec, combo.vec)
            picks.append({
                "slot": slot, "slot_label": C.SLOT_LABELS[slot], "hall": p["hall"],
                "hall_name": C.HALLS[p["hall"]]["name"], "period": p["label"], "period_key": p["key"],
                "rank": rank + 1, "title": p["titles"][rank], "score": round(min(100.0, combo.score)),
                "kcal": round(combo.vec[0]), "protein": round(combo.vec[1]),
            })
        if not picks:
            out[variant] = {"label": VARIANT_LABELS[variant], "picks": [], "totals": None, "notes": ["No meals posted."]}
            continue
        tot = {k: vec[IX[k]] for k in ("kcal", "protein", "carbs", "fat", "fiber", "sodium", "added_sugar", "sat_fat",
                                        "potassium", "calcium", "iron", "vit_d", "magnesium", "zinc", "vit_c", "epa_dha")}
        d = C.DAILY
        bars = [
            {"key": "protein", "label": "Protein", "value": round(tot["protein"]), "unit": "g", "target": d.protein,
             "lo": d.protein * 0.95, "hi": d.protein * 1.4, "status": _status(tot["protein"], d.protein * 0.95, d.protein * 1.4)},
            {"key": "kcal", "label": "Calories", "value": round(tot["kcal"]), "unit": "kcal", "target": d.kcal,
             "lo": d.kcal_lo, "hi": d.kcal_hi, "status": _status(tot["kcal"], d.kcal_lo, d.kcal_hi)},
            {"key": "carbs", "label": "Carbs", "value": round(tot["carbs"]), "unit": "g", "target": d.carbs,
             "lo": d.carbs_lo, "hi": d.carbs_hi, "status": _status(tot["carbs"], d.carbs_lo, d.carbs_hi)},
            {"key": "fat", "label": "Fat", "value": round(tot["fat"]), "unit": "g", "target": d.fat,
             "lo": d.fat_lo, "hi": d.fat_hi, "status": _status(tot["fat"], d.fat_lo, d.fat_hi)},
            {"key": "fiber", "label": "Fiber", "value": round(tot["fiber"]), "unit": "g", "target": d.fiber,
             "lo": d.fiber * 0.75, "hi": d.fiber * 2.0, "status": _status(tot["fiber"], d.fiber * 0.75, d.fiber * 2.0)},
            {"key": "sodium", "label": "Sodium", "value": round(tot["sodium"]), "unit": "mg", "target": d.sodium_ref,
             "lo": 0, "hi": d.sodium_allowance, "status": _status(tot["sodium"], 0, d.sodium_allowance)},
        ]
        out[variant] = {"label": VARIANT_LABELS[variant], "picks": picks,
                        "totals": {k: round(v, 1) for k, v in tot.items()}, "bars": bars,
                        "notes": _verdict(tot, len(picks))}
    return out
