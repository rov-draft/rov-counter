"""Build counters.js: for each hero X, the heroes C that counter X, grouped by C's role.

Stars mean HOW HARD C counters X (not how much evidence there is):
  1. QZADD 2026 guide (top-rank player interviews) rates it directly -> use that rating.
     A row "X <- C (k stars)" and a row "C beats X (k skulls)" both count; take the max.
  2. Otherwise rovmeta.com (current patch) names it -> 3 if both heroes' pages agree
     (X "กลัวเจอ" C and C "แข็งใส่" X), else 2. If the older Garena guide (2023-24) also
     rates it, blend in at half weight.
  3. Otherwise only the Garena guide rates it -> its rating, capped at 2 (old meta).
  4. Otherwise only C's own page claims "แข็งใส่" X -> 1.
  5. Otherwise a kit-mechanics estimate (est) -> 1.
  sources/counter_overrides.json wins over all of that (ev "manual"; 0 stars removes the pair).

Lanes (dsl / jungle / mid / adl / roam), not hero classes, group the table:
  main lane = the QZADD 2026 guide the hero has its own row in; if it has rows in several,
  rovmeta's lane if it is one of them, else the lane where QZADD mentions it most;
  no QZADD row -> rovmeta's lane. sources/lane_overrides.json wins over all of that. Alt lanes = other QZADD row lanes, rovmeta's lane, every lane the QZADD Tier List rates it in, and
  lanes where QZADD uses it 2+ times.
  Columns per hero X: "same" = counters that can play X's main lane; then one column per
  other lane, holding counters by their main lane.

Shown per cell: every counter from 1-3 (always), padded with 4-5 up to a minimum of
3 (same lane) / 2 (other lanes) counters.

usage: python3 -I tools/build_counters.py heroes.js .cache/mentions.json .cache/tags.json \
         .cache/rovmeta_lane.json sources/garena/garena_counters.json \
         sources/qzadd/qzadd_counters.json sources/counter_overrides.json \
         sources/qzadd/tierlist_2026-09-13.json counters.js
"""
import json, os, sys

heroes_js, mentions_json, tags_json, rovlane_json, garena_json, qzadd_json, cover_json, tierlist_json, out_js = sys.argv[1:10]
src = open(heroes_js, encoding="utf-8").read()
H = json.loads("[" + src.split("const HEROES = [", 1)[1].rsplit("];", 1)[0] + "]")
BY = {h["slug"]: h for h in H}
M = json.load(open(mentions_json, encoding="utf-8"))
T = json.load(open(tags_json, encoding="utf-8"))
assert set(T) == set(BY), set(BY) ^ set(T)

LANE_TH = {"jungle": "ป่า", "dsl": "ออฟเลน", "mid": "เมจ", "roam": "โรม", "mage": "เมจ",
           "offlane": "ออฟเลน", "carry": "แครี่"}
GUIDES = {}


def load_ratings(path, kind):
    """(x, c) -> (rating, guide id): 'c counters x' at the given strength."""
    out = {}
    def put(x, c, k, gid):
        if k > out.get((x, c), (0, ""))[0]:
            out[(x, c)] = (k, gid)
    for g in json.load(open(path, encoding="utf-8"))["guides"]:
        lane = next((v for k, v in LANE_TH.items() if k in g["id"]), "")
        GUIDES[g["id"]] = {"src": kind, "lane": lane, "date": g["date"], "url": g["url"]}
        for x, row in g["rows"].items():
            if isinstance(row, dict):  # QZADD: counters of x, and heroes x beats
                for c, k in row["counters"]:
                    put(x, c, k, g["id"])
                for victim, k in row["beats"]:
                    put(victim, x, k, g["id"])
            else:
                for c, k in row:
                    put(x, c, k, g["id"])
    return out


QZ = load_ratings(qzadd_json, "QZADD")
MANUAL = {x: v for x, v in json.load(open(cover_json, encoding="utf-8")).items() if not x.startswith("_")}
GA = load_ratings(garena_json, "Garena")

