"""Assemble whole meals from one period's line and pick the best few (RESEARCH.md section 5)."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Iterable, Optional

from . import config as C
from .classify import Food
from .formats import designed_pairing, main_protein, meal_format, plant_meat_mix, protein_mix, sweet_savory_clash
from .score import ZERO, SlotTarget, item_vec, score_vec, vec_add

# Beam widths for the staged search.
KEEP_AFTER_CARBS = 5
KEEP_AFTER_PRODUCE = 3
KEEP_MATES = 2  # always carry each protein's best own-station pairings forward


@dataclass
class Combo:
    items: tuple            # ((Food, servings), ...)
    vec: tuple
    stations: frozenset
    score: float = 0.0

    @property
    def key(self) -> tuple:
        return tuple(sorted((f.rid, s) for f, s in self.items))

    @property
    def rids(self) -> frozenset:
        return frozenset(f.rid for f, _ in self.items)

    def main_protein(self) -> Optional[Food]:
        return main_protein(self.items)


def item_quality(f: Food) -> float:
    """Rough 0-1 quality used only to prune the candidate pools before the real scoring."""
    n = f.nutrition
    kcal = max(n.kcal, 1.0)
    q = 1.0
    q -= 0.45 * f.upf
    q -= min(0.3, 0.03 * f.added_sugar * 100.0 / kcal)
    q -= min(0.25, (n.sodium * 100.0 / kcal) / 1600.0)
    q -= 0.25 if f.processed_meat_g > 0 else 0.0
    q -= 0.15 if f.fried else 0.0
    q -= 0.03 * len(f.dyes) + 0.04 * len(f.red_flags)
    q += min(0.15, 0.05 * n.fiber * 100.0 / kcal)
    return max(0.05, min(1.0, q))


def allowed_in_slot(f: Food, slot: str) -> bool:
    if f.kind == "cereal" and slot != "breakfast":
        return False
    if "breakfast_only" in f.tags and slot not in ("breakfast", "late_night"):
        return False
    return True


def _top(foods: list, key, n: int) -> list:
    return sorted(foods, key=key, reverse=True)[:n]


def build_pools(foods: Iterable[Food], slot: str) -> dict:
    seen: set = set()
    usable = []
    for f in foods:
        if f.rid in seen or not f.usable or not allowed_in_slot(f, slot) or f.nutrition.kcal <= 0 and f.role != "produce":
            continue
        seen.add(f.rid)
        usable.append(f)
    q = {f.rid: item_quality(f) for f in usable}

    # Greek yogurt and cottage cheese anchor breakfast and late night; at lunch and dinner they're a side.
    savory = slot in ("lunch", "dinner")
    proteins = [f for f in usable if f.role == "protein" and not (savory and f.kind == "dairy")]
    by_density = _top(proteins, lambda f: f.nutrition.protein / max(f.nutrition.kcal, 1.0) * 100 * q[f.rid], C.POOL_SIZES["protein"])
    by_amount = _top(proteins, lambda f: f.nutrition.protein * f.max_servings * q[f.rid], 4)
    protein_pool = list(dict.fromkeys(by_density + by_amount))

    carbs = [f for f in usable if f.role == "carb"]

    def carb_key(f: Food) -> float:
        return q[f.rid] * (0.5 + 0.5 * f.carb_quality) * min(1.0, f.nutrition.carbs / 15.0)

    carb_pool, breads = [], 0
    for f in sorted(carbs, key=carb_key, reverse=True):
        if "bread" in f.tags or "pizza" in f.tags:
            if breads >= 3:
                continue
            breads += 1
        carb_pool.append(f)
        if len(carb_pool) >= C.POOL_SIZES["carb"]:
            break

    produce = [f for f in usable if f.role == "produce"]

    def produce_key(f: Food) -> float:
        e = f.est
        density = e.get("vit_c", 0) / 60 + e.get("vit_a", 0) / 300 + e.get("magnesium", 0) / 60
        return q[f.rid] * (f.produce_cups + f.nutrition.fiber / 4.0 + 0.3 * density)

    veg = _top([f for f in produce if f.kind != "fruit"], produce_key, C.POOL_SIZES["produce"] - 2)
    fruit = _top([f for f in produce if f.kind == "fruit"], produce_key, 2)
    produce_pool = veg + fruit
    if len(produce_pool) < C.POOL_SIZES["produce"]:
        rest = [f for f in _top(produce, produce_key, C.POOL_SIZES["produce"]) if f not in produce_pool]
        produce_pool += rest[:C.POOL_SIZES["produce"] - len(produce_pool)]

    extras = [f for f in usable if f.role == "extra" or (savory and f.role == "protein" and f.kind == "dairy")]
    extra_pool, per_kind = [], {}
    for f in sorted(extras, key=lambda f: q[f.rid] * (1.0 + 10.0 * f.nutrition.protein / max(f.nutrition.kcal, 1.0)), reverse=True):
        if per_kind.get(f.kind, 0) >= 2:
            continue
        per_kind[f.kind] = per_kind.get(f.kind, 0) + 1
        extra_pool.append(f)
        if len(extra_pool) >= C.POOL_SIZES["extra"]:
            break
    return {"protein": protein_pool, "carb": carb_pool, "produce": produce_pool, "extra": extra_pool}


# ---------------------------------------------------------------- search state

class _State:
    __slots__ = ("items", "vec", "stations", "n_bread", "sandwich", "n_soup", "grain", "n_mixed", "pasta")

    def __init__(self, items=(), vec=ZERO, stations=frozenset(), n_bread=0, sandwich=False, n_soup=0, grain=False, n_mixed=0,
                 pasta=False):
        self.pasta = pasta
        self.items = items
        self.vec = vec
        self.stations = stations
        self.n_bread = n_bread
        self.sandwich = sandwich
        self.n_soup = n_soup
        self.grain = grain
        self.n_mixed = n_mixed


class _Option:
    __slots__ = ("items", "vec", "stations", "n_bread", "sandwich", "n_soup", "grain", "n_mixed", "rids", "pasta")

    def __init__(self, pairs: tuple, vec_cache: dict):
        self.items = pairs
        self.vec = ZERO
        for f, s in pairs:
            k = (f.rid, s)
            if k not in vec_cache:
                vec_cache[k] = item_vec(f, s)
            self.vec = vec_add(self.vec, vec_cache[k])
        self.stations = frozenset(f.station for f, _ in pairs)
        self.n_bread = sum(1 for f, _ in pairs if "bread" in f.tags or "pizza" in f.tags)
        self.sandwich = any("sandwich" in f.tags for f, _ in pairs)
        self.n_soup = sum(1 for f, _ in pairs if "soup" in f.tags)
        self.grain = any(f.role == "carb" and (f.kind in ("grain", "mixed") or "pasta" in f.tags or "rice" in f.tags) for f, _ in pairs)
        self.n_mixed = sum(1 for f, _ in pairs if f.kind == "mixed")
        self.rids = frozenset(f.rid for f, _ in pairs)
        self.pasta = any("pasta" in f.tags for f, _ in pairs)


def _starch_family(f: Food) -> str:
    if f.kind == "legume":
        return "legume"
    if "bread" in f.tags or "pizza" in f.tags or "sandwich" in f.tags:
        return "bread"
    if "rice" in f.tags:
        return "rice"
    if "pasta" in f.tags:
        return "pasta"
    if "potato" in f.tags or f.kind == "starchy_veg":
        return "potato"
    return "grain"


def realism_points(items: tuple, slot: str = "lunch") -> float:
    """Practical cost of a plate (positive) or bonus (negative). Not a health factor.

    Extra hot stations to visit and starches that don't go together cost points; a meal that adds
    up to something recognizable (a plate, bowl, salad, sandwich...) earns a small bonus.
    """
    weights: dict = {}
    for f, _ in items:
        st = f.station.lower()
        side = any(s in st for s in C.SIDE_STATIONS)
        w = C.SIDE_STATION_WEIGHT if (side or f.role == "extra") else 1.0
        weights[st] = max(weights.get(st, 0.0), w)
    pen = max(0.0, sum(weights.values()) - 1.5) * C.STATION_PTS
    families = {_starch_family(f) for f, _ in items if f.role == "carb"} - {"legume"}
    main = main_protein(items)
    if main is not None and main.role == "protein" and main.nutrition.carbs >= 15:
        for tag in ("pasta", "rice"):
            if tag in main.tags:
                families.add(tag)  # a pasta bake already brings its starch
    if len(families) > 1:
        pen += C.STARCH_CLASH_PTS * (len(families) - 1)
    if sweet_savory_clash(items):
        pen += C.SWEET_SAVORY_PTS
    if protein_mix(items):
        pen += C.PROTEIN_MIX_PTS
    if plant_meat_mix(items):
        pen += C.PROTEIN_MIX_PTS
    foods = sum(1 for f, _ in items if f.role != "extra")
    pen += max(0, foods - 4) * C.EXTRA_FOOD_PTS
    if meal_format(items, slot):
        pen -= C.FORMAT_BONUS
    pen -= C.DESIGNED_PAIR_PTS * designed_pairing(items)
    return pen


_DOUBLE_OK = {"egg", "cheese", "milk", "fruit", "mixed vegetables"}


def _compatible(st: _State, op: _Option) -> bool:
    if op.rids & {f.rid for f, _ in st.items}:
        return False
    have = {(f.role, f.base) for f, _ in st.items if f.base not in _DOUBLE_OK}
    if any((f.role, f.base) in have for f, _ in op.items if f.base not in _DOUBLE_OK):
        return False  # two black-bean dishes or two diced chickens is one food, not variety
    n_bread = st.n_bread + op.n_bread
    if n_bread > 1:
        return False
    if (st.sandwich or op.sandwich) and n_bread > 0:
        return False
    if st.n_soup + op.n_soup > 1 or st.n_mixed + op.n_mixed > 1:
        return False
    for f, _ in op.items:
        if f.kind == "sauce" and not (st.pasta or op.pasta):
            return False
    main_foods = sum(1 for f, _ in st.items if f.role != "extra") + sum(1 for f, _ in op.items if f.role != "extra")
    return main_foods <= C.MAX_FOODS


def _merge(st: _State, op: _Option) -> _State:
    return _State(
        items=st.items + op.items,
        vec=vec_add(st.vec, op.vec),
        stations=st.stations | op.stations,
        n_bread=st.n_bread + op.n_bread,
        sandwich=st.sandwich or op.sandwich,
        n_soup=st.n_soup + op.n_soup,
        grain=st.grain or op.grain,
        n_mixed=st.n_mixed + op.n_mixed,
        pasta=st.pasta or op.pasta,
    )


def _options(pool: list, pairs: bool, cache: dict, max_extra_servings: Optional[int] = None) -> list:
    opts = [_Option((), cache)]
    for f in pool:
        top = f.max_servings if max_extra_servings is None else min(f.max_servings, max_extra_servings)
        for s in range(1, top + 1):
            opts.append(_Option(((f, s),), cache))
    if pairs:
        for a, b in combinations(pool, 2):
            if a.base != b.base or a.base in _DOUBLE_OK:
                opts.append(_Option(((a, 1), (b, 1)), cache))
    return opts


def _protein_cores(pool: list, cache: dict) -> list:
    cores = []
    for f in pool:
        for s in range(1, f.max_servings + 1):
            cores.append(_Option(((f, s),), cache))
    for a, b in combinations(pool, 2):
        if a.base == b.base and a.base not in _DOUBLE_OK:
            continue
        for sa, sb in ((1, 1), (2, 1), (1, 2)):
            if sa <= a.max_servings and sb <= b.max_servings:
                cores.append(_Option(((a, sa), (b, sb)), cache))
    return cores or [_Option((), cache)]


def _station_mates(usable: list, role: str, stations: set, per_station: int = 4) -> dict:
    """Carbs or produce served at the same station as a protein: the chef's own pairings."""
    out: dict = {}
    for f in usable:
        if f.role == role and f.station in stations:
            out.setdefault(f.station, []).append(f)
    return {st: sorted(fs, key=item_quality, reverse=True)[:per_station] for st, fs in out.items()}


