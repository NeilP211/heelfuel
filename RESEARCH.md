# HeelFuel research notes

Research done 2026-09-26, before any code was written. It covers three things:

1. **Where the menu data comes from** and exactly what it contains (and doesn't).
2. **The daily targets** for a "maingaining" lifter and how they're split across meals.
3. **The scoring rubric**: every factor, how it's dosed, how much it can move a score, and how strong the evidence behind it is.

Everything in sections 2 to 5 is implemented in `heelfuel/config.py`, `heelfuel/score.py` and `heelfuel/optimize.py`. If a number here and a number in the code ever disagree, the code is what runs, so fix whichever is wrong.

---

## 1. Data source

### 1.1 How dining.unc.edu loads menus

The "Menu & Hours" page (`https://dining.unc.edu/menu-hours/`) is a WordPress site (theme `nmc_dining`, built by the agency NMC). It is not backed by Nutrislice (the `unc.nutrislice.com` style hosts don't exist) and there is no public JSON menu API. The data lives in two places:

| What | URL | Format |
|---|---|---|
| Daily menu for one hall | `https://dining.unc.edu/locations/{slug}/?date=YYYY-MM-DD` (slugs `top-of-lenoir`, `chase`) | Server-rendered HTML, 4 to 7 MB per page (mostly a few thousand copies of the same inline SVG icons) |
| Nutrition for one recipe | `https://dining.unc.edu/wp-content/themes/nmc_dining/ajax-content/recipe.php?recipe={id}&hide_allergens=0` | JSON `{"success": true, "html": "..."}` whose `html` is an FDA-style nutrition label |

The hall page structure:

- Meal periods are tabs: `button[role=tab] > div.c-tabs-nav__link-inner` with text like `Breakfast (7am-11am)`. Each tab's `aria-controls` points at a `div[role=tabpanel]`.
- Inside a panel, each station is a `div.menu-station` whose `button.toggle-menu-station-data` holds the station name ("Simply Prepared", "Deli", "Salad Bar"...).
- Each item is an `li.menu-item-li`. Its `data-searchable` attribute holds the **full ingredient text** (lowercased, punctuation stripped). Inside it, `a.show-nutrition` carries `data-recipe="{id}"`, the item name as its text, and CSS classes that encode allergens (`allergen-has_milk`, `allergen-has_wheat`...) and properties (`prop-vegan`, `prop-vegetarian`, `prop-halal`, `prop-made_without_gluten`, `prop-smart_choice`, `prop-local`, `prop-organic`).
- The site's own JS (`unc_dining/scripts/all.min.js`) calls `recipe.php` when you tap an item. That endpoint needs no cookies, nonce or key.
- A date with no posted menu returns **HTTP 200 with a "Page Not Found" body** (a soft 404). The fetcher treats "no `menu-tabs` element" as "no menu posted", not as an error.

A second source exists: `eatunc.com` (a Next.js app) returns an `allEntries` array in its React Server Component payload when requested with the header `RSC: 1`. It carries periods, stations and the same recipe numbers, plus macros, but no ingredients and no micronutrients, so HeelFuel does not use it. It is noted here as a fallback if dining.unc.edu ever blocks automated requests.

### 1.2 Meal periods (fall 2026)

| Hall | Weekday | Saturday | Sunday |
|---|---|---|---|
| Chase | Breakfast 7-11, Lunch 11-3, Late Lunch 3-5, Dinner 5-8, Late Dinner 8-9, **Late Night 9pm-12am** | Continental 9-11, Brunch 11-3, Late Lunch 3-5, Dinner 5-8 | Continental, Brunch, Late Lunch, Dinner, Late Dinner, Late Night |
| Top of Lenoir | Breakfast 7-11, Lunch 11-3, Late Lunch 3-5, Dinner 5-8:30 | Continental 10-11, Brunch 11-3 (closed after) | Continental, Brunch, Late Lunch, Dinner |

HeelFuel maps these onto four meal slots: **breakfast** (Breakfast, Continental), **lunch** (Lunch, Brunch), **dinner** (Dinner) and **late night** (Late Night). Late Lunch and Late Dinner are reduced versions of the lunch and dinner lines (Chase's Late Lunch drops 6 of 23 stations), so they get their own recommendations but count as alternatives, not extra meals, in the daily total.

### 1.3 What each item carries

Measured on every recipe served at both halls on Monday 2026-09-28 (413 unique recipes, 1,269 menu slots):

| Field | Coverage | Notes |
|---|---|---|
| Serving size | 100% | Household measures only: `1 each` (75), `Tbsp` (71), `½ cup` (68), `cup` (54), `oz` (43), `fl oz` (27), `slice` (34), `serving` (26), `g` (11) |
| Calories, total fat, saturated fat, trans fat, cholesterol, sodium, carbohydrate, fiber, total sugars, protein | 100% | |
| Added sugars | 78% | 91 recipes have no added-sugar row |
| Calcium, iron, potassium | 100% | mg values are usable; the %DV column is not (31 mg calcium shows "0%") |
| Vitamin D | 93% | 27 recipes show an empty value |
| Ingredients | 100% | Full label text including sub-ingredients of purchased components, e.g. the pancake mix inside "Waffle" |
| Allergens and dietary flags | 100% | 9 major allergens plus gluten; vegan, vegetarian, halal, made-without-gluten, "smart choice", local, organic |

**Not available anywhere:** magnesium, zinc, omega-3s, vitamin C, vitamin A/carotenoids, B vitamins, portion weight in grams, how much cooking oil was used, glycemic index, or any processing classification. HeelFuel estimates the missing micronutrients from food identity (section 3.7) and processing level from the ingredient text (section 3.11), and labels both as estimates on the page.

### 1.4 Data quality problems found

These are real rows from the feed, not hypotheticals:

- **Impossible nutrition:** "Swiss Cheese, 1 slice: 1,780 kcal, 136 g protein"; "Parmesan Cheese, 2 Tbsp: 1,780 kcal, 162 g protein". The macros add up (4P + 4C + 9F matches the calories), so these look like whole-batch numbers attached to a single serving.
- **Implausible for the stated serving:** "Baby Carrots, ½ cup: 170 kcal, 41 g carbs"; "Sliced English Cucumber, 2 Tbsp: 70 kcal"; "Tortilla Chips, 2 oz: 60 kcal, 0 g carbs".
- **Missing:** "Wheat Bread Slice: 0 kcal".
- **Inconsistent sugar rows:** added sugar larger than total sugar in about 1% of recipes (Waffle: 0 g sugars, 3 g added).
- **Serving labels that don't match the macros:** "Cilantro Marinated Chicken, ¼ cup: 26 g protein" (that's a 3 to 4 oz portion). HeelFuel treats one serving as "one scoop as served on the line" and always shows the label's stated size next to it.
- **Zero fiber where there must be some** (brown rice, ½ cup: 0 g).

Section 5.4 lists the plausibility rules that flag the first three kinds of row. Flagged items are left out of recommendations and listed at the bottom of the page, so nothing disappears silently.

### 1.5 Fetch plan and politeness

Each run loads 2 halls x 2 days (today and tomorrow, Eastern time), about 20 MB of HTML, plus one `recipe.php` call per recipe it hasn't seen in the last 14 days. A cold start is about 400 calls per day of menus; a warm cache needs a few dozen. Calls run 4 at a time with a 30 s timeout and 3 retries with backoff (in testing about 7% of first attempts timed out under load and all succeeded on retry). Requests identify themselves with a User-Agent that includes the repo URL.

---

## 2. Targets

### 2.1 The reference lifter

You asked me not to ask for personal stats, so the defaults describe a typical male college lifter: 20 years old, 178 cm (5'10"), 75 kg (165 lb), lifting 4 to 5 days a week and walking campus.

| Quantity | Value | Where it comes from |
|---|---|---|
| Resting energy | ~1,770 kcal | Mifflin-St Jeor: 10 x 75 + 6.25 x 178 - 5 x 20 + 5 [Mifflin 1990] |
| Activity factor | ~1.65 | FAO/WHO/UNU "active" band (1.70 to 1.99) shaded down, since lifting burns less than it feels like [FAO/WHO/UNU 2004] |
| Maintenance | ~2,900 kcal | 1,770 x 1.65 |
| **Calorie band** | **2,800 to 3,200 kcal, aiming for 3,000** | Maintenance to about +10%. Off-season guidance is a 10 to 20% surplus for novices and less for trained lifters [Iraki 2019]; "maingaining" is the conservative end, and a large surplus is not required to build muscle [Slater 2019] |
| **Protein** | **160 g (2.1 g/kg)** | Gains in fat-free mass plateau around 1.6 g/kg with a confidence interval up to 2.2 g/kg [Morton 2018]; ISSN says 1.4 to 2.0 g/kg [Jäger 2017]; off-season bodybuilding reviews say 1.6 to 2.2 [Iraki 2019]. 160 g sits at the top of the useful range, which is right for a "top priority" target. (The 2025-2030 Dietary Guidelines now say 1.2 to 1.6 g/kg for the general public [DGA 2025].) |
| **Carbohydrate** | **~390 g (5.2 g/kg), band 320 to 450** | Strength athletes: 4 to 7 g/kg [Slater & Phillips 2011]; at least 3 to 5 g/kg to support training [Iraki 2019]. Carbs mainly matter for high-volume sessions (roughly 10+ sets per muscle) and when training fasted [Henselmans 2022], so they're "important" but below protein |
| **Fat** | **~85 g (about 25% of calories), floor ~60 g** | 0.5 to 1.5 g/kg [Iraki 2019]; below about 20% of calories, intervention studies show lower testosterone in men [Whittaker & Wu 2021] |
| **Fiber** | **40 g** | 14 g per 1,000 kcal [DGA]; benefits start at 25 to 29 g/day and keep improving above that [Reynolds 2019] |
| **Sodium** | 2,300 mg reference, 3,000 mg scoring allowance | 2,300 mg is the chronic disease risk reduction intake [NASEM 2019]. Lifters lose sodium in sweat (typically 20 to 80 mmol per liter [Baker 2017]), so the scorer allows 3,000 mg before penalizing |
| **Added sugar** | 10 g per meal | The 2025-2030 Dietary Guidelines' per-meal cap [DGA 2025]; WHO says under 10% of energy, ideally under 5% [WHO 2015] |
| **Saturated fat** | under 10% of calories | Unchanged in DGA 2025-2030; lowering it reduces cardiovascular events [Hooper 2020] |

### 2.2 Splitting the day across meals

Protein is split to put at least 0.4 g/kg (30 g) in every meal and more in the big ones [Schoenfeld & Aragon 2018]. The old "30 g per meal max" idea is out: 100 g of protein after training produced a larger and longer anabolic response than 25 g [Trommelen 2023], so big lunches and dinners are fine.

| Slot | Share of calories | Share of protein | Targets on a 4-meal day |
|---|---|---|---|
| Breakfast | 24% | 25% | 720 kcal, 40 g protein |
| Lunch | 33% | 30% | 990 kcal, 48 g protein |
| Dinner | 33% | 30% | 990 kcal, 48 g protein |
| Late night | 10% | 15% | 300 kcal, 24 g protein |

When a day has no late-night period at either hall (Saturdays, for example), the shares are renormalized over the meals that exist, so the three meals get bigger and the daily total still aims at 160 g and 3,000 kcal. Late night gets a larger protein share than calorie share on purpose: 27.5 g of protein every night before sleep increased muscle and strength gains over 12 weeks of training compared with a placebo [Snijders 2015].

Carbs, fat, fiber and produce follow the calorie share. Per-meal "good enough" bands: calories within 12% of target (credit then tapers to zero 40% beyond that), protein at least 95% of target, carbs 70 to 135%, fat 60 to 140%. The bands are deliberately loose per meal because the day is what counts: the daily total at the top of the page is where you check 160 g and the calorie range.

---

## 3. Scoring rubric

### 3.1 How a meal is scored

Every candidate meal (a set of items with servings) gets a score from 0 to 100:

```
score = 100 x (FIT + QUALITY + BONUSES - PENALTIES + REALISM) / 95.25     (shown capped at 100)
```

- **FIT (max 60)** is how well the meal hits its slot's targets. These are your stated goals, so they aren't discounted by evidence.
- **QUALITY (max 31.25 effective)** rewards fiber, produce, minimally processed food, micronutrients, protein quality and carb quality.
- **PENALTIES** are dose-scaled: each one starts at zero, grows with the amount present, and has a cap. Additive penalties are per item and grow with servings of that item (the second and third servings count half as much as the first).
- **REALISM** is not a health factor: it rewards meals you'd actually assemble (a chef's plate from one station, a bowl, a salad) and costs points for running between five lines or pairing yogurt with black beans (section 5.3). It's in the score so the top pick is something you'd eat, not an optimizer's grab bag.
- 95.25 = 60 + 31.25 + the 4-point meal-format bonus, so a perfect, recognizable meal scores 100. Oily fish, pre-sleep protein and chef pairings can push past 100; the page caps the display at 100, but ranking uses the uncapped number so near-ties still sort sensibly.
- Every QUALITY, BONUS and PENALTY term is multiplied by an **evidence weight**:

| Grade | Weight | Meaning |
|---|---|---|
| A | 1.00 | Consistent RCTs and/or meta-analyses in humans |
| B+ | 0.80 | Human RCTs plus consistent large cohorts, some uncertainty on size of effect |
| B | 0.65 | Some human RCTs or consistent cohorts plus a plausible mechanism |
| C | 0.35 | Small or short human trials, animal/mechanistic data, or inconsistent cohorts |
| D | 0.15 | Mostly anecdote or community claim (gym/looksmaxxing lore) with little direct evidence |

This is how "factor in the weak claims, but weight them less" is implemented: a D-grade factor can never move a score by more than a point or so.

### 3.2 Every factor at a glance

Effective max = raw points x evidence weight. "Per meal" allowances scale with the slot's share of the day.

| # | Factor | Measured as | Dose rule | Raw max | Grade | Effective max |
|---|---|---|---|---|---|---|
| F1 | Protein amount | protein vs slot target | full at 95% of target, curve `(ratio / 0.95)^1.6` below; past 130% of target, 1 point per extra 10% (cap 6) because extra protein crowds out training carbs | 28 | (target) | 28 |
| F2 | Calories | kcal vs slot target | full within +/-12%, linear to zero 40% beyond that band | 14 | (target) | 14 |
| F3 | Carbs | carbs vs slot target | full at 70-135%, curve below, linear taper above | 12 | (target) | 12 |
| F4 | Fat | fat vs slot target | full at 60-140% | 6 | (target) | 6 |
| Q1 | Fiber | g vs slot share of 40 g | linear to target | 8 | A | 8.0 |
| Q2 | Fruit and vegetables | estimated cups vs slot share of 6 cups/day | linear to target | 7 | A | 7.0 |
| Q3 | Minimally processed food | calorie-weighted share of non-ultra-processed items (3.11) | linear | 8 | B+ | 6.4 |
| Q4 | Label micronutrients | potassium, calcium, iron, vitamin D vs slot share of the RDA/AI | weighted average, capped per nutrient | 6 | B | 3.9 |
| Q5 | Estimated micronutrients | magnesium, zinc, vitamin C, vitamin A, EPA+DHA (3.7) | same | 4 | C | 1.4 |
| Q6 | Protein quality | protein-weighted digestibility/amino-acid score proxy | linear to 0.9 | 3 | B | 1.95 |
| Q7 | Carb quality | share of carb grams from whole grains, legumes, fruit, veg, potatoes, oats, dairy | linear | 4 | B | 2.6 |
| B1 | Oily fish | estimated EPA+DHA | linear to 1 g | 4 | B | 2.6 |
| B2 | Slow protein before bed | late-night meal with 10 g+ protein from cottage cheese, Greek yogurt or milk | on/off | 3 | B | 1.95 |
| P1 | Added sugar | g above 10 g per meal | 0.35 per g, cap 10 | 10 | A | 10.0 |
| P2 | Sodium | mg above the meal's share of 3,000 mg (+200 mg grace) | 1 per 200 mg, cap 8 | 8 | B | 5.2 |
| P3 | Saturated fat | g above 10% of the meal's calories | 0.3 per g, cap 5 | 5 | B | 3.25 |
| P4 | Trans fat | label trans fat from industrial sources (partially hydrogenated, hydrogenated or interesterified oils, shortening); dairy and meat trans fat counts at 10% | 3 per g, +2 for PHO, cap 8 | 8 | A | 8.0 |
| P5 | Processed meat | estimated grams of cured/processed meat | 3.5 per 50 g, cap 7 | 7 | B+ | 5.6 |
| P6 | Deep-fried food | share of calories from fried items | 5 x share | 5 | B | 3.25 |
| P7 | Synthetic dyes | distinct certified dyes (Red 40, Yellow 5, Yellow 6, Blue 1, Blue 2, Green 3, "artificial color") | 3 each, cap 9 | 9 | C | 1.05 each, 3.15 cap |
| P8 | Red-flag additives | Red 3, titanium dioxide, potassium bromate, BHA, propylparaben | 3 each, cap 6 | 6 | C | 1.05 each, 2.1 cap |
| P9 | Emulsifiers | CMC/cellulose gum, polysorbate 80, carrageenan (2 each); mono- and diglycerides, DATEM (1 each) | cap 6 | 6 | C | 2.1 |
| P10 | Non-sugar sweeteners | sucralose, aspartame, acesulfame K, saccharin | 2 each, cap 4 | 4 | C | 1.4 |
| P11 | Refined seed oils | share of calories from items where soybean/canola/corn/cottonseed/sunflower oil is a top-3 ingredient, or that are fried | 4 x share | 4 | D | 0.6 |
| P12 | High glycemic load | g of refined-grain and sugary carbs above 45 g | 1 per 15 g, cap 5 | 5 | C | 1.75 |
| P13 | Dairy and acne | cups of milk or yogurt (cheese and cottage cheese count half) | 0.8 per cup, cap 2 | 2 | C | 0.7 |
| P14 | Phosphate additives | items with added phosphates | 0.5 each, cap 2 | 2 | D | 0.3 |
| P15 | Cosmetic colorants | caramel color | 1 per item, cap 2 | 2 | D | 0.3 |
| P16 | "Bloat" sodium spike | mg above 1,500 in one sitting | 1 per 300 mg, cap 3 | 3 | D | 0.45 |
| R1 | Recognizable meal | the items add up to a plate, bowl, salad, sandwich, pasta, pizza, breakfast plate or yogurt bowl | on/off | +4 | (practical) | +4 |
| R2 | Chef pairing | the carb, and separately the vegetable, come from the main protein's own station | per part | +2 each | (practical) | +4 |
| R3 | Extra stations | stations beyond one and a half (salad bar, hummus bar, fruit and drinks count half; extras count half) | per station | -2.5 each | (practical) | - |
| R4 | Clashes | unrelated starches (-1.5), proteins from two hot lines (-1.5), tofu with meat (-1.5), a yogurt or oatmeal base with beans, rice, meat or raw veg (-8, effectively ruled out) | per clash | - | (practical) | - |
| R5 | Simplicity | more than four foods | -0.5 each | - | (practical) | - |

The sections below justify each row.

### 3.3 Protein amount, distribution and timing (F1, B2): grade A

- Protein supplementation increases gains in muscle size and strength with training, with no further benefit past about 1.6 g/kg/day on average; the upper confidence bound is 2.2 g/kg [Morton 2018].
- Per meal: 0.4 g/kg across at least four meals reaches a 1.6 g/kg minimum; up to 0.55 g/kg per meal for 2.2 g/kg [Schoenfeld & Aragon 2018]. For 75 kg that's 30 g minimum, 40+ g for the main meals.
- There's no hard per-meal ceiling: 100 g produced a bigger and longer response than 25 g [Trommelen 2023]. So F1 only trims points past 130% of target (1 point per extra 10%), and only because a big protein surplus crowds out the carbs you asked for. In testing, without that trim the daily plan drifted to 215 g protein and 320 g carbs; with it, about 190 g and 360 g.
- Pre-sleep protein: 27.5 g of casein nightly for 12 weeks increased muscle and strength gains versus placebo [Snijders 2015]. Cottage cheese, Greek yogurt and milk are the slow-digesting options on the line, hence bonus B2 for the late-night slot.

### 3.4 Protein quality (Q6): grade B

Plant proteins score lower on digestibility and essential amino acids (the FAO DIAAS method [FAO 2013]) and produce a smaller acute muscle-building response per gram [van Vliet 2015]. But when total protein is high the long-run difference shrinks or disappears: soy vs animal supplements produced the same strength and lean-mass gains [Messina 2018], and vegans eating 1.6 g/kg gained muscle like protein-matched omnivores [Hevia-Larraín 2021]. So quality is a small term (1.95 points). Proxy scores: meat, fish, eggs, dairy 1.0; soy 0.9; pea/other legumes 0.7; grains 0.55.

### 3.5 Calories (F2) and carbohydrate amount and quality (F3, Q7, P12)

- Calories are a target, not a quality factor. Too few and you don't recover or grow; too many and the "slight surplus" becomes a bulk.
- Carbs are scored against target (F3), then on where they come from (Q7). Whole grains (dose-response reductions in cardiovascular disease, cancer and all-cause mortality [Aune 2016]), legumes, fruit, vegetables, potatoes and oats count as quality carbs; refined grains and sugars don't.
- Refined, high-glycemic-load meals get a small C-grade penalty (P12). Two small RCTs in young men found low-glycemic-load diets reduced acne lesions [Smith 2007; Kwon 2012]. Real, but small and short, hence C.

### 3.6 Fiber (Q1) and fruit and vegetables (Q2): grade A

- Fiber: the highest fiber eaters had 15 to 30% lower all-cause and cardiovascular mortality, coronary heart disease, stroke, type 2 diabetes and colorectal cancer than the lowest; dose-response curves say 25 to 29 g/day is adequate and more may be better [Reynolds 2019].
- Fruit and vegetables: dose-response benefits up to about 800 g/day [Aune 2017].
- Skin (the looksmaxxing angle, with actual data): increasing fruit and vegetable intake visibly shifted skin toward yellow/red within 6 weeks, and those carotenoid-driven color changes are rated as healthier and more attractive [Whitehead 2012; Stephen 2011]. That's one more reason produce is weighted heavily.
- Produce is measured in estimated cups (1 cup of cooked vegetables or fruit = 1; raw leafy greens count half), since the feed has no gram weights.

### 3.7 Micronutrients (Q4 measured, Q5 estimated)

- **Measured (Q4, grade B):** potassium (AI 3,400 mg; higher intake lowers blood pressure [Aburto 2013] and offsets sodium's effects), calcium (1,000 mg), iron (8 mg) and vitamin D (15 mcg). Vitamin D insufficiency is common in athletes and matters for bone, muscle and immune function [Owens 2018].
- **Estimated (Q5, grade C because they're estimates):** magnesium (400 mg), zinc (11 mg), vitamin C (90 mg), vitamin A (900 mcg RAE, carotenoids) and EPA+DHA (500 mg). Estimated from a table of USDA FoodData Central values for ~50 whole foods (salmon, beef, spinach, black beans, peppers...) matched by name and scaled by the serving. The page labels these "est.".
- Why these nutrients, in gym terms: zinc deficiency lowers testosterone and repletion restores it, but extra zinc doesn't raise normal levels [Prasad 1996]. Vitamin D raised testosterone in deficient men in one trial [Pilz 2011] and did nothing in a larger, better trial [Lerchbaum 2019]. So these are scored as "don't be deficient", never as testosterone boosters. Vitamin C is required for collagen synthesis and is concentrated in skin [Pullar 2017].

### 3.8 Added sugar (P1): grade A

WHO recommends under 10% of energy from free sugars, ideally under 5% [WHO 2015]; the 2025-2030 Dietary Guidelines set 10 g per meal [DGA 2025]. HeelFuel uses the per-meal number as a free allowance, so **1 g, or even 9 g, of added sugar costs nothing**. Above 10 g it costs 0.35 points per gram (25 g of added sugar = -5.25). When the label has no added-sugar row, it's estimated from the ingredients: if a sugar-type ingredient (sugar, syrups, honey, dextrose, fruit juice concentrate...) is listed, 75% of total sugar is assumed added; otherwise zero. 100% fruit juice counts as free sugar, as WHO defines it.

### 3.9 Sodium and water retention (P2, P16): grade B for sodium, D for "bloat"

- Sodium: the 2,300 mg/day chronic disease risk reduction intake [NASEM 2019] is for the general public. Sweat sodium in athletes runs about 20 to 80 mmol/L [Baker 2017], so a lifter who sweats can reasonably eat more. The penalty starts above the meal's share of 3,000 mg (+200 mg grace) and costs up to 5.2 points.
- "Bloat" and puffiness: in controlled experiments, extra salt raises plasma volume, and the textbook model says extracellular water rises with it, but at least one careful balance study found sodium retained without the matching fluid [Heer 2000]. The visible "salty face" effect people describe is mostly anecdotal, so the extra single-meal spike term (P16) is grade D and worth at most 0.45 points.

### 3.10 Saturated fat and trans fat (P3, P4)

- Saturated fat (grade B): cutting it reduced combined cardiovascular events by 17% in long-term RCTs (moderate-quality evidence), with bigger cholesterol drops giving bigger benefits [Hooper 2020]. Gym culture is split on this; the penalty only applies above 10% of the meal's calories and caps at 3.25.
- Trans fat (grade A): artificial trans fat is the one fat with no safe intake, and partially hydrogenated oils are still in a few products on the line (chocolate sprinkles, Froot Loops, coffee creamers). Industrial label trans fat costs 3 points per gram; a PHO ingredient costs 2 more. Trans fat that comes from cheese, milk or beef (vaccenic acid) is a different molecule and a dose story, not a no-safe-dose story, so it counts at a tenth: the 1 g of trans fat on Cheddar-Chive Mashed Potatoes is from the cheddar and costs about 0.3 points, not 3.

### 3.11 Ultra-processing (Q3): grade B+

- The strongest single piece of evidence: in an inpatient crossover RCT (two weeks on each diet), people ate about 500 kcal/day more on an ultra-processed diet whose offered meals were matched to the unprocessed diet for calories, energy density, macros, sugar, sodium and fiber, and gained 0.9 kg [Hall 2019]. A 2025 8-week crossover RCT found double the weight loss on minimally processed vs ultra-processed diets that both followed healthy guidelines [Dicken 2025]. An umbrella review found UPF exposure associated with 32 adverse outcomes, with convincing evidence for cardiovascular mortality and type 2 diabetes [Lane 2024].
- Relevance for a lifter in a surplus: UPF makes it easier to overshoot, so the "slight surplus" turns into fat gain.
- How it's measured: NOVA defines ultra-processed foods by ingredients "of no or rare culinary use" (flavors, flavor enhancers, colors, emulsifiers, non-sugar sweeteners, thickeners, glucose syrups, hydrogenated oils, protein isolates) [Monteiro 2019]. Each item gets a 0 to 1 processing score from weighted marker counts in its ingredient text. "Natural flavor" and simple gums count half; three or more full markers is fully ultra-processed. Q3 is the calorie-weighted share of the meal that is not ultra-processed.
- Scratch-cooked dishes are disaggregated the way NOVA studies handle mixed dishes. UNC's recipes list their components in descending order by weight, each with its own sub-ingredients ("CANNED BEAN BLACK [...], WATER, TOMATO, ..., BASE VEGETABLE [maltodextrin, hydrolyzed corn protein, yeast extract, ...]"). Each component is scored on its own markers and weighted by its position (weights 1, 0.6, 0.36... normalized), so a flavor base that is 2% of a pot of black beans makes the dish about 2% ultra-processed, not 100%. A single purchased product (cottage cheese with carrageenan and mono- and diglycerides; a pancake mix) is scored on its own list, where those additives mean exactly what NOVA says they mean.

### 3.12 Synthetic dyes (P7, P8): grade C

- In a double-blind RCT, mixtures of artificial colors plus sodium benzoate increased hyperactivity in 3 and 8/9 year olds [McCann 2007]. California's 2021 assessment concluded synthetic dyes can affect behavior in some children [OEHHA 2021]. The EU requires a warning label on six dyes [EU 1333/2008].
- Evidence in adults is thin, which is why each dye is worth only about 1 point. A great high-protein meal that includes one dyed item still ranks well.
- Regulatory direction: FDA revoked Red 3 in January 2025 (foods must reformulate by January 2027) and in April 2025 asked industry to voluntarily phase out six petroleum-based dyes, with the target now drifting from end-2026 to end-2027 [FDA 2025]. Titanium dioxide is banned in the EU after EFSA said genotoxicity couldn't be ruled out [EFSA 2021]. Potassium bromate and BHA are IARC group 2B possible carcinogens [IARC 1986; IARC 1999], and California banned bromate, propylparaben and Red 3 from 2027 [CA AB 418]. These "red flag" additives get their own small C-grade penalty (P8).
- Found on the UNC line: the Spinach Wrap gets its green from Yellow 5 and Blue 1 (plus Yellow 6); Birthday Cake ice cream has Red 3 and titanium dioxide; sourdough, dinner rolls and hoagie rolls list potassium bromate; pepperoni and several sausages list BHA.

### 3.13 Emulsifiers and other additives (P9, P14, P15): grades C and D

- Emulsifiers (grade C): CMC and polysorbate 80 let gut bacteria encroach on the intestinal lining and promoted low-grade inflammation, metabolic syndrome and colitis in mice [Chassaing 2015]. In an 11-day controlled-feeding RCT in healthy people, CMC reduced microbiota diversity and short-chain fatty acids and increased abdominal discomfort [Chassaing 2022]. In the NutriNet-Santé cohort, higher intakes of celluloses/CMC and mono- and diglycerides were associated with more cardiovascular disease [Sellem 2023], and mono- and diglycerides and carrageenans with more cancer [Sellem 2024]. Human outcome data are observational, so C.
- Phosphate additives (grade D): a real concern in kidney disease, weaker in healthy people [Ritz 2012].
- Caramel color (grade D): purely cosmetic; some classes contain 4-MEI, a Prop 65 listed compound. Tiny penalty, mostly so the page can say "cosmetic".
- Not penalized: lecithin, xanthan/guar gum (no meaningful human harm signal), MSG and "natural flavor" on their own (they only count toward the processing score).

### 3.14 Non-sugar sweeteners (P10): grade C

WHO recommends against non-sugar sweeteners for weight control (a conditional recommendation) [WHO 2023]; NutriNet-Santé associated them with more cardiovascular disease [Debras 2022]; IARC classified aspartame as possibly carcinogenic (2B) in 2023 [Riboli 2023]. Observational, confounded, hence C. On the UNC line they're mostly in diet sodas and hot cocoa, which aren't meal components anyway.

### 3.15 Processed meat (P5): grade B+

IARC classifies processed meat as a group 1 carcinogen: each 50 g/day raises colorectal cancer risk about 18% [Bouvard 2015]. Processed (not unprocessed) red meat is also linked to more coronary heart disease and diabetes [Micha 2010]. The absolute risk from one meal is small, so the penalty is capped at 5.6 points. Deli poultry with added salt and phosphate counts at half weight.

### 3.16 Fried food (P6) and seed oils (P11)

- Fried food (grade B): highest vs lowest fried-food intake is associated with 28% more major cardiovascular events [Qin 2021].
- Seed oils (grade D). This is the big gym/looksmaxxing claim, and it's the one where the evidence points the other way. RCTs that raised linoleic acid did not raise inflammatory markers [Johnson & Fritsche 2012], and higher linoleic acid levels in blood and fat tissue are associated with less cardiovascular disease and mortality across 30 cohorts [Marklund 2019]. The strongest counterpoint is a reanalysis of the 1968-73 Minnesota Coronary Experiment [Ramsden 2016]. So seed oils get a D-grade nudge (max 0.6 points), mainly where they're doing the frying. This matches the fact-check done for Real Food UNC: the defensible argument is whole-food displacement, not "poison".

### 3.17 Inflammation and omega-3 (B1)

EPA and DHA from oily fish partly inhibit several inflammatory pathways [Calder 2017], and a small RCT found omega-3 supplements reduced acne lesions [Jung 2014]. Dietary inflammatory indices [Shivappa 2014] boil down to the same things already scored: fiber, produce, omega-3s up; refined carbs, processed and fried food down. B1 gives up to 2.6 points for about 1 g of estimated EPA+DHA (roughly a 4 oz salmon portion).

### 3.18 Skin, acne and dairy (P12, P13)

- Glycemic load: see 3.5 [Smith 2007; Kwon 2012].
- Dairy: a meta-analysis of 78,529 young people found any dairy associated with 25% higher odds of acne (milk 28%, low-fat/skim milk 32%, yogurt 36%, cheese a borderline 22%) [Juhl 2018]. The data are observational, the associations weakened after adjustment, and there was publication bias, so dairy gets a C-grade nudge: 0.28 points per cup of milk or yogurt, half that for cottage cheese and cheese, capped at 0.7. Greek yogurt and cottage cheese are still some of the best protein on the line, and that tiny penalty never outweighs them.

### 3.19 Claims checked and deliberately not scored

- **"Soy lowers testosterone"**: a meta-analysis of clinical studies found no effect of soy or isoflavones on testosterone, free testosterone or estrogen in men [Reed 2021]. Tofu and edamame are not penalized.
- **"Low-fat diets tank testosterone"**: partly true. Across 6 intervention studies (206 men), low-fat diets produced small but significant drops in total and free testosterone versus higher-fat diets (standardized mean difference about -0.38) [Whittaker & Wu 2021; a corrigendum was issued in 2026]. Handled by the fat floor in F4, not by rewarding extra fat.
- **General bloating from beans and cruciferous vegetables**: FODMAPs matter clinically in IBS [Gibson & Shepherd 2010], but for everyone else the fiber and micronutrient benefits win, so there's no penalty. If beans bother you, that's a personal filter for later.
- **Meal timing myths** (eating late makes you fat): no. Total intake matters; the late-night slot exists and is rewarded for protein. Sleep effects of heavy late meals are weakly supported [St-Onge 2016].

---

## 4. Holistic, not absolutist

1. **Nothing is excluded for an additive or a gram of sugar.** The only items left out of recommendations are (a) rows whose nutrition data is implausible (section 5.4), and (b) things that aren't meal components: condiments and sauces, desserts, candy and ice cream toppings, soda and juice. Cereal is only considered at breakfast.
2. **Penalties scale with dose.** 1 g of added sugar costs 0, and so does 9 g; 25 g costs 5.25 raw points. 1,200 mg of sodium at lunch costs almost nothing; 2,400 mg costs about 4.
3. **Penalties scale with evidence.** One synthetic dye costs 1.05 raw points (1.1 on the 100-point scale). Missing 40% of the protein target costs about 15. So "has Yellow 5 but best protein option" wins, as it should.
4. **Caps stop any one flaw from dominating.** Even the strongest penalty (added sugar) is capped at 10 points.
5. **The page says what cost points.** Every recommendation lists its tradeoffs ("Sodium 1,690 mg, 73% of the 2,300 mg daily reference", "Yellow 5 + Blue 1 in Spinach Wrap") so you can make your own call.

### 4.1 Worked examples (real menus, Monday 2026-09-28)

| Meal | kcal | Protein | Notable | Score |
|---|---|---|---|---|
| Chase lunch, Simply Prepared: 2x Chicken Shawarma, 3x Saffron Rice, 2x Roasted Cauliflower, 2x Green Beans, skim milk | 880 | 72 g | Fit 60/60, quality 29.4/31.25, chef plate +8, dairy nudge -0.28 | 100 (102 uncapped) |
| Lenoir lunch: 2x Halal Honey BBQ Chicken, 2x Cheddar-Chive Mashed Potatoes, 2x Sauteed Kale & Brussels Sprouts | 940 | 78 g | 24 g added sugar from the BBQ sauce: -4.9. Still a strong pick, flagged on the page | 93 |
| Lenoir dinner: 2x Cajun Chicken, 2x Potato Hash, 2x Sauteed Spinach | 900 | 64 g | 2,540 mg sodium: -4.4, plus -0.45 "bloat" | 91 |
| The shawarma plate with one scoop of rice swapped for the Spinach Wrap | 1,090 | 78 g | Yellow 5, Yellow 6 and Blue 1 (-3.15, the dye cap), CMC and mono- and diglycerides (-1.05), +830 mg sodium, and a second station | 88 |
| Chase late lunch: Classic Cheeseburger + Shoestring Fries | 830 | 28 g | Protein at half the target, 3,230 mg sodium, fried, 4 g fiber | 46 |
| Chase lunch: 2 slices IP3 Pepperoni Pizza | 500 | 24 g | Half the protein and calories, processed meat, BHA in the pepperoni | 36 |

The dyed wrap costs a few points, the sugary sauce costs about five, and a meal that simply doesn't deliver protein costs forty. That ordering is the point.

---

## 5. Building meals

### 5.1 Item roles

Each item gets one role from its name, station and macros:

| Role | Examples | Used as |
|---|---|---|
| protein | grilled chicken, tilapia, tofu, eggs, Greek yogurt, cottage cheese, deli turkey | the meal's anchor, 1 to 2 kinds. At lunch and dinner, Greek yogurt and cottage cheese count as a side instead |
| carb | rice, potatoes, pasta, oatmeal, bread, wraps, beans, quinoa, cereal (breakfast only) | 0 to 2 kinds |
| produce | vegetables, salad greens, fruit | 0 to 2 kinds, 3 when they come from the protein's own station, plus a fruit |
| extra | milk, cheese, guacamole, hummus, nuts and seeds, a pasta sauce | 0 to 1 |
| mixed | burgers, sandwiches, pizza, pasta bakes, burrito bowls | anchor if it brings real protein, otherwise a carb |
| excluded | condiments, desserts, candy, snack chips, soda/juice, flagged data | never recommended; condiments come back as flavor suggestions |

Portion caps: protein 2 servings (3 for lean portions of 130 kcal or less, 1 for a 450 kcal+ entree or a sandwich); carbs 2 (3 for small scoops of 110 kcal or less, 2 for bread and beans, 1 for a cup or more of beans); vegetables 2 (1 for raw toppings and for servings of 1.5 cups or more); extras 1.

### 5.2 Search

For each hall and period the optimizer builds a pool of the 10 most protein-dense proteins plus the 4 biggest, 8 carbs, 8 produce items (including 2 fruits) and 6 extras. Each protein also brings along the carbs and vegetables from its own station, so a chef's plate (shawarma, saffron rice, roasted cauliflower) is always reachable even when a salad-bar item looks better on paper. Meals are built in stages: every protein core (one or two proteins with servings), then carb options, then produce options, then an optional extra. After each stage it keeps the best 5 (then 3) partial meals per core plus that core's 2 best own-station pairings. That's 20,000 to 60,000 full meal scores per period, 1 to 5 seconds. The top three must have different main proteins and mostly different plates, so you get three real alternatives instead of one meal with three vegetable swaps.

### 5.3 Realism rules

Hard rules: at most 5 foods plus one extra; breakfast foods (cereal, oatmeal, grits, waffles, pancakes, French toast, granola, biscuits) only at breakfast and late night; no bread next to something that's already a sandwich or burger, and only one bread; one soup; pasta sauce only with pasta; never the same base food twice (two black-bean dishes or two diced chickens is one food, not variety).

Scored rules (R1 to R5 in the table): +4 when the meal is a recognizable format, +2 for each part that comes from the main protein's own station, -2.5 per extra hot station (the salad bar, fruit and drinks count half), -1.5 for unrelated starches, proteins from two hot lines or tofu next to meat, -8 for a yogurt or oatmeal base next to beans, rice, meat or raw vegetables, and -0.5 per food beyond four.

### 5.4 Data plausibility rules

An item is flagged, excluded, and listed at the bottom of the page when any of these hold:

- More than 1,500 kcal in one serving.
- More than 130 kcal per tablespoon (pure oil is about 120).
- A cheese slice over 400 kcal.
- Stated calories and 4P + 4C + 9F disagree by more than 50% (for items over 60 kcal).
- Protein supplies more than 110% of the stated calories.
- A non-starchy vegetable with more than 30 g carbs or 500 kcal per cup (catches "Baby Carrots, ½ cup: 170 kcal").
- Zero calories on bread, pasta, rice or a protein.

Label fields that contradict each other are clamped rather than excluded: saturated or trans fat above total fat, fiber above total carbs, added sugar above total carbs ("Roasted Harissa Carrots: 0 g fat, 27 g saturated fat" becomes 0 g). When the added-sugar row is missing, added sugar is estimated from the ingredient list (section 3.8) and the page says it's an estimate.

### 5.5 Flavor ideas

The "make it tasty" line only suggests condiments actually on the line that period, with 45 kcal or less, 4 g added sugar or less, and no dyes, matched to the meal: pico, salsa verde or guacamole for bowls, tzatziki for Mediterranean plates, sriracha for tofu, vinegar-based dressing for salads, mustard instead of mayo for sandwiches, hot sauce or salsa for eggs.

---

## 6. Limitations

- The nutrition labels are the dining program's recipe calculations, not lab measurements, and the portion on your plate depends on who's serving.
- Magnesium, zinc, vitamin C, vitamin A and omega-3s are estimates.
- Ingredient text can't tell you how much of an additive is present, only that it is. Dose scaling for additives therefore uses servings of the item, not milligrams.
- The targets describe a reference lifter. A 60 kg or 100 kg lifter needs different numbers (they live in `heelfuel/config.py`).
- Nothing here is medical advice, and allergy handling is not personalized yet: always check the allergen list on the line.

---

## References

- [Aburto 2013] Aburto NJ, Hanson S, Gutierrez H, et al. Effect of increased potassium intake on cardiovascular risk factors and disease: systematic review and meta-analyses. BMJ. 2013;346:f1378. doi:10.1136/bmj.f1378
- [Aune 2016] Aune D, Keum N, Giovannucci E, et al. Whole grain consumption and risk of cardiovascular disease, cancer, and all cause and cause specific mortality. BMJ. 2016;353:i2716. doi:10.1136/bmj.i2716
- [Aune 2017] Aune D, Giovannucci E, Boffetta P, et al. Fruit and vegetable intake and the risk of cardiovascular disease, total cancer and all-cause mortality. Int J Epidemiol. 2017;46(3):1029-1056. doi:10.1093/ije/dyw319
- [Baker 2017] Baker LB. Sweating rate and sweat sodium concentration in athletes: a review of methodology and intra/interindividual variability. Sports Med. 2017;47(Suppl 1):111-128. doi:10.1007/s40279-017-0691-5
- [Bouvard 2015] Bouvard V, Loomis D, Guyton KZ, et al. Carcinogenicity of consumption of red and processed meat. Lancet Oncol. 2015;16(16):1599-1600. doi:10.1016/S1470-2045(15)00444-1
- [CA AB 418] California Food Safety Act, Assembly Bill 418 (2023): bans brominated vegetable oil, potassium bromate, propylparaben and Red 3 in foods sold in California from 2027.
- [Calder 2017] Calder PC. Omega-3 fatty acids and inflammatory processes: from molecules to man. Biochem Soc Trans. 2017;45(5):1105-1115. doi:10.1042/BST20160474
- [Chassaing 2015] Chassaing B, Koren O, Goodrich JK, et al. Dietary emulsifiers impact the mouse gut microbiota promoting colitis and metabolic syndrome. Nature. 2015;519(7541):92-96. doi:10.1038/nature14232
- [Chassaing 2022] Chassaing B, Compher C, Bonhomme B, et al. Randomized controlled-feeding study of dietary emulsifier carboxymethylcellulose reveals detrimental impacts on the gut microbiota and metabolome. Gastroenterology. 2022;162(3):743-756. doi:10.1053/j.gastro.2021.11.006
- [Debras 2022] Debras C, Chazelas E, Sellem L, et al. Artificial sweeteners and risk of cardiovascular diseases: results from the prospective NutriNet-Santé cohort. BMJ. 2022;378:e071204. doi:10.1136/bmj-2022-071204
- [DGA] U.S. Departments of Agriculture and Health and Human Services. Dietary Guidelines for Americans, 2020-2025 (fiber 14 g per 1,000 kcal; sodium; saturated fat).
- [DGA 2025] U.S. Departments of Agriculture and Health and Human Services. Dietary Guidelines for Americans, 2025-2030 (released 2026-01-07): protein 1.2-1.6 g/kg/day; no more than 10 g added sugar per meal; limit highly processed foods; saturated fat under 10% of calories.
- [Dicken 2025] Dicken SJ, Jassil FC, Brown A, et al. Ultraprocessed or minimally processed diets following healthy dietary guidelines on weight and cardiometabolic health: a randomized, crossover trial. Nat Med. 2025;31(10):3297-3308. doi:10.1038/s41591-025-03842-0
- [EFSA 2021] EFSA Panel on Food Additives and Flavourings. Safety assessment of titanium dioxide (E171) as a food additive. EFSA J. 2021;19(5):e06585. doi:10.2903/j.efsa.2021.6585
- [EU 1333/2008] Regulation (EC) No 1333/2008 on food additives, Annex V (warning label for Sunset Yellow, Quinoline Yellow, Carmoisine, Allura Red, Tartrazine, Ponceau 4R).
- [FAO 2013] FAO. Dietary protein quality evaluation in human nutrition. FAO Food and Nutrition Paper 92. 2013.
- [FAO/WHO/UNU 2004] Human energy requirements: report of a joint FAO/WHO/UNU expert consultation. FAO Food and Nutrition Technical Report Series 1. 2004.
- [FDA 2025] U.S. FDA: revocation of FD&C Red No. 3 for foods and ingested drugs (order of 2025-01-15; food compliance date 2027-01-15); HHS/FDA announcement of 2025-04-22 on phasing out petroleum-based synthetic dyes; FDA industry pledge tracker (timeline now end of 2027).
- [Gibson & Shepherd 2010] Gibson PR, Shepherd SJ. Evidence-based dietary management of functional gastrointestinal symptoms: the FODMAP approach. J Gastroenterol Hepatol. 2010;25(2):252-258. doi:10.1111/j.1440-1746.2009.06149.x
- [Hall 2019] Hall KD, Ayuketah A, Brychta R, et al. Ultra-processed diets cause excess calorie intake and weight gain: an inpatient randomized controlled trial of ad libitum food intake. Cell Metab. 2019;30(1):67-77.e3. doi:10.1016/j.cmet.2019.05.008
- [Heer 2000] Heer M, Baisch F, Kropp J, Gerzer R, Drummer C. High dietary sodium chloride consumption may not induce body fluid retention in humans. Am J Physiol Renal Physiol. 2000;278(4):F585-F595. doi:10.1152/ajprenal.2000.278.4.F585
- [Henselmans 2022] Henselmans M, Bjørnsen T, Hedderman R, Vårvik FT. The effect of carbohydrate intake on strength and resistance training performance: a systematic review. Nutrients. 2022;14(4):856. doi:10.3390/nu14040856
- [Hevia-Larraín 2021] Hevia-Larraín V, Gualano B, Longobardi I, et al. High-protein plant-based diet versus a protein-matched omnivorous diet to support resistance training adaptations. Sports Med. 2021;51(6):1317-1330. doi:10.1007/s40279-021-01434-9
- [Hooper 2020] Hooper L, Martin N, Jimoh OF, et al. Reduction in saturated fat intake for cardiovascular disease. Cochrane Database Syst Rev. 2020;8:CD011737. doi:10.1002/14651858.CD011737.pub3
- [IARC 1986] IARC Monographs volume 40 (1986) and Supplement 7 (1987): butylated hydroxyanisole (BHA), group 2B.
- [IARC 1999] IARC Monographs volume 73 (1999): potassium bromate, group 2B.
- [Iraki 2019] Iraki J, Fitschen P, Espinar S, Helms E. Nutrition recommendations for bodybuilders in the off-season: a narrative review. Sports (Basel). 2019;7(7):154. doi:10.3390/sports7070154
- [Jäger 2017] Jäger R, Kerksick CM, Campbell BI, et al. International Society of Sports Nutrition position stand: protein and exercise. J Int Soc Sports Nutr. 2017;14:20. doi:10.1186/s12970-017-0177-8
- [Johnson & Fritsche 2012] Johnson GH, Fritsche K. Effect of dietary linoleic acid on markers of inflammation in healthy persons: a systematic review of randomized controlled trials. J Acad Nutr Diet. 2012;112(7):1029-1041. doi:10.1016/j.jand.2012.03.029
- [Juhl 2018] Juhl CR, Bergholdt HKM, Miller IM, et al. Dairy intake and acne vulgaris: a systematic review and meta-analysis of 78,529 children, adolescents, and young adults. Nutrients. 2018;10(8):1049. doi:10.3390/nu10081049
- [Jung 2014] Jung JY, Kwon HH, Hong JS, et al. Effect of dietary supplementation with omega-3 fatty acid and gamma-linolenic acid on acne vulgaris: a randomised, double-blind, controlled trial. Acta Derm Venereol. 2014;94(5):521-525. doi:10.2340/00015555-1802
- [Kwon 2012] Kwon HH, Yoon JY, Hong JS, et al. Clinical and histological effect of a low glycaemic load diet in treatment of acne vulgaris in Korean patients: a randomized, controlled trial. Acta Derm Venereol. 2012;92(3):241-246. doi:10.2340/00015555-1346
- [Lane 2024] Lane MM, Gamage E, Du S, et al. Ultra-processed food exposure and adverse health outcomes: umbrella review of epidemiological meta-analyses. BMJ. 2024;384:e077310. doi:10.1136/bmj-2023-077310
- [Lerchbaum 2019] Lerchbaum E, Trummer C, Theiler-Schwetz V, et al. Effects of vitamin D supplementation on androgens in men with low testosterone levels: a randomized controlled trial. Eur J Nutr. 2019;58(8):3135-3146. doi:10.1007/s00394-018-1858-z
- [Marklund 2019] Marklund M, Wu JHY, Imamura F, et al. Biomarkers of dietary omega-6 fatty acids and incident cardiovascular disease and mortality. Circulation. 2019;139(21):2422-2436. doi:10.1161/CIRCULATIONAHA.118.038908
- [McCann 2007] McCann D, Barrett A, Cooper A, et al. Food additives and hyperactive behaviour in 3-year-old and 8/9-year-old children in the community: a randomised, double-blinded, placebo-controlled trial. Lancet. 2007;370(9598):1560-1567. doi:10.1016/S0140-6736(07)61306-3
- [Messina 2018] Messina M, Lynch H, Dickinson JM, Reed KE. No difference between the effects of supplementing with soy protein versus animal protein on gains in muscle mass and strength in response to resistance exercise. Int J Sport Nutr Exerc Metab. 2018;28(6):674-685. doi:10.1123/ijsnem.2018-0071
- [Micha 2010] Micha R, Wallace SK, Mozaffarian D. Red and processed meat consumption and risk of incident coronary heart disease, stroke, and diabetes mellitus: a systematic review and meta-analysis. Circulation. 2010;121(21):2271-2283. doi:10.1161/CIRCULATIONAHA.109.924977
- [Mifflin 1990] Mifflin MD, St Jeor ST, Hill LA, et al. A new predictive equation for resting energy expenditure in healthy individuals. Am J Clin Nutr. 1990;51(2):241-247. doi:10.1093/ajcn/51.2.241
- [Monteiro 2019] Monteiro CA, Cannon G, Levy RB, et al. Ultra-processed foods: what they are and how to identify them. Public Health Nutr. 2019;22(5):936-941. doi:10.1017/S1368980018003762
- [Morton 2018] Morton RW, Murphy KT, McKellar SR, et al. A systematic review, meta-analysis and meta-regression of the effect of protein supplementation on resistance training-induced gains in muscle mass and strength in healthy adults. Br J Sports Med. 2018;52(6):376-384. doi:10.1136/bjsports-2017-097608
- [NASEM 2019] National Academies of Sciences, Engineering, and Medicine. Dietary Reference Intakes for Sodium and Potassium. Washington, DC: National Academies Press; 2019. doi:10.17226/25353
- [OEHHA 2021] California Office of Environmental Health Hazard Assessment. Health effects assessment: potential neurobehavioral effects of synthetic food dyes in children. April 2021.
- [Owens 2018] Owens DJ, Allison R, Close GL. Vitamin D and the athlete: current perspectives and new challenges. Sports Med. 2018;48(Suppl 1):3-16. doi:10.1007/s40279-017-0841-9
- [Pilz 2011] Pilz S, Frisch S, Koertke H, et al. Effect of vitamin D supplementation on testosterone levels in men. Horm Metab Res. 2011;43(3):223-225. doi:10.1055/s-0030-1269854
- [Prasad 1996] Prasad AS, Mantzoros CS, Beck FW, et al. Zinc status and serum testosterone levels of healthy adults. Nutrition. 1996;12(5):344-348. doi:10.1016/s0899-9007(96)80058-x
- [Pullar 2017] Pullar JM, Carr AC, Vissers MCM. The roles of vitamin C in skin health. Nutrients. 2017;9(8):866. doi:10.3390/nu9080866
- [Qin 2021] Qin P, Zhang M, Han M, et al. Fried-food consumption and risk of cardiovascular disease and all-cause mortality: a meta-analysis of observational studies. Heart. 2021;107(19):1567-1575. doi:10.1136/heartjnl-2020-317883
- [Ramsden 2016] Ramsden CE, Zamora D, Majchrzak-Hong S, et al. Re-evaluation of the traditional diet-heart hypothesis: analysis of recovered data from Minnesota Coronary Experiment (1968-73). BMJ. 2016;353:i1246. doi:10.1136/bmj.i1246
- [Reed 2021] Reed KE, Camargo J, Hamilton-Reeves J, Kurzer M, Messina M. Neither soy nor isoflavone intake affects male reproductive hormones: an expanded and updated meta-analysis of clinical studies. Reprod Toxicol. 2021;100:60-67. doi:10.1016/j.reprotox.2020.12.019
- [Reynolds 2019] Reynolds A, Mann J, Cummings J, et al. Carbohydrate quality and human health: a series of systematic reviews and meta-analyses. Lancet. 2019;393(10170):434-445. doi:10.1016/S0140-6736(18)31809-9
- [Riboli 2023] Riboli E, Beland FA, Lachenmeier DW, et al. Carcinogenicity of aspartame, methyleugenol, and isoeugenol. Lancet Oncol. 2023;24(8):848-850. doi:10.1016/S1470-2045(23)00341-8
- [Ritz 2012] Ritz E, Hahn K, Ketteler M, Kuhlmann MK, Mann J. Phosphate additives in food: a health risk. Dtsch Arztebl Int. 2012;109(4):49-55. doi:10.3238/arztebl.2012.0049
- [Schoenfeld & Aragon 2018] Schoenfeld BJ, Aragon AA. How much protein can the body use in a single meal for muscle-building? Implications for daily protein distribution. J Int Soc Sports Nutr. 2018;15:10. doi:10.1186/s12970-018-0215-1
- [Sellem 2023] Sellem L, Srour B, Javaux G, et al. Food additive emulsifiers and risk of cardiovascular disease in the NutriNet-Santé cohort: prospective cohort study. BMJ. 2023;382:e076058. doi:10.1136/bmj-2023-076058
- [Sellem 2024] Sellem L, Srour B, Javaux G, et al. Food additive emulsifiers and cancer risk: results from the French prospective NutriNet-Santé cohort. PLoS Med. 2024;21(2):e1004338. doi:10.1371/journal.pmed.1004338
- [Shivappa 2014] Shivappa N, Steck SE, Hurley TG, Hussey JR, Hébert JR. Designing and developing a literature-derived, population-based dietary inflammatory index. Public Health Nutr. 2014;17(8):1689-1696. doi:10.1017/S1368980013002115
- [Slater & Phillips 2011] Slater G, Phillips SM. Nutrition guidelines for strength sports: sprinting, weightlifting, throwing events, and bodybuilding. J Sports Sci. 2011;29(Suppl 1):S67-S77. doi:10.1080/02640414.2011.574722
- [Slater 2019] Slater GJ, Dieter BP, Marsh DJ, et al. Is an energy surplus required to maximize skeletal muscle hypertrophy associated with resistance training? Front Nutr. 2019;6:131. doi:10.3389/fnut.2019.00131
- [Smith 2007] Smith RN, Mann NJ, Braue A, Mäkeläinen H, Varigos GA. A low-glycemic-load diet improves symptoms in acne vulgaris patients: a randomized controlled trial. Am J Clin Nutr. 2007;86(1):107-115. doi:10.1093/ajcn/86.1.107
- [Snijders 2015] Snijders T, Res PT, Smeets JS, et al. Protein ingestion before sleep increases muscle mass and strength gains during prolonged resistance-type exercise training in healthy young men. J Nutr. 2015;145(6):1178-1184. doi:10.3945/jn.114.208371
- [St-Onge 2016] St-Onge MP, Mikic A, Pietrolungo CE. Effects of diet on sleep quality. Adv Nutr. 2016;7(5):938-949. doi:10.3945/an.116.012336
- [Stephen 2011] Stephen ID, Coetzee V, Perrett DI. Carotenoid and melanin pigment coloration affect perceived human health. Evol Hum Behav. 2011;32(3):216-227. doi:10.1016/j.evolhumbehav.2010.09.003
- [Trommelen 2023] Trommelen J, van Lieshout GAA, Nyakayiru J, et al. The anabolic response to protein ingestion during recovery from exercise has no upper limit in magnitude and duration in vivo in humans. Cell Rep Med. 2023;4(12):101324. doi:10.1016/j.xcrm.2023.101324
- [van Vliet 2015] van Vliet S, Burd NA, van Loon LJ. The skeletal muscle anabolic response to plant- versus animal-based protein consumption. J Nutr. 2015;145(9):1981-1991. doi:10.3945/jn.114.204305
- [Whitehead 2012] Whitehead RD, Re D, Xiao D, Ozakinci G, Perrett DI. You are what you eat: within-subject increases in fruit and vegetable consumption confer beneficial skin-color changes. PLoS One. 2012;7(3):e32988. doi:10.1371/journal.pone.0032988
- [WHO 2015] World Health Organization. Guideline: sugars intake for adults and children. Geneva: WHO; 2015.
- [WHO 2023] World Health Organization. Use of non-sugar sweeteners: WHO guideline. Geneva: WHO; 2023.
- [Whittaker & Wu 2021] Whittaker J, Wu K. Low-fat diets and testosterone in men: systematic review and meta-analysis of intervention studies. J Steroid Biochem Mol Biol. 2021;210:105878. doi:10.1016/j.jsbmb.2021.105878 (corrigendum 2026, doi:10.1016/j.jsbmb.2025.106880)
