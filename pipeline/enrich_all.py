"""
TMDB enrichment for every film in Supabase: story, poster, rating, where-to-watch (IN + US) and watch-page links.
Needs SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY and TMDB_API_KEY in the environment.
Resumable: each processed film gets tmdb_checked_at, so reruns continue where they stopped.
  TMDB_API_KEY=... python enrich_all.py [--seconds 280] [--ids-only]
"""
import os, sys, re, time, json, unicodedata, argparse
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher
import requests

TMDB = "https://api.themoviedb.org/3"
KEY = os.environ.get("TMDB_API_KEY") or sys.exit("Set TMDB_API_KEY")
SB = (os.environ.get("SUPABASE_URL") or sys.exit("Set SUPABASE_URL")).rstrip("/") + "/rest/v1/"
SRK = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or sys.exit("Set SUPABASE_SERVICE_ROLE_KEY")
H = {"apikey": SRK, "Authorization": f"Bearer {SRK}", "Content-Type": "application/json"}
S = requests.Session()

LANG = {"bollywood": "hi", "tollywood": "te", "kollywood": "ta", "mollywood": "ml", "sandalwood": "kn",
        "bengali-tollywood": "bn", "marathi": "mr", "pollywood": "pa", "dhollywood": "gu", "ollywood": "or",
        "jollywood": "as", "bhojiwood": "bh", "coastalwood": "tcy", "konkani": "kok", "manipuri": "mni"}
ISO = {"lollywood": "PK", "dhallywood": "BD", "nepal": "NP", "srilanka": "LK", "china": "CN", "hongkong": "HK",
       "taiwan": "TW", "korea": "KR", "japan": "JP", "thailand": "TH", "philippines": "PH", "indonesia": "ID",
       "vietnam": "VN", "malaysia": "MY", "hollywood": "US", "canada": "CA", "mexico": "MX", "brazil": "BR",
       "argentina": "AR", "colombia": "CO", "chile": "CL", "cuba": "CU", "uk": "GB", "france": "FR", "italy": "IT",
       "germany": "DE", "spain": "ES", "russia": "RU", "denmark": "DK", "sweden": "SE", "norway": "NO", "finland": "FI",
       "iceland": "IS", "poland": "PL", "czechia": "CZ", "ireland": "IE", "greece": "GR", "romania": "RO",
       "nollywood": "NG", "ghallywood": "GH", "riverwood": "KE", "bongowood": "TZ", "southafrica": "ZA",
       "egypt": "EG", "turkey": "TR", "iran": "IR", "israel": "IL", "morocco": "MA", "australia": "AU", "newzealand": "NZ"}
OLD_ISO = {"RU": {"SU"}, "CZ": {"XC", "CS"}, "DE": {"DD", "XG"}}
PMAP = {"Amazon Prime Video": "Prime Video", "Amazon Prime Video with Ads": "Prime Video", "Amazon MX Player": "MX Player",
        "Netflix Standard with Ads": "Netflix", "Netflix basic with Ads": "Netflix", "Disney Plus Hotstar": "JioHotstar",
        "VI movies and tv": "Vi Movies & TV", "Aha": "aha"}

def norm(t):
    t = unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", re.sub(r"\(.*?\)", "", t))

def get(path, **p):
    p["api_key"] = KEY
    for i in range(4):
        try:
            r = S.get(TMDB + path, params=p, timeout=30)
            if r.status_code == 429: time.sleep(1 + i * 2); continue
            if r.status_code == 404: return None
            if r.ok: return r.json()
        except requests.RequestException: time.sleep(1)
    return None

def providers(block, kinds=("flatrate", "free", "ads")):
    names = {PMAP.get(p["provider_name"].strip(), re.sub(r" (Free )?with Ads$", "", p["provider_name"].strip()))
             for k in kinds for p in (block or {}).get(k, [])}
    return ", ".join(sorted(names)) or None

