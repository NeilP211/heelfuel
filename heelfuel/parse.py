"""Parsers for the two things dining.unc.edu serves: hall menu pages and recipe nutrition labels."""

from __future__ import annotations

import html
import json
import re
from html.parser import HTMLParser
from typing import Optional, Union

from . import config
from .model import HallMenu, MenuItem, Nutrition, Period, Recipe

# Typographic dashes and the minus sign become plain hyphens (built with chr so this file stays ASCII).
_DASHES = {chr(0x2013): "-", chr(0x2014): "-", chr(0x2012): "-", chr(0x2212): "-"}


def clean_text(s: str) -> str:
    """Collapse whitespace and swap typographic dashes for plain hyphens."""
    for bad, good in _DASHES.items():
        s = s.replace(bad, good)
    return " ".join(s.split())


def split_period_label(raw: str) -> tuple[str, str]:
    """'Breakfast  (7am-11am)' -> ('Breakfast', '7am-11am')."""
    raw = clean_text(raw)
    m = re.match(r"^(.*?)\s*\(([^)]*)\)\s*$", raw)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return raw, ""


def slot_for(label: str) -> tuple[str, bool]:
    return config.PERIOD_SLOTS.get(label.lower(), ("lunch", False))


class _MenuPageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tabs: list[tuple[str, str]] = []  # (aria-controls panel id, label)
        self.panels: dict[str, list[tuple[str, dict]]] = {}  # panel id -> [(station, item dict)]
        self.panel_order: list[str] = []
        self._cur_panel: Optional[str] = None
        self._cur_station = ""
        self._tab_controls: Optional[str] = None
        self._capture: Optional[str] = None  # tab / station / item
        self._buf: list[str] = []
        self._item: Optional[dict] = None
        self.saw_menu_tabs = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get("class") or ""
        if a.get("id") == "menu-tabs":
            self.saw_menu_tabs = True
        if tag == "button" and a.get("role") == "tab":
            self._tab_controls = a.get("aria-controls") or f"tab-{len(self.tabs)}"
        elif tag == "div" and "c-tabs-nav__link-inner" in cls and self._tab_controls is not None:
            self._capture, self._buf = "tab", []
        elif tag == "div" and a.get("role") == "tabpanel":
            pid = a.get("id") or f"panel-{len(self.panel_order)}"
            self._cur_panel = pid
            self._cur_station = ""
            self.panels.setdefault(pid, [])
            self.panel_order.append(pid)
        elif tag == "button" and "toggle-menu-station-data" in cls:
            self._capture, self._buf = "station", []
        elif tag == "li" and "menu-item-li" in cls:
            self._item = {"searchable": a.get("data-searchable") or ""}
        elif tag == "a" and "show-nutrition" in cls and self._item is not None:
            classes = cls.split()
            self._item["recipe"] = a.get("data-recipe") or ""
            self._item["allergens"] = [c[len("allergen-has_"):] for c in classes if c.startswith("allergen-has_")]
            self._item["props"] = [c[len("prop-"):] for c in classes if c.startswith("prop-")]
            self._capture, self._buf = "item", []

    def handle_endtag(self, tag):
        if self._capture == "tab" and tag == "div":
            self.tabs.append((self._tab_controls or "", "".join(self._buf)))
            self._capture, self._tab_controls = None, None
        elif self._capture == "station" and tag == "button":
            self._cur_station = clean_text("".join(self._buf))
            self._capture = None
        elif self._capture == "item" and tag == "a":
            if self._item is not None and self._cur_panel is not None:
                self._item["name"] = clean_text("".join(self._buf))
                self.panels[self._cur_panel].append((self._cur_station, self._item))
            self._capture, self._item = None, None
        elif tag == "li":
            self._item = None

    def handle_data(self, data):
        if self._capture:
            self._buf.append(data)


