"""
Pujiverse Films - fast world pipeline
  python fast_pipeline.py bollywood kollywood     # specific industries
  python fast_pipeline.py --group India           # a region group
  python fast_pipeline.py --all                   # everything
Step 1: SPARQL returns only film IDs per year (fast).  Step 2: details via wbgetentities, 50 per call.
Step 3: names of directors/cast/genres/languages resolved in batches and cached in labels.json.
Everything is cached, so you can stop and rerun at any time. Output: out/<slug>.csv
"""
import os, sys, json, time, argparse
import requests, pandas as pd
from industries import I

UA = {"User-Agent": "PujiverseFilmDB/0.3 (https://pujiverse.com)"}
S = requests.Session(); S.headers.update(UA)
EXTRA = {"russia": ["Q15180"], "czechia": ["Q33946"], "germany": ["Q713750", "Q16957", "Q41304", "Q7318"], "china": ["Q13426199"]}
TYPES = {"Q11424": "movie", "Q24862": "short", "Q202866": "animated", "Q29168811": "animated", "Q506240": "tv_film", "Q93204": "documentary"}
for d in ("cache", "out", "ents"): os.makedirs(d, exist_ok=True)
LABELS_F = "labels.json"
LABELS = json.load(open(LABELS_F)) if os.path.exists(LABELS_F) else {}

def save_json(obj, path):          # atomic: never leaves a half-written file
    tmp = path + ".tmp"
    with open(tmp, "w") as f: json.dump(obj, f)
    os.replace(tmp, path)

def sparql(q, tries=6):
    for i in range(tries):
        try:
            r = S.get("https://query.wikidata.org/sparql", params={"query": q, "format": "json"}, timeout=70)
            if r.status_code == 200: return [b["film"]["value"].rsplit("/", 1)[-1] for b in r.json()["results"]["bindings"]]
            time.sleep(20 * (i + 1) if r.status_code == 429 else 5 * (i + 1))
        except requests.RequestException: time.sleep(5 * (i + 1))
    return None

def filt(slug):
    _, _, typ, q, _, ctry = I[slug]
    if typ == "lang":
        f = f"?film wdt:P364 wd:{q}."
        return f + (f" ?film wdt:P495 wd:{ctry}." if ctry else "")
    cs = [q] + EXTRA.get(slug, [])
    return "?film wdt:P495 ?c. VALUES ?c { " + " ".join("wd:" + c for c in cs) + " }"

def ids_for(slug, a, b):
    key = f"cache/ids_{slug}_{a}_{b}.json"
    if os.path.exists(key): return json.load(open(key))
    tf = "VALUES ?ft { " + " ".join("wd:" + t for t in TYPES) + " } ?film wdt:P31 ?ft."
    if a == "all":
        q = f"SELECT DISTINCT ?film WHERE {{ {tf} {filt(slug)} }}"
    elif a is None:
        q = f"SELECT DISTINCT ?film WHERE {{ {tf} {filt(slug)} FILTER NOT EXISTS {{ ?film wdt:P577 [] }} }}"
    else:
        q = (f'SELECT DISTINCT ?film WHERE {{ {tf} {filt(slug)} ?film wdt:P577 ?d. '
             f'FILTER(?d >= "{a}-01-01T00:00:00Z"^^xsd:dateTime && ?d < "{b+1}-01-01T00:00:00Z"^^xsd:dateTime) }}')
    big = a == "all" or (a is not None and b > a)
    res = sparql(q, tries=2 if big else 6)
    if res is None and a == "all":
        res = []
        for y in range(1880, 2031, 10): res += ids_for(slug, y, y + 9)
        res += ids_for(slug, None, None)
    elif res is None and a is not None and b > a:
        m = (a + b) // 2; res = ids_for(slug, a, m) + ids_for(slug, m + 1, b)
    if res is None: res = []; print(f"  ! {slug} {a}-{b} failed", flush=True)
    else: save_json(res, key)
    return res

def get_entities(ids, props="labels|claims", langs="en"):
    out = {}
    for i in range(0, len(ids), 50):
        chunk = ids[i:i + 50]
        for t in range(5):
            try:
                r = S.get("https://www.wikidata.org/w/api.php", timeout=60, params={
                    "action": "wbgetentities", "ids": "|".join(chunk), "props": props, "languages": langs, "format": "json"})
                if r.status_code == 200: out.update(r.json().get("entities", {})); break
            except requests.RequestException: pass
            time.sleep(3 * (t + 1))
    return out

def claim_ids(c, p, limit=None):
    vals = []
    for s in c.get(p, []):
        dv = s.get("mainsnak", {}).get("datavalue", {})
        if dv.get("type") == "wikibase-entityid": vals.append(dv["value"]["id"])
    return vals[:limit] if limit else vals

