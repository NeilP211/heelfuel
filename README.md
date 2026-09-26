# HeelFuel

Every morning HeelFuel reads the posted menus for UNC's two dining halls, **Top of Lenoir** and **Chase**, and builds the best high-protein meals you can actually assemble from what's on the line, for every meal period.

**Live:** https://neilp211.github.io/heelfuel/

For each hall and meal period it shows the top three meals with calories, protein, carbs, fat, fiber and micronutrients, a short note on why each one ranks and what it trades off ("has Yellow 5 but best protein option"), and a way to make it taste good using that day's sauces and sides. At the top of the page is the day's total if you ate the top pick at every meal, measured against 160 g protein and a 2,800 to 3,200 kcal maingain range.

## How it works

```
hall pages (menus + ingredient text)    recipe.php (nutrition labels)
                 \                            /
                  v                          v
   classify every item: role, dyes and additives, processing level,
   fried, processed meat, estimated Mg / Zn / vitamin C / A / omega-3
                              |
                              v
   build meals per period: protein core, then carbs, produce, an extra;
   score each against that meal's share of the day's targets
                              |
                              v
   top 3 per period + the daily plan  ->  static page on GitHub Pages
```

- **Data:** the menu site is WordPress; each hall page embeds the full ingredient text for every item, and a JSON endpoint returns the nutrition label per recipe. No API keys, no scraping of anything private. Labels are cached for two weeks, so a normal run only fetches the handful of new recipes.
- **Scoring:** protein first, then calories, carbs and fat against that meal's share of the day, then evidence-weighted quality terms (fiber, fruit and vegetables, minimally processed food, micronutrients) and dose-scaled penalties (added sugar, sodium, saturated and trans fat, processed meat, fried food, dyes, emulsifiers, sweeteners). Every term carries an evidence grade, so weak gym and looksmaxxing claims (seed oils, dairy and acne, "bloat") count, but only a little. Nothing is thrown out for a gram of sugar or one additive.
- **Realism:** meals are built the way you'd actually eat: a chef's plate from one station plus salad-bar sides beats a plate scraped together from five lines; breakfast foods stay at breakfast; portions are capped (double protein is fine, three pounds of lettuce is not).
- **Bad data:** labels that can't be right (a 1,780 kcal slice of Swiss cheese, 27 g saturated fat in a 0 g fat vegetable side) are caught by plausibility checks, left out, and listed on the page.

The full research, targets, every scoring factor with its evidence grade, and the 60+ citations behind them are in **[RESEARCH.md](RESEARCH.md)**.

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

Targets, meal splits, evidence weights and every penalty live in `heelfuel/config.py`.

## Layout

| Path | What it does |
|---|---|
| `heelfuel/fetch.py`, `parse.py` | Hall pages and nutrition labels, with retries and a recipe cache |
| `heelfuel/classify.py`, `foods.py` | Item roles, additives, processing score, plausibility checks, micronutrient estimates |
| `heelfuel/score.py` | The meal score |
| `heelfuel/optimize.py`, `formats.py` | Meal search, realism rules, diversity of the top three |
| `heelfuel/explain.py`, `plan.py` | Titles, why-it-ranks notes, tasty ideas, the daily total |
| `heelfuel/build.py`, `render.py`, `web/index.html` | The pipeline and the page |
| `tests/` | Offline tests on real labels and a synthetic hall page |

Not medical advice. Allergens aren't filtered yet, so check the label at the station.