LANES = ["dsl", "jungle", "mid", "adl", "roam"]
GUIDE_LANE = {"qzadd-jungle-2026": "jungle", "qzadd-dsl-2026": "dsl", "qzadd-mid-2026": "mid",
              "qzadd-roam-2026": "roam", "qzadd-carry-2026": "adl"}
FALLBACK_LANE = {"Assassin": "jungle", "Marksman": "adl", "Mage": "mid", "Warrior": "dsl",
                 "Tank": "roam", "Support": "roam"}


OVERRIDE = {k: v for k, v in json.load(open(os.path.join(os.path.dirname(qzadd_json), "..", "lane_overrides.json"),
                                            encoding="utf-8")).items() if not k.startswith("_")}


TL_LANES = {}  # lanes the QZADD Tier List rates each hero in
for _lane, _tiers in json.load(open(tierlist_json, encoding="utf-8"))["lanes"].items():
    for _slugs in _tiers.values():
        for _s in _slugs:
            TL_LANES.setdefault(_s, set()).add(_lane)


def hero_lanes():
    rov = json.load(open(rovlane_json, encoding="utf-8"))
    rows, seen = {}, {}
    for g in json.load(open(qzadd_json, encoding="utf-8"))["guides"]:
        L = GUIDE_LANE[g["id"]]
        for t, r in g["rows"].items():
            rows.setdefault(t, set()).add(L)
            for c, _ in [[t, 0]] + r["counters"] + r["beats"]:
                seen.setdefault(c, {}).setdefault(L, 0)
                seen[c][L] += 1
    out = {}
    for s, h in BY.items():
        r, cnt = rows.get(s, set()), seen.get(s, {})
        rv = rov.get(s) or FALLBACK_LANE[h["role"]]
        if len(r) == 1:
            main = next(iter(r))
        elif r:
            main = rv if rv in r else max(r, key=lambda L: cnt.get(L, 0))
        else:
            main = rv
        alt = (r | {rv} | {L for L, n in cnt.items() if n >= 2} | TL_LANES.get(s, set())) - {main}
        ov = OVERRIDE.get(s)
        if isinstance(ov, dict):  # {"main": lane, "alt": [lanes]} replaces both
            main, alt = ov["main"], set(ov.get("alt", []))
        elif ov:  # a lane name: new main, old main kept as an alt lane
            alt, main = (alt | {main}) - {ov}, ov
        out[s] = {"main": main, "alt": [L for L in LANES if L in alt]}
    return out


HL = hero_lanes()
plays = lambda c, L: HL[c]["main"] == L or L in HL[c]["alt"]
TIER_BONUS = {"S+": 0.6, "S": 0.4, "A": 0.2, "B": 0.0, "C": -0.2}


def mech(c, x):
    """How well C's kit exploits X's kit, with short Thai reasons."""
    a, b = T[c], T[x]
    parts = []
    def add(v, why):
        if v > 0:
            parts.append((v, why))
    add(0.5 * a["cc"] * b["mobility"], "CC ล็อกตัวเคลื่อนที่ไว")
    add(0.4 * a["burst"] * (3 - b["durability"]), "เบิร์สต์ตัวบาง")
    if b["range"] == "ranged" and b["mobility"] <= 1:
        add(0.5 * a["mobility"], "พุ่งเข้าหาตัวยิงไกลที่หนีไม่ได้")
    if b["range"] == "melee" and b["mobility"] <= 1:
        add(0.4 * a["poke"], "โพคระยะไกลใส่ตัวประชิด")
    add(0.6 * a["antitank"] * b["durability"], "ดาเมจเจาะแทงค์")
    add(0.3 * a["escape"] * b["cc"], "หลบ/ล้าง CC ได้")
    add(0.2 * a["durability"] * b["burst"], "ทนเบิร์สต์")
    add(0.2 * a["sustain"] * b["poke"], "ฮีลสู้โพค")
    return sum(v for v, _ in parts), [w for _, w in sorted(parts, reverse=True)[:2]]


