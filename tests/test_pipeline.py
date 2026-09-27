import json
from datetime import date

from conftest import make_getter

from heelfuel import build

PAGES = {"chase": "menu_small.html", "top-of-lenoir": "page_not_found.html"}


def _run(tmp_path, pages=PAGES):
    out = tmp_path / "site"
    payload = build.run(str(out), str(tmp_path / "recipes.json"), days=1, today=date(2026, 9, 28),
                        getter=make_getter(pages))
    return payload, out


def test_end_to_end_build(tmp_path):
    payload, out = _run(tmp_path)
    day = payload["days"][0]
    halls = {h["key"]: h for h in day["halls"]}
    assert halls["chase"]["status"] == "ok"
    assert halls["lenoir"]["status"] == "no_menu"
    assert halls["chase"]["menu_url"].endswith("/locations/chase/?date=2026-09-28")

    lunch = next(p for p in halls["chase"]["periods"] if p["label"] == "Lunch")
    assert lunch["status"] == "ok" and lunch["target"]["kind"] == "main"
    top = lunch["builds"][0]
    assert top["rank"] == 1 and 0 < top["score"] <= 100
    assert set(top["sub"]) == {"macros", "micros", "clean"}
    assert top["name"] and top["how"] and top["why"] and top["steps"]
    assert top["totals"]["protein"] >= 42
    assert top["dv"]["protein"] == round(100 * top["totals"]["protein"] / 50)
    assert len(top["chips"]) == 6 and {c["key"] for c in top["chips"]} <= set(payload["dv"])

    # Every item a build points at has a label for the nutrition panel.
    for p in halls["chase"]["periods"]:
        for b in p["builds"]:
            for g in b["steps"]:
                for it in g["items"]:
                    assert it["rid"] in payload["items"]
    shawarma = next(v for v in payload["items"].values() if v["name"] == "Chicken Shawarma")
    assert shawarma["label"]["protein"] > 0 and shawarma["ingredients"]

    html = (out / "index.html").read_text(encoding="utf-8")
    assert "window.HEELFUEL = {" in html
    assert "/*__HEELFUEL_DATA__*/" not in html
    assert chr(0x2014) not in html and chr(0x2013) not in html
    assert json.loads((out / "data" / "latest.json").read_text())["days"][0]["date"] == "2026-09-28"
    assert (out / "favicon.svg").exists()

    names = {x["name"] for x in day["excluded"]}
    assert "Swiss Cheese" in names  # listed on the page instead of silently dropped


def test_no_daily_totals_anywhere(tmp_path):
    payload, _ = _run(tmp_path)
    assert "plan" not in payload["days"][0]
    assert set(payload["targets"]) == {"breakfast", "main", "late"}


def test_recipe_cache_is_reused(tmp_path):
    calls = []
    base = make_getter(PAGES)

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