def search(foods: Iterable[Food], target: SlotTarget, top_n: int = C.TOP_N) -> list[Combo]:
    foods = list(foods)
    pools = build_pools(foods, target.slot)
    cache: dict = {}
    seen: dict = {}

    usable, rids = [], set()
    for f in foods:
        if f.rid not in rids and f.usable and allowed_in_slot(f, target.slot):
            rids.add(f.rid)
            usable.append(f)
    protein_stations = {f.station for f in pools["protein"]}
    carb_mates = _station_mates(usable, "carb", protein_stations)
    produce_mates = _station_mates(usable, "produce", protein_stations)

    def evaluate(st: _State) -> float:
        key = tuple(sorted((f.rid, s) for f, s in st.items))
        if key in seen:
            return seen[key][0]
        sc = score_vec(st.vec, target, realism_points(st.items, target.slot))
        seen[key] = (sc, st)
        return sc

    def dedupe(opts: list) -> list:
        out, keys = [], set()
        for op in opts:
            k = tuple(sorted((f.rid, s) for f, s in op.items))
            if k not in keys:
                keys.add(k)
                out.append(op)
        return out

    carb_global = _options(pools["carb"], True, cache)
    produce_global = _options(pools["produce"], True, cache)
    carb_by_station = {st: _options(fs, True, cache)[1:] for st, fs in carb_mates.items()}
    fruits = [f for f in pools["produce"] if f.kind == "fruit"][:2]
    produce_by_station = {}
    for st, fs in produce_mates.items():
        mate_sets = [((f, s),) for f in fs for s in range(1, f.max_servings + 1)]
        for a, b in combinations(fs, 2):
            for sa in range(1, a.max_servings + 1):
                for sb in range(1, b.max_servings + 1):
                    mate_sets.append(((a, sa), (b, sb)))
        mate_sets += [tuple((f, 1) for f in trio) for trio in combinations(fs, 3)]
        with_fruit = [ms + ((fr, 1),) for ms in mate_sets for fr in fruits if fr not in {f for f, _ in ms}]
        produce_by_station[st] = [_Option(ms, cache) for ms in mate_sets + with_fruit]
    extra_opts = _options(pools["extra"], False, cache, max_extra_servings=1)

    stage_a = []
    for core in _protein_cores(pools["protein"], cache):
        base = _merge(_State(), core)
        if base.n_bread > 1 or (base.sandwich and base.n_bread):
            continue
        opts = carb_global + [op for st in core.stations for op in carb_by_station.get(st, [])]
        scored = []
        for op in dedupe(opts):
            if _compatible(base, op):
                st = _merge(base, op)
                scored.append((evaluate(st), st, bool(op.items) and op.stations <= core.stations))
        scored.sort(key=lambda x: -x[0])
        keep = scored[:KEEP_AFTER_CARBS] + [x for x in scored[KEEP_AFTER_CARBS:] if x[2]][:KEEP_MATES]
        stage_a.extend(st for _, st, _ in keep)

    stage_b = []
    for base in stage_a:
        core_stations = {f.station for f, _ in base.items if f.role == "protein"}
        opts = produce_global + [op for st in core_stations for op in produce_by_station.get(st, [])]
        scored = []
        for op in dedupe(opts):
            if _compatible(base, op):
                st = _merge(base, op)
                mate = bool(op.items) and any(f.station in core_stations for f, _ in op.items)
                scored.append((evaluate(st), st, mate))
        scored.sort(key=lambda x: -x[0])
        keep = scored[:KEEP_AFTER_PRODUCE] + [x for x in scored[KEEP_AFTER_PRODUCE:] if x[2]][:KEEP_MATES]
        stage_b.extend(st for _, st, _ in keep)

    for base in stage_b:
        for op in extra_opts:
            if op.items and _compatible(base, op):
                evaluate(_merge(base, op))

    ranked = sorted(seen.values(), key=lambda x: -x[0])
    combos = [Combo(items=st.items, vec=st.vec, stations=st.stations, score=sc) for sc, st in ranked if st.items]
    return pick_diverse(combos, top_n)


def _jaccard(a: frozenset, b: frozenset) -> float:
    return len(a & b) / len(a | b) if (a or b) else 1.0


def pick_diverse(ranked: list[Combo], top_n: int) -> list[Combo]:
    """Best first, then each next pick needs a different main protein and a mostly different plate."""
    picks: list[Combo] = []
    for strict in (True, False):
        for c in ranked:
            if len(picks) >= top_n:
                return picks
            if any(c.key == p.key for p in picks):
                continue
            mp = c.main_protein()
            if strict and mp is not None and any(p.main_protein() is not None and p.main_protein().rid == mp.rid for p in picks):
                continue
            limit = 0.5 if strict else 0.8
            if any(_jaccard(c.rids, p.rids) > limit for p in picks):
                continue
            picks.append(c)
    return picks
