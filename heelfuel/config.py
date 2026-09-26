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
    "lenoir": {"name": "Top of Lenoir", "slug": "top-of-lenoir"},
    "chase": {"name": "Chase", "slug": "chase"},
}

FETCH_CONCURRENCY = 4
FETCH_TIMEOUT_S = 30
FETCH_RETRIES = 3
RECIPE_CACHE_DAYS = 14
RETRY_PASS_DELAY_S = 0.4


@dataclass(frozen=True)
class DailyTargets:
    kcal: float = 3000
    kcal_lo: float = 2800
    kcal_hi: float = 3200
    protein: float = 160
    carbs: float = 390
    carbs_lo: float = 320
    carbs_hi: float = 450
    fat: float = 85
    fat_lo: float = 65
    fat_hi: float = 110
    fiber: float = 40
    produce_cups: float = 6.0
    sodium_ref: float = 2300      # NASEM chronic disease risk reduction intake
    sodium_allowance: float = 3000  # what the scorer allows a sweaty lifter before penalizing
    added_sugar_per_meal: float = 10  # DGA 2025-2030 per-meal cap
    satfat_pct: float = 0.10


DAILY = DailyTargets()

# (share of the day's calories, share of the day's protein)
SLOT_SHARES = {
    "breakfast": (0.24, 0.25),
    "lunch": (0.33, 0.30),
    "dinner": (0.33, 0.30),
    "late_night": (0.10, 0.15),
}
MAIN_SLOTS = ("breakfast", "lunch", "dinner", "late_night")
SLOT_LABELS = {
    "breakfast": "Breakfast",
    "lunch": "Lunch",
    "dinner": "Dinner",
    "late_night": "Late night",
}

# Period label (lowercased, hours stripped) -> (slot whose targets it uses, counts toward the daily total?)
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

# Daily reference values (men 19-30) used for %DV and micronutrient credit.
DV = {
    "potassium": 3400.0,   # mg, AI (NASEM 2019)
    "calcium": 1000.0,     # mg, RDA
    "iron": 8.0,           # mg, RDA
    "vit_d": 15.0,         # mcg, RDA
    "magnesium": 400.0,    # mg, RDA
    "zinc": 11.0,          # mg, RDA
    "vit_c": 90.0,         # mg, RDA
    "vit_a": 900.0,        # mcg RAE, RDA
    "epa_dha": 500.0,      # mg, common EPA+DHA target
}

# Evidence weights (RESEARCH.md section 3.1).
GRADE = {"A": 1.0, "B+": 0.8, "B": 0.65, "C": 0.35, "D": 0.15}

# Raw points for each factor before the evidence weight (RESEARCH.md section 3.2).
FIT_POINTS = {"protein": 28.0, "kcal": 14.0, "carbs": 12.0, "fat": 6.0}

QUALITY = {
    # key: (raw points, grade)
    "fiber": (8.0, "A"),
    "produce": (7.0, "A"),
    "whole_food": (8.0, "B+"),
    "label_micros": (6.0, "B"),
    "est_micros": (4.0, "C"),
    "protein_quality": (3.0, "B"),
    "carb_quality": (4.0, "B"),
}

BONUS = {
    "oily_fish": (4.0, "B"),
    "presleep_protein": (3.0, "B"),
}

# key: (grade, cap on raw points)
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
ADDED_SUGAR_PTS_PER_G = 0.35
SODIUM_GRACE_MG = 200
SODIUM_PTS_PER_200MG = 1.0
SAT_FAT_PTS_PER_G = 0.3
TRANS_PTS_PER_G = 3.0
PHO_PTS = 2.0
PROCESSED_MEAT_PTS_PER_50G = 3.5
FRIED_PTS = 5.0
DYE_PTS = 3.0
RED_FLAG_PTS = 3.0
SEED_OIL_PTS = 4.0
REFINED_CARB_FREE_G = 45.0
REFINED_CARB_PTS_PER_15G = 1.0
DAIRY_PTS_PER_CUP = 0.8
PHOSPHATE_PTS = 0.5
CARAMEL_PTS = 1.0
BLOAT_SODIUM_MG = 1500.0
BLOAT_PTS_PER_300MG = 1.0
# Protein past 130% of a meal's target costs 1 point per extra 10% (cap 6): more is fine, but not free.
PROTEIN_SOFT_CAP = 1.3
PROTEIN_OVER_PTS = 10.0

# Per-meal fit bands: calories within +/-12% get full credit and taper to zero 40% beyond that;
# carbs get full credit from 70% to 135% of the meal's share.
KCAL_BAND = 0.12
KCAL_TAPER = 0.40
CARB_BAND = (0.70, 1.35)

# Realism (not a health factor): a plate built at one station plus salad-bar sides is free; each
# extra hot-food station costs points, and so does mixing unrelated starches.
STATION_PTS = 2.5
SIDE_STATION_WEIGHT = 0.5
SIDE_STATIONS = ("salad bar", "hummus bar", "fruit", "beverage")
STARCH_CLASH_PTS = 1.5
SWEET_SAVORY_PTS = 8.0  # effectively rules out yogurt-with-beans plates
FORMAT_BONUS = 4.0
DESIGNED_PAIR_PTS = 2.0
PROTEIN_MIX_PTS = 1.5
EXTRA_FOOD_PTS = 0.5
OMEGA3_FULL_MG = 1000.0

# FIT (60) + the effective QUALITY maximum (31.25) + the meal-format bonus (4) maps to 100.
# Oily fish, pre-sleep protein and chef-built pairings can push past it; the page caps at 100
# but ranking uses the uncapped number so ties at the top still sort sensibly.
SCORE_SCALE = 95.25

# Optimizer shape (RESEARCH.md section 5).
POOL_SIZES = {"protein": 10, "carb": 8, "produce": 8, "extra": 6}
MAX_FOODS = 5
TOP_N = 3
