"""Daily pipeline: fetch menus, find the best meal builds for every period, write the static site.

    python -m heelfuel.build --out site --cache .cache/recipes.json
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import date as Date, datetime, timedelta
from typing import Callable, Optional
from zoneinfo import ZoneInfo

from . import config as C
from .builds import best_builds, nice
from .classify import analyze
from .explain import build_payload, item_payload
from .fetch import RecipeCache, fetch_hall_menu, http_get
from .model import HallMenu
from .render import render_site
from .score import target_for

log = logging.getLogger("heelfuel")


def _target_payload(t: C.MealTarget) -> dict:
    return {"kind": t.kind, "kcal_lo": t.kcal_lo, "kcal_hi": t.kcal_hi, "protein": t.protein}


def process_day(day: str, menus: dict, cache: RecipeCache, items: dict) -> dict:
    """One day's payload. Every item a build uses is added to `items` (shared across days)."""
    halls_out, excluded = [], {}
    for hall, info in C.HALLS.items():
        m: HallMenu = menus[hall]
        hall_out = {"key": hall, "name": info["name"], "building": info["building"], "status": m.status,
                    "message": m.message, "menu_url": C.MENU_URL.format(slug=info["slug"], date=day), "periods": []}
        for p in m.periods:
            target = target_for(p.slot)
            foods, missing = [], 0
            for it in p.items:
                r = cache.recipes.get(it.recipe_id)
                if r is None:
                    missing += 1
                    continue
                f = analyze(it, r)
                foods.append(f)
                if f.suspect and f.role != "excluded":
                    excluded.setdefault(nice(f), {"name": nice(f), "station": f.station, "hall": info["name"],
                                                  "reason": f.suspect})
            t0 = time.time()
            builds = best_builds(foods, p.slot, p.label) if foods else []
            log.info("%s %s %s: %d items, %d builds in %.2fs", day, hall, p.label, len(foods), len(builds), time.time() - t0)
            for b in builds:
                for _, f, _ in b.picks:
                    if f.rid not in items:
                        r = cache.recipes.get(f.rid)
                        items[f.rid] = item_payload(f, r.ingredients if r else "")
            hall_out["periods"].append({
                "key": p.key, "label": p.label, "hours": p.hours, "slot": p.slot,
                "target": _target_payload(target),
                "on_menu": len(p.items), "missing_recipes": missing,
                "status": "ok" if builds else "no_options",
                "builds": [build_payload(b, i + 1, target) for i, b in enumerate(builds)],
            })
        halls_out.append(hall_out)
    d = Date.fromisoformat(day)
    return {
        "date": day,
        "weekday": d.strftime("%A"),
        "label": d.strftime("%a, %b ") + str(d.day),
        "halls": halls_out,
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

    items: dict = {}
    out_days = [process_day(day, menus[day], cache, items) for day in dates]
    payload = {
        "generated_at": now.isoformat(timespec="minutes"),
        "generated_label": now.strftime("%a %b ") + str(now.day) + now.strftime(", %I:%M %p").replace(" 0", " ") + " ET",
        "timezone": C.TIMEZONE,
        "targets": {k: _target_payload(t) for k, t in C.MEAL_TARGETS.items()},
        "dv": C.DV,
        "estimated": sorted(C.ESTIMATED),
        "days": out_days,
        "items": items,
        "recipe_failures": len(failures),
        "links": {
            "repo": C.REPO_URL,
            "research": C.REPO_URL + "/blob/main/RESEARCH.md",
            "source": "https://dining.unc.edu/menu-hours/",
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

    for day in payload["days"]:
        for hall in day["halls"]:
            n = sum(len(p["builds"]) for p in hall["periods"])
            log.info("%s %-14s %-8s %d periods, %d builds %s", day["date"], hall["name"], hall["status"],
                     len(hall["periods"]), n, hall["message"])
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
