"""
Upload pipeline output (out/*.csv) into the Supabase `titles` table.

  export SUPABASE_URL=https://<project-ref>.supabase.co
  export SUPABASE_SERVICE_ROLE_KEY=<service role key>   # server-side only, never commit or ship to a browser
  python load_to_supabase.py                 # every CSV in out/
  python load_to_supabase.py bollywood kollywood_wiki

Existing rows are left untouched (insert-or-ignore on title_id), so reruns are safe.
"""
import os, sys, glob, json
import requests, pandas as pd

URL = os.environ.get("SUPABASE_URL") or sys.exit("Set SUPABASE_URL")
KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or sys.exit("Set SUPABASE_SERVICE_ROLE_KEY")
H = {"apikey": KEY, "Authorization": f"Bearer {KEY}", "Content-Type": "application/json",
     "Prefer": "resolution=ignore-duplicates,return=minimal"}
COLS = ["title_id", "title", "title_local", "title_telugu", "original_title", "industry", "language", "type", "status",
        "release_date", "year", "genre", "runtime_min", "director", "cast", "production", "overview", "poster_url",
        "tmdb_rating", "tmdb_votes", "rating_display", "streaming_in", "streaming_us", "rent_buy_us",
        "imdb_id", "tmdb_id", "wikidata_id", "wikipedia_url", "source"]

def load(path):
    try: d = pd.read_csv(path, low_memory=False)
    except pd.errors.EmptyDataError: return 0
    if d.empty: return 0
    d = d[[c for c in COLS if c in d.columns]].copy()
    for c in ("year", "runtime_min", "tmdb_votes", "tmdb_id"):
        if c in d: d[c] = pd.to_numeric(d[c], errors="coerce").round().astype("Int64")
    if "runtime_min" in d: d.loc[d.runtime_min > 2000, "runtime_min"] = pd.NA
    d["status"] = d.get("status", pd.Series(index=d.index, dtype=object))
    d["user_rating_count"] = 0
    d["status"] = [s if s in ("released", "upcoming", "unknown") else ("released" if pd.notna(y) else "unknown")
                   for s, y in zip(d.status, d.get("year", [None] * len(d)))]
    if "type" in d: d["type"] = d["type"].where(d["type"].isin(["movie", "short", "animated", "tv", "anime", "tv_film", "documentary"]), "movie")
    rows = json.loads(d.drop_duplicates("title_id").to_json(orient="records"))
    for i in range(0, len(rows), 300):
        r = requests.post(f"{URL}/rest/v1/titles?on_conflict=title_id", headers=H, json=rows[i:i + 300], timeout=180)
        r.raise_for_status()
    return len(rows)

if __name__ == "__main__":
    targets = [f"out/{s}.csv" for s in sys.argv[1:]] or sorted(glob.glob("out/*.csv"))
    for p in targets:
        print(f"{os.path.basename(p)}: sent {load(p)} rows", flush=True)
    for ind in sorted({os.path.basename(p)[:-4].replace("_series", "").replace("_wiki", "") for p in targets}):
        r = requests.post(f"{URL}/rest/v1/rpc/refresh_industry_stats", headers=H, json={"p_industry": ind}, timeout=300)
        r.raise_for_status()
    print("year stats refreshed")
