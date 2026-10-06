"""
Upcoming films for every industry, from TMDB. Adds new titles and refreshes the release date, story,
poster, languages and where-to-watch of upcoming titles already in the catalog.
Run it every few weeks to keep the "Coming soon" list current.

  TURSO_URL, TURSO_TOKEN (full access) and TMDB_API_KEY in the environment / .env
  python fetch_upcoming.py              # every industry, next 18 months
  python fetch_upcoming.py tollywood bollywood --days 365
"""
import os, sys, re, time, datetime, argparse
from concurrent.futures import ThreadPoolExecutor
import requests
from turso_client import execute, query, refresh_stats

KEY = os.environ.get("TMDB_API_KEY") or sys.exit("Set TMDB_API_KEY")
T = "https://api.themoviedb.org/3"; S = requests.Session()
TODAY = datetime.date.today()

LANG = {"bollywood": ("hi", "IN"), "tollywood": ("te", None), "kollywood": ("ta", "IN"), "mollywood": ("ml", None),
        "sandalwood": ("kn", None), "bengali-tollywood": ("bn", "IN"), "marathi": ("mr", None), "pollywood": ("pa", "IN"),
        "dhollywood": ("gu", None), "ollywood": ("or", None), "jollywood": ("as", None), "bhojiwood": ("bho", None),
        "coastalwood": ("tcy", None), "konkani": ("kok", None), "manipuri": ("mni", None),
        "lollywood": ("ur", "PK"), "dhallywood": ("bn", "BD"), "nepal": ("ne", None), "srilanka": ("si", None)}
ISO = {"china": "CN", "hongkong": "HK", "taiwan": "TW", "korea": "KR", "japan": "JP", "thailand": "TH", "philippines": "PH",
       "indonesia": "ID", "vietnam": "VN", "malaysia": "MY", "hollywood": "US", "canada": "CA", "mexico": "MX", "brazil": "BR",
       "argentina": "AR", "colombia": "CO", "chile": "CL", "cuba": "CU", "uk": "GB", "france": "FR", "italy": "IT", "germany": "DE",
       "spain": "ES", "russia": "RU", "denmark": "DK", "sweden": "SE", "norway": "NO", "finland": "FI", "iceland": "IS",
       "poland": "PL", "czechia": "CZ", "ireland": "IE", "greece": "GR", "romania": "RO", "nollywood": "NG", "ghallywood": "GH",
       "riverwood": "KE", "bongowood": "TZ", "southafrica": "ZA", "egypt": "EG", "turkey": "TR", "iran": "IR", "israel": "IL",
       "morocco": "MA", "australia": "AU", "newzealand": "NZ"}
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

def prov(block, kinds=("flatrate", "free", "ads")):
    names = {PMAP.get(p["provider_name"].strip(), re.sub(r" (Free )?with Ads$", "", p["provider_name"].strip()))
             for k in kinds for p in (block or {}).get(k, [])}
    return ", ".join(sorted(names)) or None

def discover(slug, days, max_pages):
    """Walk month by month so every month gets its most popular films (not just the next few weeks)."""
    base = {"sort_by": "popularity.desc", "include_adult": "false"}
    if slug in LANG:
        lang, ctry = LANG[slug]; base["with_original_language"] = lang
        if ctry: base["with_origin_country"] = ctry
    else: base["with_origin_country"] = ISO[slug]
    end, start, ids = TODAY + datetime.timedelta(days=days), TODAY, []
    while start <= end:
        nxt = (start.replace(day=1) + datetime.timedelta(days=32)).replace(day=1)
        stop = min(nxt - datetime.timedelta(days=1), end)
        page = 1
        while page <= max_pages:
            d = get("/discover/movie", page=page, **base, **{"primary_release_date.gte": start.isoformat(), "primary_release_date.lte": stop.isoformat()})
            if not d: break
            ids += [x["id"] for x in d.get("results", []) if not x.get("adult")]
            if page >= d.get("total_pages", 1): break
            page += 1
        start = nxt
    return list(dict.fromkeys(ids))

