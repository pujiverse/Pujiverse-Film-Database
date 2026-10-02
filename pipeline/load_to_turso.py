"""
Upload pipeline output (out/*.csv) into the Turso catalog, then refresh the year-strip counts.
  set TURSO_URL and TURSO_TOKEN (full-access) in your environment / .env
  python load_to_turso.py                       # every CSV in out/
  python load_to_turso.py bollywood kollywood_wiki japan_series
Insert-or-ignore on title_id: reruns never overwrite existing rows.
"""
import os, sys, glob
import pandas as pd
from turso_client import execute, refresh_stats

COLS = ["title_id", "title", "title_local", "title_telugu", "original_title", "industry", "language", "type", "status",
        "release_date", "year", "genre", "runtime_min", "director", "cast_names", "production", "overview", "poster_url",
        "tmdb_rating", "tmdb_votes", "rating_display", "streaming_in", "streaming_us", "rent_buy_us", "watch_link_in",
        "watch_link_us", "imdb_id", "tmdb_id", "wikidata_id", "wikipedia_url", "source", "seasons", "episodes", "network",
        "last_air_date", "series_status", "creators", "tmdb_checked_at"]
INTS = {"year", "runtime_min", "tmdb_votes", "tmdb_id", "seasons", "episodes"}
TYPES = {"movie", "short", "animated", "tv", "anime", "tv_film", "documentary", "series"}

def load(path):
    try: d = pd.read_csv(path, low_memory=False)
    except pd.errors.EmptyDataError: return set(), 0
    if d.empty: return set(), 0
    d = d.rename(columns={"cast": "cast_names"})
    cols = [c for c in COLS if c in d.columns]
    d = d[cols].drop_duplicates("title_id").astype(object).where(d[cols].notna(), None)
    if "type" in d: d["type"] = [t if t in TYPES else "movie" for t in d["type"]]
    sql = f"insert or ignore into titles ({', '.join(cols)}) values ({', '.join('?' * len(cols))})"
    rows = d.to_dict("records")
    for i in range(0, len(rows), 250):
        stmts = []
        for r in rows[i:i + 250]:
            args = []
            for c in cols:
                v = r[c]
                if c in INTS and v is not None:
                    try: v = int(float(v))
                    except ValueError: v = None
                args.append(v)
            stmts.append((sql, args))
        execute(stmts)
    return set(d["industry"].dropna()), len(rows)

if __name__ == "__main__":
    targets = [f"out/{s}.csv" for s in sys.argv[1:]] or sorted(glob.glob("out/*.csv"))
    touched = set()
    for p in targets:
        inds, n = load(p); touched |= inds
        print(f"{os.path.basename(p)}: sent {n} rows", flush=True)
    for ind in sorted(touched): refresh_stats(ind)
    print("year counts refreshed for:", ", ".join(sorted(touched)) or "nothing")
