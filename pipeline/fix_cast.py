"""
Repair cast_names in the Turso catalog. Dry run by default: writes fix_cast_preview.csv and changes nothing.
  TURSO_URL, TURSO_TOKEN and TMDB_API_KEY in the environment / .env
  python fix_cast.py tollywood                 # preview one industry
  python fix_cast.py tollywood --apply         # write (needs a full-access TURSO_TOKEN)
Two problems it fixes:
  1. Names run together with no separator ("Pawan KalyanEmraan Hashmi"), from Wikipedia lists parsed without
     delimiters. With a TMDB id: replaced by TMDB's billed cast. Without: split at lowercase->Capital joins.
  2. Leads buried (Wikidata P161 has no billing order). Rows with a TMDB id whose top-billed actor is missing
     from our first 3 names get TMDB's billed cast (top 12, in billing order).
"""
import os, re, sys, csv, time, argparse, unicodedata
from concurrent.futures import ThreadPoolExecutor
import requests
from turso_client import query, execute

KEY = os.environ.get("TMDB_API_KEY") or sys.exit("Set TMDB_API_KEY")
S = requests.Session()
GLUE = re.compile(r"(?<![MD]c)(?<!Mac)(?<=[a-z]{2})(?=[A-Z][a-z])")   # "KalyanEmraan" -> "Kalyan|Emraan"; keeps McCord, MacDonald

def tmdb_cast(tid):
    for i in range(4):
        try:
            r = S.get(f"https://api.themoviedb.org/3/movie/{tid}/credits", params={"api_key": KEY}, timeout=30)
            if r.status_code == 429: time.sleep(1 + 2 * i); continue
            if r.status_code == 404: return None
            if r.ok: return [c["name"] for c in sorted(r.json().get("cast", []), key=lambda c: c["order"])]
        except requests.RequestException: time.sleep(1)
    return None

def words(s):
    return set(re.sub(r"[^a-z ]", " ", unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()).split())

def same(a, b):
    A, B = words(a), words(b)
    return bool(A and B) and (A <= B or B <= A or len(A & B) >= 2)

def glued(c):
    return "," not in c and " " in c and bool(GLUE.search(c))

def plan(r):
    cur = r["cast_names"]
    ours = [n.strip() for n in cur.split(",") if n.strip()]
    if r["tmdb_id"]:
        t = tmdb_cast(r["tmdb_id"])
        if t:
            if glued(cur): return "glued->tmdb", ", ".join(t[:12])
            if not any(same(t[0], o) for o in ours[:3]):
                # keep our list if TMDB's lead is not in it at all and the lists share nobody (likely a wrong TMDB match)
                if not any(same(x, o) for x in t[:5] for o in ours): return None
                return "lead-buried->tmdb", ", ".join(t[:12])
            return None
    if glued(cur): return "glued->split", ", ".join(GLUE.split(cur))
    return None

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("industries", nargs="*"); ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    where = "type <> 'series' and cast_names is not null" + (f" and industry in ({','.join('?' * len(a.industries))})" if a.industries else "")
    rows = query(f"select title_id, title, year, tmdb_id, cast_names from titles where {where}", a.industries)
    rows = [r for r in rows if r["tmdb_id"] or glued(r["cast_names"])]
    print(f"{len(rows)} rows to check", flush=True)
    with ThreadPoolExecutor(8) as ex: plans = list(ex.map(plan, rows))
    todo = [(r, p) for r, p in zip(rows, plans) if p and p[1] != r["cast_names"]]
    with open("fix_cast_preview.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["title_id", "title", "year", "fix", "old", "new"])
        for r, (kind, new) in todo: w.writerow([r["title_id"], r["title"], r["year"], kind, r["cast_names"], new])
    kinds = {}
    for _, (k, _) in todo: kinds[k] = kinds.get(k, 0) + 1
    print("planned:", kinds, "-> fix_cast_preview.csv")
    if a.apply:
        stmts = [("update titles set cast_names = ? where title_id = ? and cast_names = ?", [new, r["title_id"], r["cast_names"]])
                 for r, (_, new) in todo]
        for i in range(0, len(stmts), 200): execute(stmts[i:i + 200])
        print(f"updated {len(stmts)} rows")
