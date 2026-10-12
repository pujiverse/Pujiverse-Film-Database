"""
Daily sync with TMDB: asks TMDB which movies and TV shows changed in the last N days, and refreshes the ones in
our catalog (rating, votes, poster, story, genre, release date, languages and where to watch).

  TURSO_URL, TURSO_TOKEN (full access) and TMDB_API_KEY in the environment / .env
  python tmdb_changes.py            # changes from the last 2 days (overlap so a missed run loses nothing)
  python tmdb_changes.py --days 7
"""
import argparse, datetime
from concurrent.futures import ThreadPoolExecutor
from turso_client import query
from enrich_watch import get, enrich, save

def changed_ids(kind, start, end):
    ids, page = [], 1
    while True:
        d = get(f"/{kind}/changes", start_date=start, end_date=end, page=page) or {}
        ids += [r["id"] for r in d.get("results", []) if not r.get("adult")]
        if page >= min(d.get("total_pages", 1), 500): return ids
        page += 1

def ours(kind, ids):
    rows = []
    typ = "series" if kind == "tv" else "movie"
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        rows += query(f"""select title_id, title, original_title, title_local, year, industry, type, tmdb_id, imdb_id from titles
                          where type = ? and tmdb_id in ({",".join("?" * len(chunk))})""", [typ] + chunk)
    return rows

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--days", type=int, default=2); ap.add_argument("--threads", type=int, default=16)
    a = ap.parse_args()
    end = datetime.date.today(); start = end - datetime.timedelta(days=min(a.days, 14))   # TMDB allows up to 14 days
    total = 0
    for kind in ("movie", "tv"):
        ids = changed_ids(kind, start.isoformat(), end.isoformat())
        rows = ours(kind, ids)
        print(f"{kind}: {len(ids)} changed on TMDB since {start}, {len(rows)} of them in our catalog", flush=True)
        with ThreadPoolExecutor(a.threads) as ex:
            for i in range(0, len(rows), 400):
                save(list(ex.map(lambda r: enrich(r, providers_only=True), rows[i:i + 400])))
        total += len(rows)
    print(f"refreshed {total} titles", flush=True)