def detail(slug, mid):
    m = get(f"/movie/{mid}", append_to_response="watch/providers,credits")
    if not m or m.get("adult") or not m.get("release_date"): return None
    rd = m["release_date"]
    wp = (m.get("watch/providers") or {}).get("results", {}); us, ind = wp.get("US") or {}, wp.get("IN") or {}
    crew = (m.get("credits") or {}).get("crew", [])
    votes = m.get("vote_count") or 0
    return {"tmdb_id": mid, "title": m.get("title"), "original_title": m.get("original_title"),
        "title_local": m.get("original_title") if m.get("original_title") != m.get("title") else None,
        "industry": slug, "language": m.get("original_language"),
        "status": "upcoming" if rd > TODAY.isoformat() else "released", "release_date": rd, "year": int(rd[:4]),
        "genre": ", ".join(g["name"] for g in m.get("genres", [])) or None, "runtime_min": m.get("runtime") or None,
        "director": ", ".join(dict.fromkeys(c["name"] for c in crew if c.get("job") == "Director")) or None,
        "cast_names": ", ".join(c["name"] for c in (m.get("credits") or {}).get("cast", [])[:12]) or None,
        "overview": m.get("overview") or None,
        "poster_url": ("https://image.tmdb.org/t/p/w500" + m["poster_path"]) if m.get("poster_path") else None,
        "tmdb_rating": m.get("vote_average"), "tmdb_votes": votes,
        "rating_display": m.get("vote_average") if votes >= 10 else None,
        "streaming_in": prov(ind), "streaming_us": prov(us), "rent_buy_us": prov(us, ("rent", "buy")),
        "watch_link_in": ind.get("link"), "watch_link_us": us.get("link"), "imdb_id": m.get("imdb_id") or None,
        "languages": ", ".join(dict.fromkeys(l.get("english_name") or l.get("name") for l in m.get("spoken_languages", []))) or None,
        "source": "tmdb"}

INS_COLS = ["title_id", "tmdb_id", "title", "original_title", "title_local", "industry", "language", "type", "status",
            "release_date", "year", "genre", "runtime_min", "director", "cast_names", "overview", "poster_url", "tmdb_rating",
            "tmdb_votes", "rating_display", "streaming_in", "streaming_us", "rent_buy_us", "watch_link_in", "watch_link_us",
            "imdb_id", "languages", "source", "tmdb_checked_at"]
UPD = """update titles set release_date = ?, year = ?, status = ?, languages = coalesce(?, languages),
  overview = coalesce(overview, ?), poster_url = coalesce(poster_url, ?), director = coalesce(director, ?),
  cast_names = coalesce(cast_names, ?), genre = coalesce(genre, ?), imdb_id = coalesce(imdb_id, ?), tmdb_id = coalesce(tmdb_id, ?),
  streaming_in = coalesce(?, streaming_in), streaming_us = coalesce(?, streaming_us), watch_link_in = coalesce(?, watch_link_in),
  watch_link_us = coalesce(?, watch_link_us), tmdb_checked_at = datetime('now')
where title_id = ?"""

def run(slug, days, max_pages):
    t0 = time.time()
    with ThreadPoolExecutor(12) as ex:
        rows = [r for r in ex.map(lambda i: detail(slug, i), discover(slug, days, max_pages)) if r]
    if not rows:
        print(f"{slug}: no upcoming films found", flush=True); return
    tids = [r["tmdb_id"] for r in rows]; imdbs = [r["imdb_id"] for r in rows if r["imdb_id"]]
    existing = {}
    for i in range(0, len(tids), 400):
        chunk = tids[i:i + 400]
        for e in query(f"select title_id, tmdb_id from titles where industry = ? and tmdb_id in ({','.join('?' * len(chunk))})", [slug] + chunk):
            existing[e["tmdb_id"]] = e["title_id"]
    for i in range(0, len(imdbs), 400):
        chunk = imdbs[i:i + 400]
        for e in query(f"select title_id, imdb_id from titles where industry = ? and imdb_id in ({','.join('?' * len(chunk))})", [slug] + chunk):
            for r in rows:
                if r["imdb_id"] == e["imdb_id"]: existing.setdefault(r["tmdb_id"], e["title_id"])
    stmts, new = [], 0
    for r in rows:
        tid = existing.get(r["tmdb_id"])
        if tid:
            stmts.append((UPD, [r["release_date"], r["year"], r["status"], r["languages"], r["overview"], r["poster_url"],
                                r["director"], r["cast_names"], r["genre"], r["imdb_id"], r["tmdb_id"], r["streaming_in"],
                                r["streaming_us"], r["watch_link_in"], r["watch_link_us"], tid]))
        else:
            new += 1
            vals = {**r, "title_id": f"{slug}-tmdb-{r['tmdb_id']}", "type": "movie",
                    "tmdb_checked_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")}
            stmts.append((f"insert or ignore into titles ({', '.join(INS_COLS)}) values ({', '.join('?' * len(INS_COLS))})",
                          [vals.get(c) for c in INS_COLS]))
    for i in range(0, len(stmts), 150): execute(stmts[i:i + 150])
    refresh_stats(slug)
    up = sum(1 for r in rows if r["status"] == "upcoming")
    print(f"{slug}: {up} upcoming ({new} new, {len(rows) - new} updated) in {int(time.time() - t0)}s", flush=True)

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("slugs", nargs="*")
    ap.add_argument("--days", type=int, default=540); ap.add_argument("--max-pages", type=int, default=5, help="pages of 20 films per month")
    a = ap.parse_args()
    for s in a.slugs or (list(LANG) + list(ISO)):
        if s in LANG or s in ISO: run(s, a.days, a.max_pages)
