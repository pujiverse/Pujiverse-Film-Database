"""
"Trending on streaming" for every industry and every language: the most popular titles right now (TMDB popularity)
among those streaming on each major service in that market (Netflix, Prime Video, JioHotstar, ...).
Streaming availability is JustWatch data via TMDB. This is TMDB's popularity ranking, not the services' own top-10 lists.

Writes table platform_trends (scope, scope_key, region, provider, rank, ...), replaced on every run.

  TURSO_URL, TURSO_TOKEN (full access) and TMDB_API_KEY in the environment / .env
  python platform_trends.py
"""
import datetime, argparse
from concurrent.futures import ThreadPoolExecutor
from turso_client import query, execute
from enrich_watch import get, HOME, PMAP
from build_languages import INDUSTRY_LANG, CODES, load_codes

INDIAN = {"bollywood", "tollywood", "kollywood", "mollywood", "sandalwood", "bengali-tollywood", "marathi", "pollywood",
          "dhollywood", "ollywood", "jollywood", "bhojiwood", "chhollywood", "coastalwood", "konkani", "manipuri", "rajasthani", "haryanvi"}
INDIAN_LANGS = {INDUSTRY_LANG[s] for s in INDIAN} | {"Urdu"}
COUNTRY = {**HOME, "hollywood": "US", "canada": "CA", "uk": "GB", "australia": "AU", "cuba": "CU", "iran": "IR", "bongowood": "TZ"}
LANG_CODE_FIX = {"Mandarin": "zh", "Cantonese": "cn", "Odia": "or", "Tagalog": "tl", "Norwegian": "no", "Persian": "fa",
                 "Hebrew": "he", "Malay": "ms", "Bengali": "bn", "Tulu": "tcy", "Bhojpuri": "bho", "Konkani": "kok", "Manipuri": "mni"}
# subscription / free services worth a row, in order of preference per market
SERVICES = {
    "IN": ["Netflix", "Amazon Prime Video", "JioHotstar", "Zee5", "Sony Liv", "aha", "Sun Nxt", "Amazon MX Player"],
    "US": ["Netflix", "Amazon Prime Video", "Disney Plus", "HBO Max", "Max", "Hulu", "Apple TV+", "Apple TV Plus", "Paramount Plus", "Peacock Premium"],
    "*":  ["Netflix", "Amazon Prime Video", "Disney Plus", "HBO Max", "Max", "Apple TV+", "Apple TV Plus", "Viki", "iQIYI", "Viu",
           "BBC iPlayer", "Canal+", "Movistar Plus+", "RaiPlay", "Globoplay", "Crunchyroll", "MUBI", "Showmax", "Shahid VIP", "Wavve", "TVING", "U-NEXT"],
}
PER_REGION = 4
TOP = 10

def providers(region):
    """[(id, display name)] of up to PER_REGION known streaming services available in the region."""
    seen, have = {}, {}
    for media in ("movie", "tv"):
        for p in (get(f"/watch/providers/{media}", watch_region=region) or {}).get("results", []):
            have.setdefault(p["provider_name"], p["provider_id"])
    for name in SERVICES.get(region, []) + SERVICES["*"]:
        if name in have:
            disp = PMAP.get(name, name.replace("Disney Plus", "Disney+").replace("Paramount Plus", "Paramount+").replace("Apple TV Plus", "Apple TV+"))
            if disp not in seen.values(): seen[have[name]] = disp
        if len(seen) >= PER_REGION: break
    return list(seen.items())

def scopes():
    out = []
    for slug, lang in INDUSTRY_LANG.items():
        f = {}
        code = LANG_CODE_FIX.get(lang) or next((c for c, n in CODES.items() if n == lang and len(c) == 2), None)
        if slug in INDIAN and code: f["with_original_language"] = code
        elif COUNTRY.get(slug): f["with_origin_country"] = COUNTRY[slug]
        else: continue
        out.append(("industry", slug, "IN" if slug in INDIAN else COUNTRY.get(slug, "US"), f))
    langs = [r["lang"] for r in query("select lang, sum(total) n from language_stats group by lang order by n desc limit 45")]
    for lang in langs:
        code = LANG_CODE_FIX.get(lang) or next((c for c, n in CODES.items() if n == lang and len(c) == 2), None)
        if code: out.append(("language", lang, "IN" if lang in INDIAN_LANGS else "US", {"with_original_language": code}))
    return out