def fits(row, m):
    if row["industry"] in LANG: return m.get("original_language") == LANG[row["industry"]]
    iso = ISO.get(row["industry"])
    if not iso: return True
    oc = set(m.get("origin_country") or []) | {c["iso_3166_1"] for c in m.get("production_countries", [])}
    return iso in oc or bool(oc & OLD_ISO.get(iso, set()))

def resolve(row):
    if row.get("tmdb_id"): return int(row["tmdb_id"]), "id"
    if row.get("imdb_id"):
        f = get(f"/find/{row['imdb_id']}", external_source="imdb_id")
        if f and f.get("movie_results"): return f["movie_results"][0]["id"], "imdb"
    if not row.get("year"): return None, None
    want = {norm(row["title"]), norm(row.get("original_title")), norm(row.get("title_local"))} - {""}
    res = (get("/search/movie", query=row["title"], primary_release_year=row["year"]) or {}).get("results", [])
    for c in res[:5]:
        names = {norm(c.get("title")), norm(c.get("original_title"))}
        if any(SequenceMatcher(None, a, b).ratio() >= 0.88 for a in want for b in names if a and b):
            return c["id"], "search"
    return None, None

def enrich(row):
    out = {"title_id": row["title_id"]}
    try:
        tid, how = resolve(row)
        if not tid: return out
        m = get(f"/movie/{tid}", append_to_response="watch/providers")
        if not m: return out
        if how == "search" and not fits(row, m): return out
        wp = (m.get("watch/providers") or {}).get("results", {})
        us, ind = wp.get("US") or {}, wp.get("IN") or {}
        out.update({
            "tmdb_id": tid, "overview": m.get("overview") or None,
            "poster_url": ("https://image.tmdb.org/t/p/w500" + m["poster_path"]) if m.get("poster_path") else None,
            "tmdb_rating": m.get("vote_average"), "tmdb_votes": m.get("vote_count"),
            "streaming_in": providers(ind), "streaming_us": providers(us),
            "rent_buy_us": providers(us, ("rent", "buy")),
            "watch_link_in": ind.get("link"), "watch_link_us": us.get("link"),
            "runtime_min": m.get("runtime") or None,
            "release_date": m.get("release_date") or None, "imdb_id": m.get("imdb_id") or None})
    except Exception as e:
        print("err", row["title_id"], e, flush=True)
    return out

def fetch_todo(ids_only, n=600):
    p = {"select": "title_id,title,original_title,title_local,year,industry,tmdb_id,imdb_id",
         "tmdb_checked_at": "is.null", "order": "year.desc.nullslast", "limit": str(n)}
    if ids_only: p["or"] = "(tmdb_id.not.is.null,imdb_id.not.is.null)"
    r = S.get(SB + "titles", params=p, headers=H, timeout=60); r.raise_for_status(); return r.json()

def save(rows):
    if not rows: return
    r = S.post(SB + "rpc/apply_tmdb_enrichment", headers=H, json={"rows": rows}, timeout=120)
    if r.ok: return
    if len(rows) == 1:
        print("skip", rows[0]["title_id"], r.text[:160], flush=True)
        S.post(SB + "rpc/apply_tmdb_enrichment", headers=H, json={"rows": [{"title_id": rows[0]["title_id"]}]}, timeout=60)
        return
    h = len(rows) // 2; save(rows[:h]); save(rows[h:])

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--seconds", type=int, default=280); ap.add_argument("--ids-only", action="store_true")
    a = ap.parse_args(); t0 = time.time(); done = hit = 0
    with ThreadPoolExecutor(12) as ex:
        while time.time() - t0 < a.seconds:
            todo = fetch_todo(a.ids_only)
            if not todo: print("nothing left"); break
            res = list(ex.map(enrich, todo))
            for i in range(0, len(res), 150): save(res[i:i+150])
            done += len(res); hit += sum(1 for r in res if r.get("tmdb_id"))
            print(f"{done} checked, {hit} matched ({int(time.time()-t0)}s)", flush=True)
