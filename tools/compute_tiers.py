"""Re-tier heroes by combining several 2026 tier sources into one weighted average.

Ranks: SS(S+, SSS)=0, S=1, A=2, B=3, C=4, D=5 (lower = stronger). Sources and weights:
  QZADD Tier List (Thai ranked, 75 stars - Glorious Ruler): when it rates a hero, its tier
      in the hero's best lane IS the final tier (SSS/SS -> SS, A+/A -> A, B+/B/B- -> B,
      "เฉพาะดราฟต์" draft-only -> B). The weighted mean below only covers unrated heroes.
  rovmeta.com hero tier (patch 1.64, Oct 2026)          weight 2.0
  RoV Pro League stats (rovmeta.com/th/stats)            weight 1.5, only when the hero is
      drafted enough to rate B or better (pros skipping a hero says little about ranked)
      pro score = pick% + ban% + (win% - 50) * 0.6 * min(1, pick% / 8)
      S+ >= 60, S >= 35, A >= 18, B >= 8
  sources/tier_sources.json ranked lists                 weight per source
Final: weighted mean -> S+ < 0.85 <= S < 1.8 <= A < 2.6 <= B < 3.4 <= C.
A hero with its own row in a QZADD 2026 counter guide is at least B (top-rank players
still pick it in that lane). sources/tier_overrides.json wins over everything.

Writes "tier" (final) and keeps "tier_site" (rovmeta's original) in heroes.js.
usage: python3 -I tools/compute_tiers.py heroes.js .cache/pro_stats.json sources/tier_sources.json \
         sources/qzadd/qzadd_counters.json sources/qzadd/tierlist_2026-09-13.json sources/tier_overrides.json
"""
import json, re, sys
from collections import Counter

heroes_js, stats_json, sources_json, qzadd_json, qz_tierlist_json, overrides_json = sys.argv[1:7]
src = open(heroes_js, encoding="utf-8").read()
head, rest = src.split("const HEROES = [", 1)
H = json.loads("[" + rest.rsplit("];", 1)[0] + "]")
P = json.load(open(stats_json, encoding="utf-8"))
S = json.load(open(sources_json, encoding="utf-8"))["sources"]
QZ_ROWS = {t for g in json.load(open(qzadd_json, encoding="utf-8"))["guides"] for t in g["rows"]}

RANK = {"SSS": 0, "SS": 0, "S+": 0, "S": 1, "S/A": 1.5, "A": 2, "draft": 2.5, "B": 3, "C": 4, "D": 5}
norm = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())
NAME = {}
for h in H:
    NAME[norm(h["en"])] = NAME[norm(h["slug"])] = h["slug"]
    if h.get("aka"):  # same hero listed under another name (e.g. Brunhilda = Celica)
        NAME[norm(h["aka"])] = h["slug"]
NAME.update({norm("Ngộ Không"): "wukong", "ngkhng": "wukong"})

votes = {h["slug"]: [] for h in H}  # slug -> [(rank, weight, label)]
best_lane = {}
for lane, tiers in json.load(open(qz_tierlist_json, encoding="utf-8"))["lanes"].items():
    for tier, slugs in tiers.items():
        for slug in slugs:
            best_lane[slug] = min(best_lane.get(slug, 9), RANK[tier])
for slug, r in best_lane.items():
    votes[slug].append((r, 3.0, "qzadd-tierlist"))
OVERRIDE = {k: v for k, v in json.load(open(overrides_json, encoding="utf-8")).items() if not k.startswith("_")}
for s in S:
    for tier, names in s["tiers"].items():
        for n in names:
            slug = NAME.get(norm(n))
            if not slug:
                sys.exit(f"unknown hero name in {s['id']}: {n}")
            votes[slug].append((RANK[tier], s["weight"], s["id"]))


def pro_rank(st):
    score = st["pick"] + st["ban"] + (st["wr"] - 50) * 0.6 * min(1, st["pick"] / 8)
    for r, cut in ((0, 60), (1, 35), (2, 18), (3, 8)):
        if score >= cut:
            return r
    return None


ORDER = ["SS", "S", "A", "B", "C"]
changes = []
for h in H:
    site = h.get("tier_site", h.get("tier"))
    h["tier_site"] = site
    v = list(votes[h["slug"]])
    if site:
        v.append((RANK[site], 2.0, "rovmeta"))
    site = "SS" if site == "S+" else site
    if h["slug"] in P and (pr := pro_rank(P[h["slug"]])) is not None:
        v.append((pr, 1.5, "pro"))
    if not v:
        h["tier"] = None
        continue
    mean = sum(r * w for r, w, _ in v) / sum(w for _, w, _ in v)
    h["tier"] = next(t for t, cut in zip(ORDER, (0.85, 1.8, 2.6, 3.4, 99)) if mean < cut)
    if h["slug"] in best_lane:  # QZADD's Thai ranked list is the authority when it rates the hero
        r = best_lane[h["slug"]]
        h["tier"] = ORDER[3 if r == RANK["draft"] else int(r)]
    if h["tier"] == "C" and h["slug"] in QZ_ROWS:
        h["tier"] = "B"
    h["tier"] = OVERRIDE.get(h["slug"], h["tier"])
    if h["tier"] != site:
        changes.append((h["en"], site, h["tier"], round(mean, 2)))

body = ",\n".join("  " + json.dumps(o, ensure_ascii=False) for o in H)
open(heroes_js, "w", encoding="utf-8").write(head + "const HEROES = [\n" + body + "\n];\n")
print("tiers:", dict(Counter(h["tier"] for h in H)))
print("changed vs rovmeta:", len(changes))
for en, a, b, m in sorted(changes, key=lambda c: (ORDER.index(c[2]) - ORDER.index(c[1] or "C"), c[3])):
    print(f"  {en:12} {a or '-':>2} -> {b:<2} ({m})")
