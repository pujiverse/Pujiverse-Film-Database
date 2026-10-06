"""Run: TURSO_URL=... TURSO_TOKEN=<full access> python wiki_dates.py
Backfill exact release dates from Wikipedia 'List of <Language> films of <YEAR>' pages (Opening month/day columns)."""
import re, io, sys, time, datetime, unicodedata
from difflib import SequenceMatcher
import requests, pandas as pd
from turso_client import query, execute
UA = {"User-Agent": "PujiverseFilmDB/0.4 (https://movies-pujiverse.vercel.app)"}
LANGS = {"tollywood": "Telugu", "bollywood": "Hindi", "kollywood": "Tamil", "mollywood": "Malayalam", "sandalwood": "Kannada",
         "marathi": "Marathi", "bengali-tollywood": "Bengali", "pollywood": "Punjabi"}
MONTHS = {m: i for i, m in enumerate(["jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"], 1)}
def norm(t):
    t = unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", re.sub(r"\(.*?\)", "", t))
def page_dates(lang, year):
    r = requests.get(f"https://en.wikipedia.org/wiki/List_of_{lang}_films_of_{year}", headers=UA, timeout=60)
    if r.status_code != 200: return []
    try: tables = pd.read_html(io.StringIO(r.text))
    except Exception: return []
    out = []
    for t in tables:
        cols = [str(c) for c in t.columns]; t.columns = cols
        if "Title" not in cols or "Opening" not in cols: continue
        day_col = "Opening.1" if "Opening.1" in cols else None
        for _, x in t.iterrows():
            mon = MONTHS.get(re.sub(r"[^a-z]", "", str(x["Opening"]).lower())[:3])
            try: day = int(float(str(x.get(day_col, "")).strip())) if day_col else None
            except ValueError: day = None
            if not mon or not day: continue
            try: d = datetime.date(year, mon, day).isoformat()
            except ValueError: continue
            title = re.sub(r"\[.*?\]", "", str(x["Title"])).strip()
            if title and title.lower() != "nan": out.append((title, d))
    return out
if __name__ == "__main__":
    total = 0
    for slug, lang in LANGS.items():
        for year in range(2000, 2027):
            found = page_dates(lang, year)
            if not found: continue
            rows = query("select title_id, title, title_local, original_title from titles where industry = ? and year = ? and type <> 'series' "
                         "and (release_date is null or substr(release_date, 6) = '01-01')", [slug, year])
            if not rows: continue
            keys = [(r["title_id"], {norm(r["title"]), norm(r["title_local"]), norm(r["original_title"])} - {""}) for r in rows]
            stmts, used = [], set()
            for title, d in found:
                n = norm(title)
                if not n: continue
                best = None
                for tid, ks in keys:
                    if tid in used: continue
                    if n in ks: best = tid; break
                    if any(SequenceMatcher(None, n, k).ratio() >= 0.9 for k in ks): best = best or tid
                if best:
                    used.add(best); stmts.append(("update titles set release_date = ? where title_id = ?", [d, best]))
            for i in range(0, len(stmts), 200): execute(stmts[i:i + 200])
            total += len(stmts)
            print(f"{slug} {year}: {len(found)} dated on Wikipedia, {len(rows)} undated here, filled {len(stmts)}", flush=True)
            time.sleep(0.2)
    print("total dates filled:", total)