def parse_menu_page(page: str, hall: str, date: str) -> HallMenu:
    """Turn one hall page into periods of items. A page with no menu tabs means no menu is posted."""
    p = _MenuPageParser()
    p.feed(page)
    p.close()
    if not p.tabs:
        not_found = "Page Not Found" in page[:200000]
        msg = "No menu posted for this date." if (not_found or not p.saw_menu_tabs) else "Menu page had no meal periods."
        return HallMenu(hall=hall, date=date, status="no_menu", message=msg)

    periods: list[Period] = []
    for i, (controls, raw_label) in enumerate(p.tabs):
        label, hours = split_period_label(raw_label)
        slot, counts = slot_for(label)
        entries = p.panels.get(controls)
        if entries is None and i < len(p.panel_order):  # fall back to document order
            entries = p.panels[p.panel_order[i]]
        items = []
        for station, it in entries or []:
            if not it.get("recipe") or not it.get("name"):
                continue
            items.append(MenuItem(
                recipe_id=str(it["recipe"]),
                name=it["name"],
                station=station or "Other",
                searchable=it.get("searchable", ""),
                allergens=it.get("allergens", []),
                props=it.get("props", []),
            ))
        periods.append(Period(label=label, hours=hours, slot=slot, counts=counts, items=items))

    if not any(pr.items for pr in periods):
        return HallMenu(hall=hall, date=date, status="no_menu", message="Menu page listed no items.")
    return HallMenu(hall=hall, date=date, status="ok", periods=periods)


# ---------------------------------------------------------------- recipe labels

_LABEL_FIELDS = {
    "kcal": "Calories",
    "fat": "Total Fat",
    "sat_fat": "Saturated Fat",
    "trans_fat": "Trans Fat",
    "cholesterol": "Cholesterol",
    "sodium": "Sodium",
    "carbs": "Total Carbohydrate",
    "fiber": "Dietary Fiber",
    "sugars": "Sugars",
    "added_sugar": "Added Sugar",
    "protein": "Protein",
    "calcium": "Calcium",
    "iron": "Iron",
    "potassium": "Potassium",
    "vit_d": "Vitamin D",
}
_OPTIONAL = {"added_sugar", "vit_d"}


def _num(s: Optional[str]) -> Optional[float]:
    if s is None:
        return None
    s = s.replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def _field(label_html: str, label: str) -> tuple[bool, Optional[float]]:
    """(row present?, value) for one label row such as '<b>Sodium</b> 270 mg </th>'."""
    m = re.search(
        r"(?:<b>)?\s*" + re.escape(label) + r"\s*(?:</b>)?\s*([0-9][0-9.,]*)?\s*(?:g|mg|mcg)?\s*</th>",
        label_html,
        re.S,
    )
    if not m:
        return False, None
    return True, _num(m.group(1))


def parse_recipe(payload: Union[str, dict], rid: str, fetched: str = "") -> Recipe:
    data = json.loads(payload) if isinstance(payload, str) else payload
    if not data or not data.get("success") or not data.get("html"):
        raise ValueError(f"recipe {rid}: unexpected payload")
    h = data["html"]

    def grab(pattern: str) -> str:
        m = re.search(pattern, h, re.S)
        return clean_text(html.unescape(re.sub(r"<[^>]+>", " ", m.group(1)))) if m else ""

    name = grab(r"<h2>(.*?)</h2>")
    description = grab(r"</h2>\s*<p>(.*?)</p>")
    serving = grab(r"Amount Per Serving</strong>(.*?)</th>")
    allergens_txt = grab(r"<h6>Allergens</h6>\s*<p>(.*?)</p>")
    ingredients = grab(r"<strong>Ingredients:</strong>(.*?)</p>")

    values: dict = {}
    for key, label in _LABEL_FIELDS.items():
        present, val = _field(h, label)
        if key in _OPTIONAL:
            values[key] = val if present else None
        else:
            values[key] = val if val is not None else 0.0
    nutrition = Nutrition(**values)
    allergens = [a.strip() for a in allergens_txt.split(",") if a.strip()]
    return Recipe(
        id=str(rid),
        name=name,
        serving=serving,
        description=description,
        allergens=allergens,
        ingredients=ingredients,
        nutrition=nutrition,
        fetched=fetched,
    )
