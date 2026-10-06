"""
Where-to-watch (and story/poster) for every title, from TMDB (streaming data by JustWatch).
Keeps per-country providers for India, US, UK, Canada, Australia and the title's home country in
`watch_regions` (JSON), and fills streaming_in / streaming_us / rent_buy_us for the list views.
Resumable and safe to rerun.

  TURSO_URL, TURSO_TOKEN (full access) and TMDB_API_KEY in the environment / .env
  python enrich_watch.py --phase new      # titles never checked that have a TMDB or IMDb id
  python enrich_watch.py --phase recheck  # already-checked titles: add per-country providers
  python enrich_watch.py --phase search   # titles with no ids: match by title + year (strict)
  python enrich_watch.py --phase all --seconds 3600
"""
import os, sys, re, time, json, argparse, unicodedata, datetime
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher
import requests
from turso_client import query, execute

KEY = os.environ.get("TMDB_API_KEY") or sys.exit("Set TMDB_API_KEY")
T = "https://api.themoviedb.org/3"
S = requests.Session()
S.mount("https://", requests.adapters.HTTPAdapter(pool_connections=32, pool_maxsize=32))

KEEP = ["IN", "US", "GB", "CA", "AU"]
HOME = {"lollywood": "PK", "dhallywood": "BD", "nepal": "NP", "srilanka": "LK", "china": "CN", "hongkong": "HK", "taiwan": "TW",
        "korea": "KR", "japan": "JP", "thailand": "TH", "philippines": "PH", "indonesia": "ID", "vietnam": "VN", "malaysia": "MY",
        "mexico": "MX", "brazil": "BR", "argentina": "AR", "colombia": "CO", "chile": "CL", "france": "FR", "italy": "IT",
        "germany": "DE", "spain": "ES", "russia": "RU", "denmark": "DK", "sweden": "SE", "norway": "NO", "finland": "FI",
        "iceland": "IS", "poland": "PL", "czechia": "CZ", "ireland": "IE", "greece": "GR", "romania": "RO", "nollywood": "NG",
        "ghallywood": "GH", "riverwood": "KE", "southafrica": "ZA", "egypt": "EG", "turkey": "TR", "israel": "IL",
        "morocco": "MA", "newzealand": "NZ"}
LANG = {"bollywood": "hi", "tollywood": "te", "kollywood": "ta", "mollywood": "ml", "sandalwood": "kn", "bengali-tollywood": "bn",
        "marathi": "mr", "pollywood": "pa", "dhollywood": "gu", "ollywood": "or", "jollywood": "as", "bhojiwood": "bho"}
PMAP = {"Amazon Prime Video": "Prime Video", "Amazon Prime Video with Ads": "Prime Video", "Amazon Prime Video Free with Ads": "Prime Video",
        "Amazon MX Player": "MX Player", "Netflix Standard with Ads": "Netflix", "Netflix basic with Ads": "Netflix",
        "Disney Plus Hotstar": "JioHotstar", "Hotstar": "JioHotstar", "VI movies and tv": "Vi Movies & TV", "Aha": "aha"}

def get(path, **p):
    p["api_key"] = KEY
    for i in range(5):
        try:
            r = S.get(T + path, params=p, timeout=30)
            if r.status_code == 429: time.sleep(1 + 2 * i); continue
            if r.status_code == 404: return None
            if r.ok: return r.json()
        except requests.RequestException: time.sleep(1 + i)
    return None

def names(block, kinds):
    out = []
    for k in kinds:
        for p in (block or {}).get(k, []):
            n = p["provider_name"].strip()
            n = PMAP.get(n, re.sub(r" (Free )?with Ads$", "", n))
            if n not in out: out.append(n)
    return out

def regions(results, industry):
    keep = KEEP + ([HOME[industry]] if industry in HOME and HOME[industry] not in KEEP else [])
    out = {}
    for c in keep:
        b = (results or {}).get(c)
        if not b: continue
        e = {"s": names(b, ("flatrate", "free", "ads")), "r": names(b, ("rent",)), "b": names(b, ("buy",)), "l": b.get("link")}
        e = {k: v for k, v in e.items() if v}
        if any(k in e for k in ("s", "r", "b")): out[c] = e
    return out

def norm(t):
    t = unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", re.sub(r"\(.*?\)", "", t))

def resolve(row):
    """Return (kind, tmdb_id) or (None, None)."""
    kind = "tv" if row["type"] == "series" else "movie"
    if row.get("tmdb_id"): return kind, int(row["tmdb_id"])
    if row.get("imdb_id"):
        f = get(f"/find/{row['imdb_id']}", external_source="imdb_id") or {}
        hit = (f.get("tv_results") if kind == "tv" else f.get("movie_results")) or f.get("movie_results") or f.get("tv_results")
        if hit: return ("tv" if hit[0].get("media_type") == "tv" or "first_air_date" in hit[0] else "movie"), hit[0]["id"]
    if not row.get("year") or not row.get("title"): return None, None
    want = {norm(row["title"]), norm(row.get("original_title")), norm(row.get("title_local"))} - {""}
    params = {"query": row["title"]}
    params["first_air_date_year" if kind == "tv" else "primary_release_year"] = row["year"]
    for c in ((get(f"/search/{kind}", **params) or {}).get("results") or [])[:5]:
        got = {norm(c.get("title") or c.get("name")), norm(c.get("original_title") or c.get("original_name"))} - {""}
        lang_ok = row["industry"] not in LANG or c.get("original_language") == LANG[row["industry"]]
        if lang_ok and any(a == b or SequenceMatcher(None, a, b).ratio() >= 0.9 for a in want for b in got):
            return kind, c["id"]
    return None, None

