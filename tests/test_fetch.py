from datetime import date

from conftest import fixture_text

from heelfuel import config
from heelfuel.fetch import RecipeCache, fetch_hall_menu


def test_second_pass_recovers_dropped_recipes(monkeypatch, recipe_ids):
    monkeypatch.setattr(config, "RETRY_PASS_DELAY_S", 0)
    calls: dict = {}

    def flaky(url):
        rid = url.split("recipe=")[1].split("&")[0]
        calls[rid] = calls.get(rid, 0) + 1
        if calls[rid] == 1 and int(rid) % 2 == 0:
            raise RuntimeError("timed out")  # the server sheds load on the parallel pass
        return fixture_text(f"recipes/{rid}.json")

    cache = RecipeCache(None)
    failures = cache.ensure(recipe_ids.values(), date(2026, 9, 28), getter=flaky)
    assert failures == {}
    assert len(cache.recipes) == len(recipe_ids)


def test_cache_freshness_and_persistence(tmp_path, recipe_ids):
    path = str(tmp_path / "recipes.json")
    cache = RecipeCache(path)
    rid = recipe_ids["Tofu"]
    cache.ensure([rid], date(2026, 9, 1), getter=lambda url: fixture_text(f"recipes/{rid}.json"))
    cache.save()
    again = RecipeCache(path)
    assert again.is_fresh(rid, date(2026, 9, 10))
    assert not again.is_fresh(rid, date(2026, 9, 1 + config.RECIPE_CACHE_DAYS))
    assert not again.is_fresh("missing", date(2026, 9, 10))


def test_unreadable_cache_starts_fresh(tmp_path):
    p = tmp_path / "recipes.json"
    p.write_text("{not json")
    assert RecipeCache(str(p)).recipes == {}


def test_failed_menu_fetch_is_an_error_not_a_crash():
    def down(url):
        raise RuntimeError("connection reset")
    m = fetch_hall_menu("chase", "2026-09-28", getter=down)
    assert m.status == "error"
    assert "dining.unc.edu" in m.message
    assert m.periods == []


def test_menu_fetch_builds_the_right_url():
    seen = []

    def spy(url):
        seen.append(url)
        return fixture_text("page_not_found.html")
    fetch_hall_menu("lenoir", "2026-10-01", getter=spy)
    assert seen == ["https://dining.unc.edu/locations/top-of-lenoir/?date=2026-10-01"]
