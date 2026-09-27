# HeelFuel

Every morning HeelFuel reads the posted menus for UNC's two dining halls, **Top of Lenoir** and **Chase**, and builds athlete meals you can put together from what's actually on the line: high protein, loaded with micronutrients, minimally processed. It does this for every meal period (breakfast, lunch, late lunch, dinner, late dinner, late night, and the weekend continental and brunch).

**Live:** https://neilp211.github.io/heelfuel/

Each period gets up to five builds, like a Chicken Shawarma Bowl, a Chipotle Lime Chicken Power Salad or a Loaded Scramble Plate, pulled from whichever stations have the best parts that day. Every build shows:

- a score out of 100 split into **Macros**, **Micros** and **Clean**
- calories, protein, carbs, fat and fiber, with **% Daily Value**
- the six nutrients it covers best as % Daily Value (vitamin C, potassium, iron, zinc...)
- **Build it**: each item grouped by station, with servings; tap any item for its UNC nutrition label
- how to plate it, why it ranks, and what it trades off ("Salty: 2,325 mg sodium", "Yellow 5 in Spinach Wrap")
- a Nutrition Facts panel for the whole meal

Each meal is judged on its own. There's no daily plan and no running total. The page is styled after UNC's own menu pages.

## How it works

```
hall pages (menus + ingredient text)    recipe.php (nutrition labels)
                 \                            /
                  v                          v
   classify every item: role, dyes and additives, processing level,
   fried, processed meat, estimated Mg / Zn / vitamin C / A / omega-3
                              |
                              v
   fill 13 dish templates (burrito bowl, power salad, scramble...)
   from every station, beam search, score each build per meal
                              |
                              v
   up to 5 distinct builds per period  ->  static page on GitHub Pages
```

- **Data:** the menu site is WordPress; each hall page embeds the full ingredient text for every item, and a JSON endpoint returns the nutrition label per recipe. No API keys, nothing private. Labels are cached for two weeks, so a normal run only fetches the handful of new recipes.
- **Scoring:** Macros (35) is protein first, then calories, carbs and fat against that one meal's target. Micros (35) is % Daily Value coverage of fiber, potassium, iron, calcium, vitamin D, magnesium, zinc, vitamins C and A and omega-3, plus fruit and vegetables. Clean (30) is how much of the meal is minimally processed, minus dose-scaled, evidence-weighted deductions (added sugar, sodium, saturated and trans fat, processed meat, fried food, dyes, emulsifiers, sweeteners). Weak gym and looksmaxxing claims (seed oils, dairy and acne, "bloat") count, but only a little. Nothing is thrown out for a gram of sugar or one additive.
- **Athlete food:** protein comes from meat, fish, eggs and dairy; no tofu, quinoa or vegan swaps, and deli ham or bacon never anchors a build.
- **Real dishes:** builds keep a cuisine together (no Santa Fe beef over penne with Szechuan green beans), portions are capped, and two builds that share most of their items count as one.
- **Bad data:** labels that can't be right (a 1,780 kcal slice of Swiss cheese, 93 mg of iron in 2 Tbsp of salsa, vitamin D entered in IU) are caught, corrected or left out, and listed on the page.

The full research, per-meal targets, every scoring factor with its evidence grade, and the citations behind them are in **[RESEARCH.md](RESEARCH.md)**.

## Schedule

A GitHub Actions workflow runs the tests, builds the site and deploys it three times a day: early morning Eastern (5:17 AM EDT), late morning, and early evening so tomorrow's menu is ready when you plan. If a hall is closed or a menu isn't posted, the page says so; if dining.unc.edu is unreachable for every menu, the run fails and the last good page stays up.

## Run it locally

Python 3.10+, no dependencies beyond the standard library.

```bash
python -m heelfuel.build --out site --cache .cache/recipes.json   # today and tomorrow
python -m heelfuel.build --date 2026-10-01 --days 1                  # a specific day
python -m http.server -d site 8000                                   # then open localhost:8000
pip install pytest && python -m pytest -q                            # tests run offline on fixtures
```

Per-meal targets, Daily Values, evidence weights and every penalty live in `heelfuel/config.py`.

## Layout

| Path | What it does |
|---|---|
| `heelfuel/fetch.py`, `parse.py` | Hall pages and nutrition labels, with retries and a recipe cache |
| `heelfuel/classify.py`, `foods.py` | Item roles, additives, processing score, label sanity checks, micronutrient estimates |
| `heelfuel/score.py` | The Macros / Micros / Clean score |
| `heelfuel/builds.py` | Dish templates, the build search, cuisine and variety rules |
| `heelfuel/explain.py` | Steps by station, % Daily Value, why it ranks, tradeoffs, item labels |
| `heelfuel/build.py`, `render.py`, `web/index.html` | The pipeline and the page |
| `tests/` | Offline tests on real labels and a synthetic hall page |

Not medical advice. Allergens aren't filtered yet, so check the label at the station.
