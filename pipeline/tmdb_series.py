"""
Web series for every industry, from TMDB. A show counts as a web series when its original network is a
streaming service. TV-channel serials and adult-content platforms are excluded.
  TMDB_API_KEY=... python tmdb_series.py tollywood bollywood ...   (or --all)
Writes out/<slug>_series.csv  (load with the normal uploader).
"""
import os, sys, re, json, time, argparse, datetime
from concurrent.futures import ThreadPoolExecutor
import requests, pandas as pd

KEY = os.environ.get("TMDB_API_KEY") or sys.exit("Set TMDB_API_KEY")
T = "https://api.themoviedb.org/3"; S = requests.Session()
TODAY = datetime.date.today().isoformat()
LANG = {"bollywood": ("hi", "IN"), "tollywood": ("te", None), "kollywood": ("ta", "IN"), "mollywood": ("ml", None),
        "sandalwood": ("kn", None), "bengali-tollywood": ("bn", "IN"), "marathi": ("mr", None), "pollywood": ("pa", "IN"),
        "dhollywood": ("gu", None), "ollywood": ("or", None), "jollywood": ("as", None), "bhojiwood": ("bho", None),
        "lollywood": ("ur", "PK"), "dhallywood": ("bn", "BD"), "nepal": ("ne", None), "srilanka": ("si", None)}
ISO = {"china": "CN", "hongkong": "HK", "taiwan": "TW", "korea": "KR", "japan": "JP", "thailand": "TH", "philippines": "PH",
       "indonesia": "ID", "vietnam": "VN", "malaysia": "MY", "hollywood": "US", "canada": "CA", "mexico": "MX", "brazil": "BR",
       "argentina": "AR", "colombia": "CO", "chile": "CL", "cuba": "CU", "uk": "GB", "france": "FR", "italy": "IT", "germany": "DE",
       "spain": "ES", "russia": "RU", "denmark": "DK", "sweden": "SE", "norway": "NO", "finland": "FI", "iceland": "IS",
       "poland": "PL", "czechia": "CZ", "ireland": "IE", "greece": "GR", "romania": "RO", "nollywood": "NG", "ghallywood": "GH",
       "riverwood": "KE", "bongowood": "TZ", "southafrica": "ZA", "egypt": "EG", "turkey": "TR", "iran": "IR", "israel": "IL",
       "morocco": "MA", "australia": "AU", "newzealand": "NZ"}
STREAMERS = ["netflix", "prime video", "amazon", "disney+", "hotstar", "zee5", "sonyliv", "sony liv", "aha", "altbalaji",
    "alt balaji", "mx player", "jiocinema", "voot", "etv win", "sun nxt", "sunnxt", "hoichoi", "addatimes", "klikk", "chaupal",
    "stage", "planet marathi", "shemaroo", "hungama", "epic on", "apple tv", "hulu", "max", "paramount+", "peacock", "youtube",
    "viki", "tving", "wavve", "coupang play", "iqiyi", "youku", "tencent video", "mango tv", "bilibili", "u-next", "abema",
    "fod", "stan", "binge", "crave", "globoplay", "vix", "movistar plus+", "viaplay", "c more", "ruutu", "tv 2 play",
    "showmax", "irokotv", "blim", "claro video", "star+", "kinopoisk", "okko", "ivi", "premier", "start", "wink", "more.tv",
    "kion", "viu", "iflix", "vidio", "wetv", "catchplay", "friday", "line tv", "trueid", "aisplay", "iwanttfc", "shahid",
    "osn+", "watch it", "yango play", "exxen", "blutv", "gain", "tabii", "filmo", "namava", "filimo", "yes+", "rakuten",
    "skyshowtime", "rtl+", "joyn", "magenta", "raiplay", "mediaset infinity", "atresplayer", "france.tv", "salto",
    "britbox", "itvx", "all 4", "bbc iplayer", "britbox", "now", "sbs on demand", "abc iview", "neon", "tvnz+", "three now",
    "polsat box go", "player", "cda", "voyo", "hbo"]
BLOCK = ["ullu", "kooku", "primeplay", "prime play", "hunters", "rabbit movies", "vivamax", "atrangii", "besharams",
         "hotx", "fliz", "nuefliks", "bigshots", "cineprime", "voovi", "dreams films", "tadka prime", "navarasa"]
PMAP = {"Amazon Prime Video": "Prime Video", "Amazon Prime Video with Ads": "Prime Video", "Netflix Standard with Ads": "Netflix",
        "Disney Plus Hotstar": "JioHotstar", "Aha": "aha"}

