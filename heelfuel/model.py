"""Plain data containers shared by the fetcher, scorer and renderer."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional

NUTRIENTS = (
    "kcal", "fat", "sat_fat", "trans_fat", "cholesterol", "sodium", "carbs", "fiber",
    "sugars", "added_sugar", "protein", "calcium", "iron", "potassium", "vit_d",
)


@dataclass
class Nutrition:
    kcal: float = 0.0
    fat: float = 0.0
    sat_fat: float = 0.0
    trans_fat: float = 0.0
    cholesterol: float = 0.0
    sodium: float = 0.0
    carbs: float = 0.0
    fiber: float = 0.0
    sugars: float = 0.0
    added_sugar: Optional[float] = None  # None when the label has no added-sugar row
    protein: float = 0.0
    calcium: float = 0.0
    iron: float = 0.0
    potassium: float = 0.0
    vit_d: Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Nutrition":
        return cls(**{k: d.get(k) for k in NUTRIENTS if k in d})


@dataclass
class Recipe:
    """One nutrition label from recipe.php."""

    id: str
    name: str
    serving: str = ""
    description: str = ""
    allergens: list[str] = field(default_factory=list)
    ingredients: str = ""
    nutrition: Nutrition = field(default_factory=Nutrition)
    fetched: str = ""  # ISO date the label was fetched

    def to_dict(self) -> dict:
        d = asdict(self)
        d["nutrition"] = self.nutrition.to_dict()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Recipe":
        d = dict(d)
        d["nutrition"] = Nutrition.from_dict(d.get("nutrition") or {})
        return cls(**d)


@dataclass
class MenuItem:
    """One line on a station, as listed on the hall page."""

    recipe_id: str
    name: str
    station: str
    searchable: str = ""  # lowercased ingredient text from data-searchable
    allergens: list[str] = field(default_factory=list)
    props: list[str] = field(default_factory=list)


@dataclass
class Period:
    label: str   # "Breakfast", "Late Night"...
    hours: str   # "7am-11am"
    slot: str    # breakfast / lunch / dinner / late_night
    counts: bool  # counts toward the daily total (False for Late Lunch, Late Dinner)
    items: list[MenuItem] = field(default_factory=list)

    @property
    def key(self) -> str:
        return self.label.lower().replace(" ", "-")


@dataclass
class HallMenu:
    hall: str        # config.HALLS key
    date: str        # YYYY-MM-DD
    status: str      # ok / no_menu / error
    message: str = ""
    periods: list[Period] = field(default_factory=list)
