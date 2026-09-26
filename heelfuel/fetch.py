"""Network access: hall pages and recipe labels, with retries and a recipe cache."""

from __future__ import annotations

import gzip
import json
import logging
import os
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date as Date
from typing import Callable, Iterable, Optional

from . import config
from .model import HallMenu, Recipe
from .parse import parse_menu_page, parse_recipe

log = logging.getLogger("heelfuel.fetch")


def http_get(url: str, timeout: float = config.FETCH_TIMEOUT_S, retries: int = config.FETCH_RETRIES) -> str:
    """GET a URL as text, retrying transient failures with a growing pause."""
    last: Optional[Exception] = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": config.USER_AGENT,
                "Accept-Encoding": "gzip",
                "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
            })
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read()
                if resp.headers.get("Content-Encoding", "").lower() == "gzip":
                    body = gzip.decompress(body)
                return body.decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            last = e
            if 400 <= e.code < 500 and e.code not in (408, 429):
                break  # a real client error will not fix itself
        except Exception as e:  # timeouts, resets, DNS blips
            last = e
        time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"GET {url} failed: {last}")


def fetch_hall_menu(hall: str, day: str, getter: Callable[[str], str] = http_get) -> HallMenu:
    slug = config.HALLS[hall]["slug"]
    url = config.MENU_URL.format(slug=slug, date=day)
    try:
        page = getter(url)
    except Exception as e:
        log.warning("menu fetch failed for %s %s: %s", hall, day, e)
        return HallMenu(hall=hall, date=day, status="error", message="Couldn't reach dining.unc.edu for this menu.")
    try:
        return parse_menu_page(page, hall, day)
    except Exception as e:  # a redesign of the page should not take the whole site down
        log.exception("menu parse failed for %s %s", hall, day)
        return HallMenu(hall=hall, date=day, status="error", message=f"Menu page changed shape ({type(e).__name__}).")


class RecipeCache:
    """Recipe labels keyed by id, persisted as one JSON file and refreshed after RECIPE_CACHE_DAYS."""

    def __init__(self, path: Optional[str] = None) -> None:
        self.path = path
        self.recipes: dict[str, Recipe] = {}
        if path and os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    raw = json.load(f)
                self.recipes = {k: Recipe.from_dict(v) for k, v in raw.items()}
            except Exception:
                log.warning("recipe cache at %s unreadable, starting fresh", path)

    def save(self) -> None:
        if not self.path:
            return
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({k: v.to_dict() for k, v in sorted(self.recipes.items())}, f, separators=(",", ":"))
        os.replace(tmp, self.path)

    def is_fresh(self, rid: str, today: Date) -> bool:
        r = self.recipes.get(rid)
        if not r or not r.fetched:
            return False
        try:
            age = (today - Date.fromisoformat(r.fetched)).days
        except ValueError:
            return False
        return age < config.RECIPE_CACHE_DAYS

    def ensure(self, ids: Iterable[str], today: Date, getter: Callable[[str], str] = http_get) -> dict[str, str]:
        """Fetch every id that is missing or stale. Returns {id: error} for the ones that failed."""
        todo = sorted({i for i in ids if not self.is_fresh(i, today)})
        failures: dict[str, str] = {}
        if not todo:
            return failures

        def one(rid: str):
            try:
                text = getter(config.RECIPE_URL.format(rid=rid))
                return rid, parse_recipe(text, rid, fetched=today.isoformat()), None
            except Exception as e:
                return rid, None, str(e)

        with ThreadPoolExecutor(max_workers=config.FETCH_CONCURRENCY) as pool:
            for rid, recipe, err in pool.map(one, todo):
                if recipe is not None:
                    self.recipes[rid] = recipe
                else:
                    failures[rid] = err or "unknown error"
        if failures:
            # The server sheds load under concurrent requests; a slow, one-at-a-time second pass
            # recovers nearly everything the first pass dropped.
            log.info("recipes: %d failed on the first pass (e.g. %s); retrying one at a time",
                     len(failures), next(iter(failures.values()))[:160])
            for rid in list(failures):
                time.sleep(config.RETRY_PASS_DELAY_S)
                rid, recipe, err = one(rid)
                if recipe is not None:
                    self.recipes[rid] = recipe
                    del failures[rid]
                else:
                    failures[rid] = err or "unknown error"
        log.info("recipes: %d fetched, %d failed, %d cached", len(todo) - len(failures), len(failures), len(self.recipes))
        for rid, err in list(failures.items())[:5]:
            log.warning("recipe %s still failing: %s", rid, err[:200])
        return failures
