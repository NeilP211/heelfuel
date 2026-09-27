# HeelFuel research notes

Research done 2026-09-26, before any code was written, and revised 2026-09-27 after the first round of feedback. It covers four things:

1. **Where the menu data comes from** and exactly what it contains (and doesn't).
2. **The per-meal targets** for a lifter eating at maintenance to a slight surplus.
3. **The scoring rubric**: every factor, how it's dosed, how much it can move a score, and how strong the evidence behind it is.
4. **How meals are built**: recognizable athlete dishes assembled from every station on the line.

What changed after feedback: the first version planned a whole day and leaned on tofu, quinoa and chickpea salads when they scored well. The brief is athlete food (meat, fish, eggs, dairy, fruit, real carbs), judged one meal at a time, with % Daily Values on show. So v2 drops the daily plan, leaves plant-protein swaps out of the builds, scores each meal on MACROS, MICROS and CLEAN, and builds dishes you'd actually make.

Everything in sections 2 to 5 is implemented in `heelfuel/config.py`, `heelfuel/score.py` and `heelfuel/builds.py`. If a number here and a number in the code ever disagree, the code is what runs, so fix whichever is wrong.

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
- **Impossible micronutrients:** "Salsa, 2 Tbsp: 93 mg iron"; "Seasoned Black Beans, ½ cup: 64 mg iron" (the Daily Value is 18 mg); "Italian Sausage, ½ cup: 61.4 mcg vitamin D" and "Sliced Ham: 13.9 mcg", which only make sense as IU.
- **Impossible fruit:** "Roasted Cinnamon Apples, ¼ cup: 560 kcal, 23 g fiber".

Section 5.5 lists the plausibility rules that catch these rows. Flagged items are left out of recommendations and listed at the bottom of the page, so nothing disappears silently.

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

### 2.2 One meal at a time

The site never adds up a day. You pick the meal you're about to eat and the score says how good that one meal is on its own. The daily numbers above only set the size of a good meal:

| Meal | Calories | Protein for full credit | Carbs | Fat | Fruit and veg | Sodium allowance | Refined carbs allowed | Share of the Daily Value for full micronutrient credit |
|---|---|---|---|---|---|---|---|---|
| Breakfast, continental | 500 to 800 | 35 g | 45 to 100 g | 10 to 30 g | 1 cup | 800 mg | 40 g | 30% |
| Lunch, dinner, brunch, late lunch, late dinner | 600 to 950 | 42 g | 60 to 120 g | 12 to 35 g | 1.5 cups | 1,000 mg | 50 g | a third |
| Late night | 300 to 600 | 28 g | 25 to 70 g | 5 to 22 g | 0.5 cup | 600 mg | 25 g | 20% |

- **Protein:** at least 0.4 g/kg per meal, up to about 0.55 g/kg for the bigger ones [Schoenfeld & Aragon 2018], so 30 to 41 g for a 75 kg lifter; 42 g is the top of that range for lunch and dinner. There's no hard ceiling: 100 g of protein after training produced a larger and longer anabolic response than 25 g [Trommelen 2023]. Late night is sized to the 27.5 g of pre-sleep protein that increased muscle and strength gains over 12 weeks [Snijders 2015].
- **Calories:** a main meal is roughly a third of a 2,800 to 3,200 kcal day, with a wide band on purpose: one meal doesn't have to be exact when you're the one deciding what else you eat.
- **Carbs and fat** follow from the calories, with the fat floor from 2.1.
- **Sodium:** about a third of a 3,000 mg lifter's allowance per main meal (2.1 and 3.9).

---

## 3. Scoring rubric---

## 3. Scoring rubric

### 3.1 How a meal is scored

Every candidate meal (a set of items with servings) gets a score out of 100 in three parts, shown on the page as three bars:

```
score = MACROS (35) + MICROS (35) + CLEAN (30) + dish bonus (up to 3)     (shown capped at 100)
```

- **MACROS (35)** is how well the meal hits its targets from 2.2: protein 18, calories 8, carbs 5, fat 4. These are your stated goals, so they aren't discounted by evidence.
- **MICROS (35)** is 30 points for % Daily Value coverage across ten nutrients plus 5 for fruit and vegetables (3.6 and 3.7).
- **CLEAN (30)** is 15 points for the share of calories that isn't ultra-processed (3.11), plus 15 points minus the dose-scaled penalties (3.8 to 3.18), floored at zero.
- **Dish bonus** is not a health factor: +1 for each item that belongs to the dish (the burrito bowl's pico and beans, the power plate's sides from the protein's own station), capped at 3, so ties go to the build that reads like a real dish. Ranking uses the uncapped number.
- Every penalty is multiplied by an **evidence weight**:

| Grade | Weight | Meaning |
|---|---|---|
| A | 1.00 | Consistent RCTs and/or meta-analyses in humans |
| B+ | 0.80 | Human RCTs plus consistent large cohorts, some uncertainty on size of effect |
| B | 0.65 | Some human RCTs or consistent cohorts plus a plausible mechanism |
| C | 0.35 | Small or short human trials, animal/mechanistic data, or inconsistent cohorts |
| D | 0.15 | Mostly anecdote or community claim (gym/looksmaxxing lore) with little direct evidence |

This is how "factor in the weak claims, but weight them less" is implemented: a D-grade factor can never move a score by more than a point or so.

### 3.2 Every factor at a glance

Effective max = raw points x evidence weight. "Per meal" allowances come from the table in 2.2.

| # | Factor | Measured as | Dose rule | Raw max | Grade | Effective max |
|---|---|---|---|---|---|---|
| M1 | Protein | g vs the meal's target | `(g / target)^1.3` up to full credit; past 160% of target, 10 points per extra 100% (cap 5), because a plate of only chicken crowds out the carbs you asked for | 18 | (target) | 18 |
| M2 | Calories | kcal vs the meal's band | full inside the band, linear to zero 35% of the band's middle outside it | 8 | (target) | 8 |
| M3 | Carbs | g vs band | full inside, `(g / low)^1.2` below, linear taper above | 5 | (target) | 5 |
| M4 | Fat | g vs band | full inside, linear below and above | 4 | (target) | 4 |
| V1 | % Daily Value | fiber, potassium, iron, calcium, vitamin D (label) and magnesium, zinc, vitamin C, vitamin A, EPA+DHA (estimated), each capped at the meal's share of the Daily Value | weighted average; label-measured nutrients weigh more (fiber and potassium 1.0, vitamin C 0.9, iron, magnesium and zinc 0.8, calcium 0.7, vitamins D and A 0.6, EPA+DHA 0.5) | 30 | A to C | 30 |
| V2 | Fruit and vegetables | estimated cups vs 1, 1.5 or 0.5 cups | linear to target | 5 | A | 5 |
| C1 | Minimally processed | calorie share of the meal that isn't ultra-processed (3.11) | linear | 15 | B+ | 15 |
| P1 | Added sugar | g above 10 g per meal | 0.35 per g, cap 10 | 10 | A | 10.0 |
| P2 | Sodium | mg above the meal's allowance (+200 mg grace) | 1 per 200 mg, cap 8 | 8 | B | 5.2 |
| P3 | Saturated fat | g above 10% of the meal's calories | 0.3 per g, cap 5 | 5 | B | 3.25 |
| P4 | Trans fat | label trans fat from industrial sources (partially hydrogenated, hydrogenated or interesterified oils, shortening); dairy and meat trans fat counts at 10% | 3 per g, +2 for PHO, cap 8 | 8 | A | 8.0 |
| P5 | Processed meat | estimated grams of cured/processed meat | 3.5 per 50 g, cap 7 | 7 | B+ | 5.6 |
| P6 | Deep-fried food | share of calories from fried items | 5 x share | 5 | B | 3.25 |
| P7 | Synthetic dyes | distinct certified dyes (Red 40, Yellow 5, Yellow 6, Blue 1, Blue 2, Green 3, "artificial color") | 3 each, cap 9 | 9 | C | 1.05 each, 3.15 cap |
| P8 | Red-flag additives | Red 3, titanium dioxide, potassium bromate, BHA, propylparaben | 3 each, cap 6 | 6 | C | 1.05 each, 2.1 cap |
| P9 | Emulsifiers | CMC/cellulose gum, polysorbate 80, carrageenan (2 each); mono- and diglycerides, DATEM (1 each) | cap 6 | 6 | C | 2.1 |
| P10 | Non-sugar sweeteners | sucralose, aspartame, acesulfame K, saccharin | 2 each, cap 4 | 4 | C | 1.4 |
| P11 | Refined seed oils | share of calories from items where soybean/canola/corn/cottonseed/sunflower oil is a top-3 ingredient, or that are fried | 4 x share | 4 | D | 0.6 |
| P12 | High glycemic load | g of refined-grain and sugary carbs above the meal's allowance | 1 per 15 g, cap 5 | 5 | C | 1.75 |
| P13 | Dairy and acne | cups of milk or yogurt (cheese and cottage cheese count half) | 0.8 per cup, cap 2 | 2 | C | 0.7 |
| P14 | Phosphate additives | items with added phosphates | 0.5 each, cap 2 | 2 | D | 0.3 |
| P15 | Cosmetic colorants | caramel color | 1 per item, cap 2 | 2 | D | 0.3 |
| P16 | "Bloat" sodium spike | mg above 1,500 in one sitting | 1 per 300 mg, cap 3 | 3 | D | 0.45 |

The penalties come out of CLEAN's 15-point base, so a meal can lose at most 15 there however many flaws it stacks up; the whole-food half of CLEAN is separate.

Dropped in v2, because the Daily Value coverage now does their job or the brief changed: the v1 protein-quality and carb-quality terms, the oily-fish and pre-sleep-protein bonuses (omega-3 and late-night protein are now part of V1 and M1), and the realism terms (replaced by building real dishes, section 5).

The sections below justify each row.

### 3.3 Protein amount, distribution and timing (M1): grade A

- Protein supplementation increases gains in muscle size and strength with training, with no further benefit past about 1.6 g/kg/day on average; the upper confidence bound is 2.2 g/kg [Morton 2018].
- Per meal: 0.4 g/kg across at least four meals reaches a 1.6 g/kg minimum; up to 0.55 g/kg per meal for 2.2 g/kg [Schoenfeld & Aragon 2018]. For 75 kg that's 30 g minimum, 40+ g for the main meals, which is where the 35, 42 and 28 g targets in 2.2 come from.
- There's no hard per-meal ceiling: 100 g produced a bigger and longer response than 25 g [Trommelen 2023]. So M1 only trims points past 160% of the target, and only because a plate of nothing but meat crowds out the carbs you asked for.
- Pre-sleep protein: 27.5 g of casein nightly for 12 weeks increased muscle and strength gains versus placebo [Snijders 2015]. Greek yogurt parfaits, cottage cheese and milk show up in the late-night builds for this reason, through the protein target rather than a separate bonus.

### 3.4 Protein sources: meat, fish, eggs and dairy, by request

Builds take their protein from meat, fish, eggs and dairy only; tofu, tempeh, "chik'n", vegan swaps, quinoa, lentils and chickpea salads are left out of every slot. That's a preference call, not an evidence call, and it's worth being honest about: plant proteins score lower on digestibility and essential amino acids (the FAO DIAAS method [FAO 2013]) and produce a smaller acute muscle-building response per gram [van Vliet 2015], but when total protein is high the long-run difference shrinks or disappears: soy vs animal supplements produced the same strength and lean-mass gains [Messina 2018], and vegans eating 1.6 g/kg gained muscle like protein-matched omnivores [Hevia-Larraín 2021]. The brief asked for athlete food, so that's what the builds are.

### 3.5 Calories (M2) and carbohydrate amount and quality (M3, P12)

- Calories are a target, not a quality factor. Too few and you don't recover or grow; too many and the "slight surplus" becomes a bulk.
- Carbs are scored against the meal's band (M3), and where they come from matters through P12 and the whole-food share. Whole grains (dose-response reductions in cardiovascular disease, cancer and all-cause mortality [Aune 2016]), legumes, fruit, vegetables, potatoes and oats count as quality carbs; refined grains and sugars above the meal's allowance cost a little.
- Refined, high-glycemic-load meals get a small C-grade penalty (P12). Two small RCTs in young men found low-glycemic-load diets reduced acne lesions [Smith 2007; Kwon 2012]. Real, but small and short, hence C.

### 3.6 Fiber (V1) and fruit and vegetables (V2): grade A

- Fiber: the highest fiber eaters had 15 to 30% lower all-cause and cardiovascular mortality, coronary heart disease, stroke, type 2 diabetes and colorectal cancer than the lowest; dose-response curves say 25 to 29 g/day is adequate and more may be better [Reynolds 2019].
- Fruit and vegetables: dose-response benefits up to about 800 g/day [Aune 2017].
- Skin (the looksmaxxing angle, with actual data): increasing fruit and vegetable intake visibly shifted skin toward yellow/red within 6 weeks, and those carotenoid-driven color changes are rated as healthier and more attractive [Whitehead 2012; Stephen 2011]. That's one more reason produce is weighted heavily.
- Produce is measured in estimated cups (1 cup of cooked vegetables or fruit = 1; raw leafy greens count half), since the feed has no gram weights.

### 3.7 Micronutrients as % Daily Value (V1)

- **The yardstick is the FDA label's Daily Value**, the same %DV column UNC's own nutrition panel prints: fiber 28 g, potassium 4,700 mg, iron 18 mg, calcium 1,300 mg, vitamin D 20 mcg, magnesium 420 mg, zinc 11 mg, vitamin C 90 mg, vitamin A 900 mcg RAE, protein 50 g [21 CFR 101.9]. EPA+DHA has no Daily Value; many organizations recommend roughly 250 to 500 mg a day [Kris-Etherton 2009], and HeelFuel uses 500 mg and labels it as a target rather than a DV.
- **Per meal, not per day:** a main meal gets full credit for a nutrient at a third of its Daily Value (breakfast 30%, late night 20%), and credit is capped there, so a meal can't coast on 300% of one vitamin. The page shows the real percentage anyway ("Vitamin C 111%") because that's the number you'd want to know.
- **Measured vs estimated:** fiber, potassium, iron, calcium and vitamin D come from UNC's labels. Magnesium, zinc, vitamin C, vitamin A and EPA+DHA aren't on the labels, so they're estimated from a table of USDA FoodData Central values for about 50 whole foods (salmon, beef, spinach, black beans, peppers...) matched by name and scaled by the serving, and marked with an asterisk on the page. Measured nutrients get more weight in the average (3.2).
- Why these nutrients, in gym terms: potassium offsets sodium and lowers blood pressure [Aburto 2013]; vitamin D insufficiency is common in athletes and matters for bone, muscle and immune function [Owens 2018]; zinc deficiency lowers testosterone and repletion restores it, but extra zinc doesn't raise normal levels [Prasad 1996]; vitamin D raised testosterone in deficient men in one trial [Pilz 2011] and did nothing in a larger, better trial [Lerchbaum 2019]. So these are scored as "don't be deficient", never as testosterone boosters. Vitamin C is required for collagen synthesis and is concentrated in skin [Pullar 2017].

### 3.8 Added sugar (P1): grade A

WHO recommends under 10% of energy from free sugars, ideally under 5% [WHO 2015]; the 2025-2030 Dietary Guidelines set 10 g per meal [DGA 2025]. HeelFuel uses the per-meal number as a free allowance, so **1 g, or even 9 g, of added sugar costs nothing**. Above 10 g it costs 0.35 points per gram (25 g of added sugar = -5.25). When the label has no added-sugar row, it's estimated from the ingredients: if a sugar-type ingredient (sugar, syrups, honey, dextrose, fruit juice concentrate...) is listed, 75% of total sugar is assumed added; otherwise zero. 100% fruit juice counts as free sugar, as WHO defines it.

### 3.9 Sodium and water retention (P2, P16): grade B for sodium, D for "bloat"

- Sodium: the 2,300 mg/day chronic disease risk reduction intake [NASEM 2019] is for the general public. Sweat sodium in athletes runs about 20 to 80 mmol/L [Baker 2017], so a lifter who sweats can reasonably eat more. The penalty starts above the meal's share of 3,000 mg (+200 mg grace) and costs up to 5.2 points.
- "Bloat" and puffiness: in controlled experiments, extra salt raises plasma volume, and the textbook model says extracellular water rises with it, but at least one careful balance study found sodium retained without the matching fluid [Heer 2000]. The visible "salty face" effect people describe is mostly anecdotal, so the extra single-meal spike term (P16) is grade D and worth at most 0.45 points.

### 3.10 Saturated fat and trans fat (P3, P4)

- Saturated fat (grade B): cutting it reduced combined cardiovascular events by 17% in long-term RCTs (moderate-quality evidence), with bigger cholesterol drops giving bigger benefits [Hooper 2020]. Gym culture is split on this; the penalty only applies above 10% of the meal's calories and caps at 3.25.
- Trans fat (grade A): artificial trans fat is the one fat with no safe intake, and partially hydrogenated oils are still in a few products on the line (chocolate sprinkles, Froot Loops, coffee creamers). Industrial label trans fat costs 3 points per gram; a PHO ingredient costs 2 more. Trans fat that comes from cheese, milk or beef (vaccenic acid) is a different molecule and a dose story, not a no-safe-dose story, so it counts at a tenth: the 1 g of trans fat on Cheddar-Chive Mashed Potatoes is from the cheddar and costs about 0.3 points, not 3.

### 3.11 Ultra-processing (C1): grade B+

- The strongest single piece of evidence: in an inpatient crossover RCT (two weeks on each diet), people ate about 500 kcal/day more on an ultra-processed diet whose offered meals were matched to the unprocessed diet for calories, energy density, macros, sugar, sodium and fiber, and gained 0.9 kg [Hall 2019]. A 2025 8-week crossover RCT found double the weight loss on minimally processed vs ultra-processed diets that both followed healthy guidelines [Dicken 2025]. An umbrella review found UPF exposure associated with 32 adverse outcomes, with convincing evidence for cardiovascular mortality and type 2 diabetes [Lane 2024].
- Relevance for a lifter in a surplus: UPF makes it easier to overshoot, so the "slight surplus" turns into fat gain.
- How it's measured: NOVA defines ultra-processed foods by ingredients "of no or rare culinary use" (flavors, flavor enhancers, colors, emulsifiers, non-sugar sweeteners, thickeners, glucose syrups, hydrogenated oils, protein isolates) [Monteiro 2019]. Each item gets a 0 to 1 processing score from weighted marker counts in its ingredient text. "Natural flavor" and simple gums count half; three or more full markers is fully ultra-processed. C1 is the calorie-weighted share of the meal that is not ultra-processed.
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

### 3.17 Inflammation and omega-3 (V1)

EPA and DHA from oily fish partly inhibit several inflammatory pathways [Calder 2017], and a small RCT found omega-3 supplements reduced acne lesions [Jung 2014]. Dietary inflammatory indices [Shivappa 2014] boil down to the same things already scored: fiber, produce, omega-3s up; refined carbs, processed and fried food down. EPA+DHA is one of the ten V1 nutrients, so a salmon or shrimp build earns it through MICROS.

### 3.18 Skin, acne and dairy (P12, P13)

- Glycemic load: see 3.5 [Smith 2007; Kwon 2012].
- Dairy: a meta-analysis of 78,529 young people found any dairy associated with 25% higher odds of acne (milk 28%, low-fat/skim milk 32%, yogurt 36%, cheese a borderline 22%) [Juhl 2018]. The data are observational, the associations weakened after adjustment, and there was publication bias, so dairy gets a C-grade nudge: 0.28 points per cup of milk or yogurt, half that for cottage cheese and cheese, capped at 0.7. Greek yogurt and cottage cheese are still some of the best protein on the line, and that tiny penalty never outweighs them.

### 3.19 Claims checked and deliberately not scored

- **"Soy lowers testosterone"**: a meta-analysis of clinical studies found no effect of soy or isoflavones on testosterone, free testosterone or estrogen in men [Reed 2021]. Soy isn't penalized in the score; tofu is left out of the builds only because the brief is meat-and-fruit athlete meals (3.4).
- **"Low-fat diets tank testosterone"**: partly true. Across 6 intervention studies (206 men), low-fat diets produced small but significant drops in total and free testosterone versus higher-fat diets (standardized mean difference about -0.38) [Whittaker & Wu 2021; a corrigendum was issued in 2026]. Handled by the fat floor in F4, not by rewarding extra fat.
- **General bloating from beans and cruciferous vegetables**: FODMAPs matter clinically in IBS [Gibson & Shepherd 2010], but for everyone else the fiber and micronutrient benefits win, so there's no penalty. If beans bother you, that's a personal filter for later.
- **Meal timing myths** (eating late makes you fat): no. Total intake matters; late night gets its own smaller target and is rewarded for protein. Sleep effects of heavy late meals are weakly supported [St-Onge 2016].

---

## 4. Holistic, not absolutist

1. **Nothing is excluded for an additive or a gram of sugar.** What never appears in a build: rows whose nutrition data is implausible (5.5); things that aren't meal components (desserts, candy, ice cream toppings, soda and juice; condiments only appear in their flavor slots, like salsa on a burrito bowl); the Stress Less allergy-friendly pantry, which is there for people who need it; plant-protein swaps (3.4, a preference); and processed meat as the main protein, since the brief asks for low-processed meals. Ham or bacon inside an omelet still counts through P5 instead.
2. **Penalties scale with dose.** 1 g of added sugar costs 0, and so does 9 g; 25 g costs 5.25 raw points. 1,200 mg of sodium at lunch costs almost nothing; 2,400 mg costs about 4.
3. **Penalties scale with evidence.** One synthetic dye costs 1.05 points. Missing half the protein target costs about 10. So "has Yellow 5 but best protein option" still wins, as it should.
4. **Caps stop any one flaw from dominating.** Even the strongest penalty (added sugar) is capped at 10 points, and all of them together can take at most 15.
5. **The page says what cost points.** Every build lists its tradeoffs ("Salty: 2,325 mg sodium (101% of a day); drink water", "Dyes: Yellow 5 in Spinach Wrap") so you can make your own call.

### 4.1 Worked examples (real menus, Monday 2026-09-28)

| Meal | kcal | Protein | Notable | Score |
|---|---|---|---|---|
| Chase lunch, Shrimp and Mushroom Scampi Power Plate: 2x scampi, 2x brown rice, sauteed spinach, steamed broccoli, cantaloupe, skim milk | 915 | 52 g | Every macro in band, 140% of the day's vitamin A and 111% of vitamin C, nothing ultra-processed | 99 |
| Chase lunch: 2x Chicken Shawarma, 2x Saffron Rice, sauteed spinach, roasted cauliflower, hummus | 760 | 62 g | Clean and on target; loses a little on micros without fruit | 93 |
| The same bowl with the Spinach Wrap instead of rice | 880 | 66 g | Yellow 5, Yellow 6 and Blue 1 (the dye cap, -3.15), CMC and mono- and diglycerides (-1.05), +830 mg sodium (-2.5), and a third of the calories now ultra-processed (-5 whole-food points) | 82 |
| Lenoir lunch: 2x Halal Honey BBQ Chicken, 2x Cheddar-Chive Mashed Potatoes, kale and Brussels sprouts, collards | 930 | 78 g | 24 g added sugar from the BBQ sauce (-4.9). Still a strong meal, flagged on the page | 83 |
| Lenoir dinner, Blackened Tilapia Burrito Bowl | 740 | 69 g | 2,325 mg sodium (-3.7, plus -0.4 "bloat"); everything else is excellent | 95 |
| Chase: Classic Cheeseburger + Shoestring Fries | 830 | 28 g | Two-thirds of the protein target, 3,230 mg sodium, fried, 4 g fiber | 53 |
| Chase: 2 slices IP3 Pepperoni Pizza | 500 | 24 g | Half the protein, processed meat, BHA in the pepperoni, almost no micronutrients | 54 |

The dyed wrap costs about ten points, the sugary sauce about five, and a meal that simply doesn't deliver protein or micronutrients costs forty. That ordering is the point.

---

## 5. Building meals

v1 let an optimizer assemble any combination of items, and even with realism terms it produced plates nobody would build. v2 starts from dishes and fills them.

### 5.1 Dishes

Each dish is a list of slots, each with a filter, a count and a serving range. Items can come from any station.

| Dish | Periods | Slots (required in bold) |
|---|---|---|
| Loaded Scramble Plate | breakfast, late night | **eggs**, a carb (potatoes, toast or oats), up to 2 veg that go in eggs, salsa or hot sauce, up to 2 fruits, yogurt or milk |
| Greek Yogurt Power Parfait | breakfast, late night | **yogurt or cottage cheese**, **1 to 2 fruits**, seeds, nuts or granola, eggs or milk on the side |
| Breakfast Burrito | breakfast, late night | **tortilla**, **eggs**, potatoes, up to 2 veg, cheese, salsa, fruit |
| Oatmeal (or Grits) Power Bowl | breakfast, late night | **oats or grits**, **1 to 2 fruits**, **eggs or yogurt**, seeds or nuts, milk |
| Burrito Bowl | lunch, dinner, late night | **rice**, **hot meat that isn't Asian, BBQ, Mediterranean or Italian-seasoned**, beans, **1 to 3 veg**, salsa, guacamole or cheese, fruit |
| Mediterranean or Shawarma Bowl | lunch, dinner, late night | **grilled meat**, **rice, pita or roasted potatoes**, **1 to 3 veg**, tzatziki or hummus, feta, fruit |
| Poke Bowl | lunch, dinner, late night | **rice**, **chicken or seafood**, **2 to 3 raw veg**, a sushi-bar sauce, avocado, fruit |
| Power Plate | lunch, dinner, late night | **a hot entree**, **a starch**, **1 to 2 cooked veg**, fruit, milk |
| Red-sauce Pasta | lunch, dinner, late night | **pasta**, **a tomato or meat sauce**, **meat or fish**, up to 2 veg that go in pasta, parmesan, fruit |
| Power Salad | lunch, dinner, late night | **greens**, **meat**, hard-boiled eggs, **1 to 3 toppings**, a carb so it's a meal, fruit, seeds or nuts, a vinaigrette |
| Wrap, Pita or Sandwich | lunch, dinner, late night | **tortilla, pita or bread**, **meat (doubled when it fits)**, **1 to 3 sandwich veg**, cheese, mustard, hummus or hot sauce, fruit |
| Rice Bowl | lunch, dinner, late night | **rice**, **a saucy hot entree (stir-fry, curry, chili)**, **1 to 2 cooked veg**, sauce, fruit |
| Burger + Sides | lunch, dinner, late night | **a burger**, raw veg for it, fruit instead of fries, milk |

Brunch gets the lunch dishes and the breakfast dishes. The main protein is always meat, fish, eggs or dairy (3.4) and never processed meat (section 4).

### 5.2 Search

For each dish, every slot gets its best few candidates on the line that period (3 to 6, ranked by a quick quality or micronutrient-density score). A beam search fills the slots in order, scoring every partial build with the full rubric and keeping the best 24 (at most 3 per main protein, so different proteins stay alive). That's about 0.03 to 0.4 seconds per period.

### 5.3 Coherence rules

- **Cuisines don't mix.** An item whose name commits it to a cuisine (Mexican: Santa Fe, chipotle, cilantro-lime, enchilada; Asian: teriyaki, Szechuan, curry, sesame; Mediterranean: shawarma, gyro, harissa, tzatziki; Italian: marinara, alfredo, alla vodka, and plain pasta) never shares a build with an item committed to another one. Plain rice, chicken, spinach or fruit goes with anything.
- Taco meat, pulled BBQ or curry doesn't go on sliced bread or a bagel (a tortilla or pita is fine), fish doesn't go in meat sauce, and composed dishes (enchiladas, pasta bakes, soups, shrimp and grits, deli spreads like tuna salad) aren't used as a bowl's protein.
- At most 8 items; never the same base food twice; a bagel is one serving and a sandwich takes two slices of bread; the allergy-friendly pantry is skipped.

### 5.4 Picking the builds for a period

Up to five builds per period, sorted by score. The first pass takes different dishes with different main proteins (eggs and yogurt may repeat). The second pass fills the list with other dishes, but never two of the same dish with the same protein, never more than two of one dish, and never one protein item in more than two builds; a third pass lets a thin late menu reuse a protein a third time. Two builds that share 70% of their items count as the same meal, and nothing more than 12 points below the best build is shown just to fill space.

### 5.5 Data plausibility rules

An item is flagged, excluded, and listed at the bottom of the page when any of these hold:

- More than 1,500 kcal in one serving.
- More than 130 kcal per tablespoon (pure oil is about 120).
- A cheese slice over 400 kcal.
- Stated calories and 4P + 4C + 9F disagree by more than 50% (for items over 60 kcal).
- Protein supplies more than 110% of the stated calories.
- A non-starchy vegetable with more than 30 g carbs or 500 kcal per cup (catches "Baby Carrots, ½ cup: 170 kcal").
- Fruit with more than 60 g carbs or 300 kcal per cup, dried fruit and baked goods aside (catches "Roasted Cinnamon Apples, ¼ cup: 560 kcal").
- Zero calories on bread, pasta, rice or a protein.

Label fields that contradict each other or can't be real are corrected rather than excluded, and the item's nutrition panel says so:

- Saturated or trans fat above total fat, fiber above total carbs, added sugar above total carbs are clamped ("Roasted Harissa Carrots: 0 g fat, 27 g saturated fat" becomes 0 g).
- More than 10 mg of iron in a serving of anything but a fortified cereal is replaced with a typical 1.2 mg per 100 kcal (at most 4 mg): the salsa's 93 mg becomes 0.1 mg.
- More than 5 mcg of vitamin D in a food that doesn't naturally carry it (anything but fish, mushrooms, milk, yogurt or cereal) is read as IU and divided by 40: the ham's 13.9 becomes 0.35 mcg.
- When the added-sugar row is missing, added sugar is estimated from the ingredient list (3.8) and the page says it's an estimate.

---

## 6. Limitations

- The nutrition labels are the dining program's recipe calculations, not lab measurements, and the portion on your plate depends on who's serving.
- Magnesium, zinc, vitamin C, vitamin A and omega-3s are estimates, marked with an asterisk.
- Ingredient text can't tell you how much of an additive is present, only that it is. Dose scaling for additives therefore uses servings of the item, not milligrams.
- A build assumes every item is still out when you get there. Stations run out, and late periods often serve a smaller line.
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
- [21 CFR 101.9] Code of Federal Regulations, Title 21, section 101.9: Nutrition labeling of food. Reference Daily Intakes in (c)(8)(iv) and Daily Reference Values in (c)(9), as revised by FDA's 2016 Nutrition Facts label rule.
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
- [Kris-Etherton 2009] Kris-Etherton PM, Grieger JA, Etherton TD. Dietary reference intakes for DHA and EPA. Prostaglandins Leukot Essent Fatty Acids. 2009;81(2-3):99-104. doi:10.1016/j.plefa.2009.05.011
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
