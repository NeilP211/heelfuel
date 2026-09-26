import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from heelfuel.classify import analyze  # noqa: E402
from heelfuel.model import MenuItem  # noqa: E402
from heelfuel.parse import parse_menu_page, parse_recipe  # noqa: E402

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def fixture_text(name: str) -> str:
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="session")
def recipe_ids() -> dict:
    return json.loads(fixture_text("recipe_ids.json"))


@pytest.fixture(scope="session")
def recipes(recipe_ids) -> dict:
    return {rid: parse_recipe(fixture_text(f"recipes/{rid}.json"), rid, fetched="2026-09-28")
            for rid in recipe_ids.values()}


@pytest.fixture(scope="session")
def menu():
    return parse_menu_page(fixture_text("menu_small.html"), "chase", "2026-09-28")


@pytest.fixture
def foods_for(menu, recipes):
    def build(label: str):
        period = next(p for p in menu.periods if p.label == label)
        return [analyze(it, recipes[it.recipe_id]) for it in period.items]
    return build


@pytest.fixture
def food(recipes, recipe_ids):
    def build(name: str, station: str = "The Kitchen Table"):
        rid = recipe_ids[name]
        return analyze(MenuItem(recipe_id=rid, name=name, station=station), recipes[rid])
    return build


def make_getter(hall_pages: dict):
    """A stand-in for http_get that serves fixtures: hall slug -> page file, recipes from fixtures."""
    def get(url: str) -> str:
        if "recipe.php" in url:
            rid = url.split("recipe=")[1].split("&")[0]
            return fixture_text(f"recipes/{rid}.json")
        for slug, page in hall_pages.items():
            if f"/locations/{slug}/" in url:
                if page is None:
                    raise RuntimeError("connection refused")
                return fixture_text(page)
        raise AssertionError(f"unexpected URL {url}")
    return get
