"""Daily pipeline: fetch menus, score meals, write the static site.

    python -m heelfuel.build --out site --cache .cache/recipes.json
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import date as Date, datetime, timedelta
from typing import Callable, Optional
from zoneinfo import ZoneInfo

from . import config as C
from .classify import analyze
from .explain import compare_to, micros, pros_cons, short_name, tasty_idea, title_for
from .fetch import RecipeCache, fetch_hall_menu, http_get
from .formats import meal_format
from .model import HallMenu
from .optimize import search
from .plan import daily_plans
from .render import render_site
from .score import IX, slot_targets

log = logging.getLogger("heelfuel")


def _item_payload(f, servings: int) -> dict:
    n = f.nutrition
    flags = []
    if f.fried:
        flags.append("fried")
    if f.processed_meat_g:
        flags.append("processed meat")
    flags += list(f.dyes) + list(f.red_flags)
    return {
        "name": short_name(f.name), "station": f.station, "servings": servings, "serving": f.serving.lower(),
        "kcal": round(n.kcal * servings), "protein": round(n.protein * servings),
        "carbs": round(n.carbs * servings), "fat": round(n.fat * servings), "role": f.role, "flags": flags,
    }


def _combo_payload(combo, rank: int, target, slot: str, condiments, best=None, period: str = "") -> dict:
    v = combo.vec
    pros, cons = pros_cons(combo, target, slot, period)
    return {
        "rank": rank,
        "score": round(min(100.0, combo.score)),
        "title": title_for(combo, slot),
        "format": meal_format(combo.items, slot) or "plate",
        "items": [_item_payload(f, s) for f, s in combo.items],
        "totals": {k: round(v[IX[k]], 1) for k in ("kcal", "protein", "carbs", "fat", "fiber", "sodium", "sat_fat", "added_sugar", "sugars")},
        "micros": micros(v),
        "pros": pros,
        "cons": cons,
        "idea": tasty_idea(combo, slot, condiments),
        "compare": compare_to(best, combo) if best is not None and rank > 1 else "",
        "stations": sorted({f.station for f, _ in combo.items}),
    }


def process_day(day: str, menus: dict, cache: RecipeCache) -> dict:
    present = {p.slot for m in menus.values() if m.status == "ok" for p in m.periods if p.counts}
    targets = slot_targets(present)
    halls_out, plan_periods, excluded = [], [], {}
    for hall, info in C.HALLS.items():
        m: HallMenu = menus[hall]
        hall_out = {"key": hall, "name": info["name"], "status": m.status, "message": m.message, "periods": []}
        for p in m.periods:
            t = targets[p.slot]
            foods, missing = [], 0
            for it in p.items:
                r = cache.recipes.get(it.recipe_id)
                if r is None:
                    missing += 1
                    continue
                f = analyze(it, r)
                foods.append(f)
                if f.suspect and f.role != "excluded":
                    excluded.setdefault(short_name(f.name), {"name": short_name(f.name), "station": f.station,
                                                             "hall": info["name"], "reason": f.suspect})
            condiments = [f for f in foods if f.kind == "condiment" or f.kind == "sauce"]
            t0 = time.time()
            combos = search(foods, t) if foods else []
            log.info("%s %s %s: %d items, %d combos in %.1fs", day, hall, p.label, len(foods), len(combos), time.time() - t0)
            period_out = {
                "key": p.key, "label": p.label, "hours": p.hours, "slot": p.slot, "counts": p.counts,
                "target": {"kcal": round(t.kcal), "protein": round(t.protein), "carbs": round(t.carbs), "fat": round(t.fat)},
                "missing_recipes": missing,
                "status": "ok" if combos else "no_options",
                "combos": [_combo_payload(c, i + 1, t, p.slot, condiments, combos[0], p.label) for i, c in enumerate(combos)],
            }
            hall_out["periods"].append(period_out)
            plan_periods.append({"hall": hall, "key": p.key, "label": p.label, "slot": p.slot, "counts": p.counts,
                                 "combos": combos, "titles": [c["title"] for c in period_out["combos"]]})
        halls_out.append(hall_out)
    d = Date.fromisoformat(day)
    return {
        "date": day,
        "weekday": d.strftime("%A"),
        "label": d.strftime("%a, %b ") + str(d.day),
        "halls": halls_out,
        "plan": daily_plans(plan_periods),
        "slot_targets": {s: {"kcal": round(t.kcal), "protein": round(t.protein)} for s, t in targets.items() if s in present},
        "excluded": sorted(excluded.values(), key=lambda x: x["name"]),
    }


def run(out_dir: str, cache_path: Optional[str], days: int = 2, today: Optional[Date] = None,
        getter: Optional[Callable[[str], str]] = None) -> dict:
    getter = getter or http_get
    tz = ZoneInfo(C.TIMEZONE)
    now = datetime.now(tz)
    today = today or now.date()
    dates = [(today + timedelta(days=i)).isoformat() for i in range(days)]
    cache = RecipeCache(cache_path)

    menus = {day: {hall: fetch_hall_menu(hall, day, getter) for hall in C.HALLS} for day in dates}
    ids = {it.recipe_id for day in menus.values() for m in day.values() for p in m.periods for it in p.items}
    failures = cache.ensure(ids, today, getter)
    cache.save()

    out_days = [process_day(day, menus[day], cache) for day in dates]
    payload = {
        "generated_at": now.isoformat(timespec="minutes"),
        "generated_label": now.strftime("%a %b ") + str(now.day) + now.strftime(", %I:%M %p").replace(" 0", " ") + " ET",
        "timezone": C.TIMEZONE,
        "targets": {
            "kcal": C.DAILY.kcal, "kcal_lo": C.DAILY.kcal_lo, "kcal_hi": C.DAILY.kcal_hi,
            "protein": C.DAILY.protein, "carbs": C.DAILY.carbs, "fat": C.DAILY.fat, "fiber": C.DAILY.fiber,
        },
        "days": out_days,
        "recipe_failures": len(failures),
        "links": {
            "repo": C.REPO_URL,
            "research": C.REPO_URL + "/blob/main/RESEARCH.md",
            "source": "https://dining.unc.edu/menu-hours/",
            "halls": {k: C.MENU_URL.format(slug=v["slug"], date=today.isoformat()) for k, v in C.HALLS.items()},
        },
    }
    render_site(payload, out_dir)
    return payload


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description="Build the HeelFuel site for today and tomorrow.")
    ap.add_argument("--out", default="site")
    ap.add_argument("--cache", default=".cache/recipes.json")
    ap.add_argument("--days", type=int, default=2)
    ap.add_argument("--date", help="Build as if today were YYYY-MM-DD (Eastern)")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    today = Date.fromisoformat(args.date) if args.date else None
    payload = run(args.out, args.cache, args.days, today)

    ok = 0
    for day in payload["days"]:
        for hall in day["halls"]:
            n = sum(len(p["combos"]) for p in hall["periods"])
            log.info("%s %-14s %-8s %d periods, %d picks %s", day["date"], hall["name"], hall["status"],
                     len(hall["periods"]), n, hall["message"])
            ok += hall["status"] == "ok"
    if payload["recipe_failures"]:
        log.warning("%d recipe labels could not be fetched", payload["recipe_failures"])
    # Every hall failing to load means dining.unc.edu is down or blocking us: fail so the last good
    # deploy stays up instead of being replaced by an empty page.
    errors = sum(h["status"] == "error" for d in payload["days"] for h in d["halls"])
    if errors == sum(len(d["halls"]) for d in payload["days"]):
        log.error("every menu fetch failed; not publishing")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