def get(path, **p):
    p["api_key"] = KEY
    for i in range(4):
        try:
            r = S.get(T + path, params=p, timeout=30)
            if r.status_code == 429: time.sleep(1 + 2 * i); continue
            if r.status_code == 404: return None
            if r.ok: return r.json()
        except requests.RequestException: time.sleep(1)
    return None

def is_web(networks):
    names = [n.lower() for n in networks[:1]]          # judge by the ORIGINAL network only
    if any(b in n for n in names for b in BLOCK): return False
    return any(re.search(r"(^|\W)" + re.escape(s) + r"($|\W)", n) for n in names for s in STREAMERS)

def prov(block, kinds=("flatrate", "free", "ads")):
    names = {PMAP.get(p["provider_name"].strip(), re.sub(r" (Free )?with Ads$", "", p["provider_name"].strip()))
             for k in kinds for p in (block or {}).get(k, [])}
    return ", ".join(sorted(names)) or None

def discover(slug, year):
    p = {"first_air_date_year": year, "sort_by": "popularity.desc", "include_adult": "false"}
    if slug in LANG:
        lang, ctry = LANG[slug]; p["with_original_language"] = lang
        if ctry: p["with_origin_country"] = ctry
    else: p["with_origin_country"] = ISO[slug]
    ids, page = [], 1
    while page <= 500:
        d = get("/discover/tv", page=page, **p)
        if not d: break
        ids += [x["id"] for x in d.get("results", []) if not x.get("adult")]
        if page >= d.get("total_pages", 1): break
        page += 1
    return ids

def detail(slug, sid):
    m = get(f"/tv/{sid}", append_to_response="watch/providers,external_ids,credits")
    if not m or m.get("adult"): return None
    nets = [n["name"] for n in m.get("networks", [])]
    if not is_web(nets): return None
    fa = m.get("first_air_date") or None
    wp = (m.get("watch/providers") or {}).get("results", {}); us, ind = wp.get("US") or {}, wp.get("IN") or {}
    rt = (m.get("episode_run_time") or [None])[0]
    votes = m.get("vote_count") or 0
    return {"title_id": f"{slug}-tv-{sid}", "title": m.get("name"), "original_title": m.get("original_name"),
        "title_local": m.get("original_name") if m.get("original_name") != m.get("name") else None,
        "industry": slug, "language": m.get("original_language"), "type": "series",
        "status": "upcoming" if fa and fa > TODAY else ("released" if fa else "unknown"),
        "release_date": fa, "year": int(fa[:4]) if fa else None, "last_air_date": m.get("last_air_date"),
        "series_status": m.get("status"), "seasons": m.get("number_of_seasons"), "episodes": m.get("number_of_episodes"),
        "network": ", ".join(nets) or None, "genre": ", ".join(g["name"] for g in m.get("genres", [])) or None,
        "runtime_min": rt, "creators": ", ".join(c["name"] for c in m.get("created_by", [])) or None,
        "cast": ", ".join(c["name"] for c in (m.get("credits") or {}).get("cast", [])[:12]) or None,
        "overview": m.get("overview") or None,
        "poster_url": ("https://image.tmdb.org/t/p/w500" + m["poster_path"]) if m.get("poster_path") else None,
        "tmdb_rating": m.get("vote_average"), "tmdb_votes": votes,
        "rating_display": m.get("vote_average") if votes >= 10 else None,
        "streaming_in": prov(ind), "streaming_us": prov(us), "rent_buy_us": prov(us, ("rent", "buy")),
        "watch_link_in": ind.get("link"), "watch_link_us": us.get("link"),
        "imdb_id": (m.get("external_ids") or {}).get("imdb_id"), "tmdb_id": sid, "source": "tmdb",
        "tmdb_checked_at": datetime.datetime.now(datetime.timezone.utc).isoformat(), "user_rating_count": 0}

def run(slug):
    t = time.time()
    with ThreadPoolExecutor(12) as ex:
        ids = list(dict.fromkeys(i for lst in ex.map(lambda y: discover(slug, y), range(1995, 2028)) for i in lst))
        rows = [r for r in ex.map(lambda i: detail(slug, i), ids) if r]
    pd.DataFrame(rows).to_csv(f"out/{slug}_series.csv", index=False)
    print(f"{slug}: {len(ids)} shows checked, {len(rows)} web series ({int(time.time()-t)}s)", flush=True)

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("slugs", nargs="*"); ap.add_argument("--all", action="store_true")
    a = ap.parse_args()
    for s in (list(LANG) + list(ISO)) if a.all else a.slugs:
        if s in LANG or s in ISO: run(s)