def claim_str(c, p):
    for s in c.get(p, []):
        dv = s.get("mainsnak", {}).get("datavalue", {})
        if dv.get("type") == "string": return dv["value"]
        if dv.get("type") == "monolingualtext": return dv["value"]["text"]
        if dv.get("type") == "quantity": return dv["value"]["amount"]
    return None

def best_date(c):
    best = None
    for s in c.get("P577", []):
        dv = s.get("mainsnak", {}).get("datavalue", {})
        if dv.get("type") != "time": continue
        t, prec = dv["value"]["time"], dv["value"]["precision"]
        if t.startswith("-"): continue
        y = int(t[1:5]); d = t[1:11] if prec >= 11 else None
        if best is None or y < best[0] or (y == best[0] and d and (not best[1] or d < best[1])): best = (y, d)
    return best or (None, None)

def resolve_labels(qids):
    need = [q for q in set(qids) if q not in LABELS]
    for i in range(0, len(need), 500):
        ents = get_entities(need[i:i + 500], props="labels", langs="en|mul")
        for q, e in ents.items():
            lab = e.get("labels", {})
            l = (lab.get("en") or lab.get("mul") or {}).get("value")
            LABELS[q] = l
        save_json(LABELS, LABELS_F)

def pull(slug, expected=0):
    if expected <= 15000:
        ids = ids_for(slug, "all", "all")            # one query for the whole industry
    else:
        ids = []
        for a in range(1880, 2031, 10): ids += ids_for(slug, a, a + 9)   # decades, auto-split if slow
        ids += ids_for(slug, None, None)
    ids = list(dict.fromkeys(ids))
    ent_f = f"ents/{slug}.json"
    ents = json.load(open(ent_f)) if os.path.exists(ent_f) else {}
    missing = [q for q in ids if q not in ents]
    local = I[slug][4] or ""
    langs = "en|mul" + ("|" + local if local and len(local) == 2 else "")
    if missing:
        for i in range(0, len(missing), 1000):
            got = get_entities(missing[i:i + 1000], langs=langs)
            for q, e in got.items():   # keep only what we need, small cache
                c = e.get("claims", {})
                lab = e.get("labels", {})
                ents[q] = {"en": (lab.get("en") or lab.get("mul") or {}).get("value"), "local": lab.get(local, {}).get("value") if local else None,
                           "orig": claim_str(c, "P1476"), "date": best_date(c), "runtime": claim_str(c, "P2047"),
                           "types": claim_ids(c, "P31"), "genre": claim_ids(c, "P136", 4), "dir": claim_ids(c, "P57", 3),
                           "cast": claim_ids(c, "P161", 15), "lang": claim_ids(c, "P364", 3),
                           "imdb": claim_str(c, "P345"), "tmdb": claim_str(c, "P4947")}
            save_json(ents, ent_f)
    ref = [x for e in ents.values() for k in ("genre", "dir", "cast", "lang") for x in e[k]]
    resolve_labels(ref)
    L = lambda qs: ", ".join(l for l in (LABELS.get(q) for q in qs) if l) or None
    rows = []
    for q in ids:
        e = ents.get(q)
        if not e: continue
        y, d = e["date"]
        rt = e["runtime"]
        try: rt = round(float(rt)) if rt else None
        except ValueError: rt = None
        rows.append({"title_id": f"{slug}-{q}", "title": e["en"] or e["orig"] or e["local"] or q,
            "title_local": e["local"] if e["local"] and e["local"] != e["en"] else None,
            "original_title": e["orig"], "industry": slug, "language": L(e["lang"]),
            "release_date": d, "year": y, "type": next((TYPES[t] for t in e["types"] if TYPES.get(t, "movie") != "movie"), "movie"),
            "genre": L(e["genre"]), "runtime_min": rt, "director": L(e["dir"]), "cast": L(e["cast"]),
            "imdb_id": e["imdb"], "tmdb_id": e["tmdb"], "wikidata_id": q, "source": "wikidata"})
    df = pd.DataFrame(rows)
    if len(df): df = df.sort_values(["year", "release_date", "title"], na_position="last")
    df.to_csv(f"out/{slug}.csv", index=False)
    return len(df)

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("slugs", nargs="*")
    ap.add_argument("--group"); ap.add_argument("--all", action="store_true")
    a = ap.parse_args()
    counts = json.load(open("counts.json")) if os.path.exists("counts.json") else {}
    slugs = list(I) if a.all else [s for s in I if I[s][1] == a.group] if a.group else a.slugs
    for s in slugs:
        t = time.time(); n = pull(s, counts.get(s, 0))
        print(f"{s}: {n} films ({int(time.time() - t)}s)", flush=True)
