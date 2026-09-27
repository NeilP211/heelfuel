"""Every tunable number lives here. RESEARCH.md explains where each one comes from."""

from __future__ import annotations

from dataclasses import dataclass

REPO_URL = "https://github.com/NeilP211/heelfuel"
SITE_URL = "https://neilp211.github.io/heelfuel/"
TIMEZONE = "America/New_York"

BASE_URL = "https://dining.unc.edu"
MENU_URL = BASE_URL + "/locations/{slug}/?date={date}"
RECIPE_URL = BASE_URL + "/wp-content/themes/nmc_dining/ajax-content/recipe.php?recipe={rid}&hide_allergens=0"
USER_AGENT = f"HeelFuel/1.0 (daily menu optimizer; {REPO_URL})"

# Order here is the order on the page.
HALLS = {
    "lenoir": {"name": "Top of Lenoir", "slug": "top-of-lenoir", "building": "Lenoir Hall"},
    "chase": {"name": "Chase", "slug": "chase", "building": "Chase Hall"},
}

FETCH_CONCURRENCY = 4
FETCH_TIMEOUT_S = 30
FETCH_RETRIES = 3
RECIPE_CACHE_DAYS = 14
RETRY_PASS_DELAY_S = 0.4

# Period label (lowercased, hours stripped) -> (meal slot, is it a main period rather than a late alternate?)
PERIOD_SLOTS = {
    "breakfast": ("breakfast", True),
    "continental": ("breakfast", True),
    "brunch": ("lunch", True),
    "lunch": ("lunch", True),
    "late lunch": ("lunch", False),
    "dinner": ("dinner", True),
    "late dinner": ("dinner", False),
    "late night": ("late_night", True),
}


@dataclass(frozen=True)
class MealTarget:
    """What one good athlete meal looks like, judged on its own (no daily totals)."""
    kind: str
    kcal_lo: float
    kcal_hi: float
    protein: float        # full protein credit at this many grams
    carbs_lo: float
    carbs_hi: float
    fat_lo: float
    fat_hi: float
    dv_share: float       # a meal covering this share of a nutrient's Daily Value gets full credit
    produce_cups: float
    sodium_allowance: float
    refined_carb_free: float

    @property
    def kcal_mid(self) -> float:
        return (self.kcal_lo + self.kcal_hi) / 2


MEAL_TARGETS = {
    "breakfast": MealTarget("breakfast", 500, 800, 35, 45, 100, 10, 30, 0.30, 1.0, 800, 40),
    "main": MealTarget("main", 600, 950, 42, 60, 120, 12, 35, 1 / 3, 1.5, 1000, 50),
    "late": MealTarget("late", 300, 600, 28, 25, 70, 5, 22, 0.20, 0.5, 600, 25),
}
SLOT_KIND = {"breakfast": "breakfast", "lunch": "main", "dinner": "main", "late_night": "late"}

# FDA label Daily Values (21 CFR 101.9), the same %DV column UNC's own nutrition panel shows.
# Omega-3 has no FDA Daily Value; 500 mg EPA+DHA is a common target and is labeled as such.
DV = {
    "fat": 78.0, "sat_fat": 20.0, "cholesterol": 300.0, "sodium": 2300.0, "carbs": 275.0,
    "fiber": 28.0, "added_sugar": 50.0, "protein": 50.0, "vit_d": 20.0, "calcium": 1300.0,
    "iron": 18.0, "potassium": 4700.0, "magnesium": 420.0, "zinc": 11.0, "vit_c": 90.0,
    "vit_a": 900.0, "epa_dha": 500.0,
}

# Micronutrient score: how much of each nutrient's per-meal share of the Daily Value a meal covers.
# Label-measured nutrients get more weight than ones estimated from the food (see RESEARCH.md 3.7).
MICRO_WEIGHTS = {
    "fiber": 1.0, "potassium": 1.0, "iron": 0.8, "calcium": 0.7, "vit_d": 0.6,
    "magnesium": 0.8, "zinc": 0.8, "vit_c": 0.9, "vit_a": 0.6, "epa_dha": 0.5,
}
ESTIMATED = {"magnesium", "zinc", "vit_c", "vit_a", "epa_dha"}

# Score out of 100 = MACROS (35) + MICROS (35) + CLEAN (30).
MACRO_POINTS = {"protein": 18.0, "kcal": 8.0, "carbs": 5.0, "fat": 4.0}
MICRO_DV_POINTS = 30.0
PRODUCE_POINTS = 5.0
WHOLE_FOOD_POINTS = 15.0
CLEAN_BASE_POINTS = 15.0
PROTEIN_SOFT_CAP = 1.6     # past 160% of the meal's protein target, extra protein starts to cost a little
PROTEIN_OVER_PTS = 10.0
KCAL_TAPER = 0.35          # calories this far outside the band (as a share of the band's middle) earn nothing

# Evidence weights (RESEARCH.md section 3.1).
GRADE = {"A": 1.0, "B+": 0.8, "B": 0.65, "C": 0.35, "D": 0.15}

# key: (grade, cap on raw points). These come out of the 15 CLEAN_BASE_POINTS.
PENALTY = {
    "added_sugar": ("A", 10.0),
    "sodium": ("B", 8.0),
    "sat_fat": ("B", 5.0),
    "trans_fat": ("A", 8.0),
    "processed_meat": ("B+", 7.0),
    "fried": ("B", 5.0),
    "dyes": ("C", 9.0),
    "red_flag_additives": ("C", 6.0),
    "emulsifiers": ("C", 6.0),
    "sweeteners": ("C", 4.0),
    "seed_oils": ("D", 4.0),
    "glycemic_load": ("C", 5.0),
    "dairy_acne": ("C", 2.0),
    "phosphates": ("D", 2.0),
    "cosmetic_color": ("D", 2.0),
    "bloat": ("D", 3.0),
}

# Dose rules (RESEARCH.md section 3.2).
ADDED_SUGAR_PER_MEAL = 10.0   # DGA 2025-2030 per-meal cap: under it costs nothing
ADDED_SUGAR_PTS_PER_G = 0.35
SODIUM_GRACE_MG = 200
SODIUM_PTS_PER_200MG = 1.0
SAT_FAT_PCT = 0.10
SAT_FAT_PTS_PER_G = 0.3
TRANS_PTS_PER_G = 3.0
PHO_PTS = 2.0
PROCESSED_MEAT_PTS_PER_50G = 3.5
FRIED_PTS = 5.0
DYE_PTS = 3.0
RED_FLAG_PTS = 3.0
SEED_OIL_PTS = 4.0
REFINED_CARB_PTS_PER_15G = 1.0
DAIRY_PTS_PER_CUP = 0.8
PHOSPHATE_PTS = 0.5
CARAMEL_PTS = 1.0
BLOAT_SODIUM_MG = 1500.0
BLOAT_PTS_PER_300MG = 1.0

# Builds.
BUILDS_PER_PERIOD = 5
BEAM_WIDTH = 24
THEME_BONUS_PER_ITEM = 1.0
THEME_BONUS_CAP = 3.0
