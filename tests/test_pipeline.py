import json
import os
from datetime import date

from conftest import make_getter

from heelfuel import build
from heelfuel.plan import daily_plans


def _run(tmp_path, pages):
    out = tmp_path / "site"
    payload = build.run(str(out), str(tmp_path / "recipes.json"), days=1, today=date(2026, 9, 28),
                        getter=make_getter(pages))
    return payload, out


def test_end_to_end_build(tmp_path):
    payload, out = _run(tmp_path, {"chase": "menu_small.html", "top-of-lenoir": "page_not_found.html"})
    day = payload["days"][0]
    halls = {h["key"]: h for h in day["halls"]}
    assert halls["chase"]["status"] == "ok"
    assert halls["lenoir"]["status"] == "no_menu"
    lunch = next(p for p in halls["chase"]["periods"] if p["label"] == "Lunch")
    top = lunch["combos"][0]
    assert top["rank"] == 1 and 0 < top["score"] <= 100
    assert top["title"] and top["idea"] and top["pros"]
    assert {m["key"] for m in top["micros"]} >= {"potassium", "iron", "magnesium", "epa_dha"}

    html = (out / "index.html").read_text(encoding="utf-8")
    assert "window.HEELFUEL = {" in html
    assert "/*__HEELFUEL_DATA__*/" not in html
    assert chr(0x2014) not in html and chr(0x2013) not in html
    assert json.loads((out / "data" / "latest.json").read_text())["days"][0]["date"] == "2026-09-28"
    assert (out / "favicon.svg").exists()

    names = {x["name"] for x in day["excluded"]}
    assert "Swiss Cheese" in names  # listed on the page instead of silently dropped


def test_daily_plan_totals(tmp_path):
    payload, _ = _run(tmp_path, {"chase": "menu_small.html", "top-of-lenoir": "page_not_found.html"})
    plan = payload["days"][0]["plan"]
    best = plan["best"]
    assert [p["slot"] for p in best["picks"]] == ["breakfast", "lunch", "late_night"]
    assert abs(best["totals"]["protein"] - sum(p["protein"] for p in best["picks"])) <= 2
    assert plan["lenoir"]["picks"] == []
    assert plan["chase"]["picks"] == best["picks"]
    assert best["bars"][0]["key"] == "protein"


def test_recipe_cache_is_reused(tmp_path):
    calls = []
    base = make_getter({"chase": "menu_small.html", "top-of-lenoir": "page_not_found.html"})

    def counting(url):
        calls.append(url)
        return base(url)

    cache = str(tmp_path / "recipes.json")
    build.run(str(tmp_path / "a"), cache, days=1, today=date(2026, 9, 28), getter=counting)
    first = sum("recipe.php" in u for u in calls)
    calls.clear()
    build.run(str(tmp_path / "b"), cache, days=1, today=date(2026, 9, 29), getter=counting)
    assert first > 20
    assert sum("recipe.php" in u for u in calls) == 0


def test_every_fetch_failing_does_not_publish(tmp_path, monkeypatch):
    monkeypatch.setattr(build, "http_get", make_getter({"chase": None, "top-of-lenoir": None}))
    code = build.main(["--out", str(tmp_path / "site"), "--cache", str(tmp_path / "r.json"),
                       "--days", "1", "--date", "2026-09-28"])
    assert code == 1


def test_one_hall_down_still_publishes(tmp_path, monkeypatch):
    monkeypatch.setattr(build, "http_get", make_getter({"chase": "menu_small.html", "top-of-lenoir": None}))
    code = build.main(["--out", str(tmp_path / "site"), "--cache", str(tmp_path / "r.json"),
                       "--days", "1", "--date", "2026-09-28"])
    assert code == 0
    data = json.loads((tmp_path / "site" / "data" / "latest.json").read_text())
    lenoir = next(h for h in data["days"][0]["halls"] if h["key"] == "lenoir")
    assert lenoir["status"] == "error" and "dining.unc.edu" in lenoir["message"]


def test_plan_prefers_variety():
    from types import SimpleNamespace as NS

    def combo(name, score):
        f = NS(name=name, role="protein", kind="protein", nutrition=NS(protein=40), rid=name, tags=frozenset())
        return NS(items=((f, 1),), vec=tuple([700, 40] + [0] * 40), score=score)

    periods = [
        {"hall": "chase", "key": "lunch", "label": "Lunch", "slot": "lunch", "counts": True,
         "combos": [combo("Tofu", 99), combo("Chicken", 97)], "titles": ["Tofu plate", "Chicken plate"]},
        {"hall": "chase", "key": "dinner", "label": "Dinner", "slot": "dinner", "counts": True,
         "combos": [combo("Tofu", 99), combo("Salmon", 98)], "titles": ["Tofu plate", "Salmon plate"]},
    ]
    picks = daily_plans(periods)["best"]["picks"]
    assert [p["title"] for p in picks] == ["Tofu plate", "Salmon plate"]