RAW = {c: {x: mech(c, x)[0] - 0.5 * mech(x, c)[0] for x in BY if x != c} for c in BY}
MEAN = {c: sum(v.values()) / len(v) for c, v in RAW.items()}
USED = {c: 0 for c in BY}  # estimate picks so far, to stop a few all-round kits filling every row


def est_score(c, x):
    # Matchup-specific edge: how much better C does vs X than vs an average hero.
    return RAW[c][x] - 0.8 * MEAN[c] + TIER_BONUS.get(BY[c]["tier"], 0) - 0.08 * USED[c]


def rate(x, c):
    """-> (star, tier, ev). tier: 0 must-show (rated), 1 one-sided claim, 2 estimate."""
    ev = []
    weak = c in BY[x]["weak"]
    strong = x in BY[c]["strong"]
    text = c in M[x]["faq"] or c in M[x]["weaktxt"]
    if weak: ev.append("weak")
    if strong: ev.append("strong")
    if text: ev.append("text")
    if c in MANUAL.get(x, {}):
        k = MANUAL[x][c]
        return (k, 0, ev + ["manual"]) if k else (0, 3, ev)
    q, g = QZ.get((x, c)), GA.get((x, c))
    if q: ev.append(f"q:{q[1]}:{q[0]}")
    if g: ev.append(f"g:{g[1]}:{g[0]}")
    if q:
        return q[0], 0, ev
    if weak or text:
        base = 3 if (weak and strong) else 2
        star = round((2 * base + g[0]) / 3) if g else base
        return max(1, min(3, star)), 0, ev
    if g:
        return min(g[0], 2), 0, ev
    if strong:
        return 1, 1, ev
    return 1, 2, ev


SRC_RANK = lambda ev: 0 if any(e.startswith("q:") for e in ev) else 1 if any(e in ("weak", "text") for e in ev) else 2

out = {}
for x in BY:
    rec = {}
    xl = HL[x]["main"]
    for col in ["same"] + [L for L in LANES if L != xl]:
        n = 3 if col == "same" else 2
        cands = []
        for c in BY:
            if c == x:
                continue
            if (col == "same") != plays(c, xl) or (col != "same" and HL[c]["main"] != col):
                continue
            star, tier, ev = rate(x, c)
            cands.append({"c": c, "star": star, "tier": tier, "ev": ev, "sc": est_score(c, x)})
        cands.sort(key=lambda d: (d["tier"], -d["star"], SRC_RANK(d["ev"]), -d["sc"]))
        cands = [d for d in cands if d["tier"] < 3]  # tier 3 = removed by hand
        must = [d for d in cands if d["tier"] == 0]
        chosen = must + [d for d in cands if d["tier"] > 0][:max(0, n - len(must))]
        picks = []
        for d in chosen:
            item = {"s": d["c"], "star": d["star"], "ev": d["ev"]}
            if d["tier"] == 2:
                item["est"] = 1
                item["why"] = mech(d["c"], x)[1]
                USED[d["c"]] += 1
            picks.append(item)
        rec[col] = picks
    out[x] = rec

cells = [p for r in out.values() for ps in r.values() for p in ps]
print("counters:", len(cells), "stars", {k: sum(p["star"] == k for p in cells) for k in (3, 2, 1)},
      "| qzadd", sum(any(e.startswith("q:") for e in p["ev"]) for p in cells),
      "| estimates", sum(1 for p in cells if p.get("est")))
with open(out_js, "w", encoding="utf-8") as f:
    f.write("// Generated by tools/build_counters.py — see its docstring for what stars mean.\n")
    f.write("// ev: weak/strong/text = rovmeta.com; q:<guide>:<k> = QZADD 2026; g:<guide>:<k> = Garena 2023-24.\n")
    f.write("const HERO_LANES = " + json.dumps(HL, separators=(",", ":")) + ";\n")
    f.write("const GUIDES = " + json.dumps(GUIDES, ensure_ascii=False) + ";\n")
    f.write("const COUNTERS = " + json.dumps(out, ensure_ascii=False, separators=(",", ":")) + ";\n")