def trending(scope, region, prov, filters):
    pid, pname = prov
    items = []
    for media in ("movie", "tv"):
        d = get(f"/discover/{media}", watch_region=region, with_watch_providers=pid, with_watch_monetization_types="flatrate|free|ads",
                sort_by="popularity.desc", include_adult="false", **filters) or {}
        for x in d.get("results", [])[:TOP]:
            if x.get("adult"): continue
            date = x.get("release_date") or x.get("first_air_date") or ""
            items.append({"media": media, "tmdb_id": x["id"], "title": x.get("title") or x.get("name"),
                          "year": int(date[:4]) if date[:4].isdigit() else None,
                          "poster": ("https://image.tmdb.org/t/p/w342" + x["poster_path"]) if x.get("poster_path") else None,
                          "popularity": x.get("popularity") or 0})
    items.sort(key=lambda i: -i["popularity"])
    return [(scope[0], scope[1], region, pid, pname, n + 1, i["media"], i["tmdb_id"], i["title"], i["year"], i["poster"], i["popularity"])
            for n, i in enumerate(items[:TOP])]

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--threads", type=int, default=12); a = ap.parse_args()
    load_codes()
    sc = scopes()
    regions = sorted({r for _, _, r, _ in sc})
    with ThreadPoolExecutor(a.threads) as ex:
        provs = dict(zip(regions, ex.map(providers, regions)))
    jobs = [((kind, key), region, p, f) for kind, key, region, f in sc for p in provs[region]]
    print(f"{len(sc)} industries/languages, {len(jobs)} service lists", flush=True)
    with ThreadPoolExecutor(a.threads) as ex:
        rows = [r for res in ex.map(lambda j: trending(*j), jobs) for r in res]
    # link to our catalog where we have the title
    ids = {}
    for media, typ in (("movie", "movie"), ("tv", "series")):
        tids = sorted({r[7] for r in rows if r[6] == media})
        for i in range(0, len(tids), 400):
            chunk = tids[i:i + 400]
            q = f"""select tmdb_id, title_id, industry from titles where {"type = 'series'" if typ == "series" else "type <> 'series'"}
                    and tmdb_id in ({",".join("?" * len(chunk))})"""
            for t in query(q, chunk): ids.setdefault((media, t["tmdb_id"]), []).append(t)
    today = datetime.date.today().isoformat()
    final = []
    for r in rows:
        cands = ids.get((r[6], r[7]), [])
        pick = next((c for c in cands if r[0] == "industry" and c["industry"] == r[1]), None) or (cands[0] if cands else None)
        final.append(r + ((pick or {}).get("title_id"), today))
    stmts = [("drop table if exists platform_trends_new", []), ("""create table platform_trends_new (scope text, scope_key text, region text,
        provider_id integer, provider text, rank integer, media text, tmdb_id integer, title text, year integer, poster text,
        popularity real, title_id text, updated text)""", [])]
    for i in range(0, len(final), 60):
        chunk = final[i:i + 60]
        stmts.append((f"insert into platform_trends_new values {','.join(['(?,?,?,?,?,?,?,?,?,?,?,?,?,?)'] * len(chunk))}", [v for row in chunk for v in row]))
    stmts += [("drop table if exists platform_trends", []), ("alter table platform_trends_new rename to platform_trends", []),
              ("create index if not exists platform_trends_idx on platform_trends (scope, scope_key, provider, rank)", [])]
    for i in range(0, len(stmts), 40): execute(stmts[i:i + 40])
    linked = sum(1 for r in final if r[12])
    print(f"saved {len(final)} trending entries ({linked} link to our catalog)", flush=True)