def enrich(row, providers_only=False):
    out = {"title_id": row["title_id"]}
    try:
        kind, tid = ("tv" if row["type"] == "series" else "movie", int(row["tmdb_id"])) if providers_only else resolve(row)
        if not tid: return out
        m = get(f"/{kind}/{tid}", append_to_response="watch/providers") or {}
        if not m: return out
        wp = (m.get("watch/providers") or {}).get("results", {})
        reg = regions(wp, row["industry"])
        ind, us = reg.get("IN", {}), reg.get("US", {})
        votes = m.get("vote_count")
        out.update({"tmdb_id": tid, "watch_regions": json.dumps(reg, separators=(",", ":")),
            "streaming_in": ", ".join(ind.get("s", [])) or None, "streaming_us": ", ".join(us.get("s", [])) or None,
            "rent_buy_us": ", ".join(dict.fromkeys(us.get("r", []) + us.get("b", []))) or None,
            "watch_link_in": ind.get("l"), "watch_link_us": us.get("l"),
            "overview": m.get("overview") or None,
            "poster_url": ("https://image.tmdb.org/t/p/w500" + m["poster_path"]) if m.get("poster_path") else None,
            "tmdb_rating": m.get("vote_average"), "tmdb_votes": votes,
            "runtime_min": m.get("runtime") or ((m.get("episode_run_time") or [None])[0]),
            "release_date": m.get("release_date") or m.get("first_air_date") or None, "imdb_id": m.get("imdb_id") or None,
            "genre": ", ".join(g["name"] for g in m.get("genres", [])) or None,
            "languages": ", ".join(dict.fromkeys(l.get("english_name") or l.get("name") for l in m.get("spoken_languages", []))) or None})
    except Exception as e:
        print("err", row["title_id"], str(e)[:120], flush=True)
    return out

UPD = """update titles set
  tmdb_id = coalesce(tmdb_id, ?), watch_regions = coalesce(?, watch_regions, '{}'),
  streaming_in = coalesce(?, streaming_in), streaming_us = coalesce(?, streaming_us), rent_buy_us = coalesce(?, rent_buy_us),
  watch_link_in = coalesce(?, watch_link_in), watch_link_us = coalesce(?, watch_link_us),
  overview = coalesce(overview, ?), poster_url = coalesce(poster_url, ?),
  tmdb_rating = coalesce(?, tmdb_rating), tmdb_votes = coalesce(?, tmdb_votes),
  rating_display = case when coalesce(?, tmdb_votes, 0) >= 10 then coalesce(?, tmdb_rating) else rating_display end,
  runtime_min = coalesce(runtime_min, ?),
  release_date = case when (release_date is null or substr(release_date, 6) = '01-01') and ? is not null
                       and (year is null or substr(?, 1, 4) = cast(year as text)) then ? else release_date end,
  genre = coalesce(genre, ?),
  imdb_id = coalesce(imdb_id, ?), languages = coalesce(languages, ?), tmdb_checked_at = datetime('now')
where title_id = ?"""

def save(rows):
    st = []
    for r in rows:
        g = r.get
        st.append((UPD, [g("tmdb_id"), g("watch_regions"), g("streaming_in"), g("streaming_us"), g("rent_buy_us"), g("watch_link_in"),
                         g("watch_link_us"), g("overview"), g("poster_url"), g("tmdb_rating"), g("tmdb_votes"), g("tmdb_votes"),
                         g("tmdb_rating"), g("runtime_min"), g("release_date"), g("release_date"), g("release_date"), g("genre"),
                         g("imdb_id"), g("languages"), r["title_id"]]))
    for i in range(0, len(st), 150): execute(st[i:i + 150])

COLS = "title_id, title, original_title, title_local, year, industry, type, tmdb_id, imdb_id"
PHASES = {
    "new": f"select {COLS} from titles where tmdb_checked_at is null and (tmdb_id is not null or imdb_id is not null) order by year desc limit ?",
    "recheck": f"select {COLS} from titles where watch_regions is null and tmdb_id is not null and tmdb_checked_at is not null limit ?",
    "search": f"select {COLS} from titles where tmdb_checked_at is null and tmdb_id is null and imdb_id is null order by year desc limit ?",
}

def run_phase(name, deadline, ex):
    done = hit = 0
    while time.time() < deadline:
        todo = query(PHASES[name], [400])
        if not todo: print(f"{name}: nothing left", flush=True); return True
        res = list(ex.map(lambda r: enrich(r, providers_only=(name == "recheck")), todo))
        if name == "search":   # mark unmatched titles as checked so they aren't searched again
            for r in res: r.setdefault("watch_regions", None)
        save(res)
        done += len(res); hit += sum(1 for r in res if r.get("watch_regions") not in (None, "{}"))
        print(f"{name}: {done} processed, {hit} with where-to-watch", flush=True)
    return False

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["new", "recheck", "search", "all"], default="all")
    ap.add_argument("--seconds", type=int, default=3600); ap.add_argument("--threads", type=int, default=16)
    a = ap.parse_args(); deadline = time.time() + a.seconds
    with ThreadPoolExecutor(a.threads) as ex:
        for ph in (["new", "recheck", "search"] if a.phase == "all" else [a.phase]):
            if not run_phase(ph, deadline, ex): break
