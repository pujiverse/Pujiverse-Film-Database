"""
Add films that Wikidata is missing, from Wikipedia "List of <X> films of <YEAR>" pages.
  python wiki_fill.py bhojiwood chhollywood ...
Writes out/<slug>_wiki.csv with only the NEW films (not already in out/<slug>.csv).
"""
import sys, re, io, time, datetime, unicodedata
import requests, pandas as pd
from difflib import SequenceMatcher

UA = {"User-Agent": "PujiverseFilmDB/0.3 (https://pujiverse.com; contact: pujiverse films project)"}
S = requests.Session(); S.headers.update(UA)
# industry -> Wikipedia list prefixes
PREFIX = {
    "bollywood": ["List of Hindi films of"], "kollywood": ["List of Tamil films of"],
    "mollywood": ["List of Malayalam films of"], "sandalwood": ["List of Kannada films of"],
    "bengali-tollywood": ["List of Bengali films of"], "marathi": ["List of Marathi films of"],
    "pollywood": ["List of Punjabi films of"], "dhollywood": ["List of Gujarati films of"],
    "ollywood": ["List of Odia films of", "List of Ollywood films of"], "jollywood": ["List of Assamese films of"],
    "bhojiwood": ["List of Bhojpuri films"], "chhollywood": ["List of Chhattisgarhi films"],
    "coastalwood": ["List of Tulu films"], "haryanvi": ["List of Haryanvi"], "rajasthani": ["List of Rajasthani films"],
    "konkani": ["List of Konkani films"], "manipuri": ["List of Meitei-language films", "List of Manipuri films"],
    "lollywood": ["List of Pakistani films of"], "dhallywood": ["List of Bangladeshi films of"],
    "nepal": ["List of Nepali films"], "srilanka": ["List of Sri Lankan films of", "List of Sinhala films of"],
    "nollywood": ["List of Nigerian films of"], "ghallywood": ["List of Ghanaian films"],
}
MONTHS = {m: i for i, m in enumerate(["jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"], 1)}

def norm(t):
    t = unicodedata.normalize("NFKD", str(t)).encode("ascii", "ignore").decode().lower()
    t = re.sub(r"\(.*?\)", "", t)
    return re.sub(r"[^a-z0-9]", "", t)

def clean(v):
    if v is None or (isinstance(v, float) and pd.isna(v)): return None
    v = re.sub(r"\[.*?\]", "", str(v)).strip()
    return v if v and v.lower() not in ("nan", "—", "-", "tba") else None

def pages_for(prefix):
    r = S.get("https://en.wikipedia.org/w/api.php", params={"action": "query", "list": "prefixsearch",
              "pssearch": prefix, "pslimit": 500, "format": "json"}, timeout=60).json()
    return [x["title"] for x in r["query"]["prefixsearch"] if x["title"].lower().startswith(prefix.lower())]

def year_of(title):
    m = re.search(r"(1[89]\d\d|20\d\d)(?:s)?$", title.strip())
    return int(m.group(1)) if m else None

def scrape(title):
    r = S.get("https://en.wikipedia.org/w/index.php", params={"title": title, "action": "render"}, timeout=60)
    if r.status_code != 200: return []
    html = re.sub(r"<br\s*/?>|</li>\s*<li[^>]*>", ", ", r.text)
    try: tables = pd.read_html(io.StringIO(html), flavor="lxml")
    except Exception: return []
    page_year = year_of(title); decade = title.strip().endswith("s")
    url = "https://en.wikipedia.org/wiki/" + title.replace(" ", "_")
    out = []
    for t in tables:
        if isinstance(t.columns, pd.MultiIndex): t.columns = [" ".join(str(x) for x in c if "Unnamed" not in str(x)) for c in t.columns]
        cols = {str(c).strip(): c for c in t.columns}
        tcol = next((cols[c] for c in cols if c.lower() in ("title", "film", "name", "movie", "film title")), None)
        if tcol is None or any("gross" in c.lower() for c in cols): continue
        dcol = next((cols[c] for c in cols if c.lower().startswith("director")), None)
        ccol = next((cols[c] for c in cols if c.lower() in ("cast", "starring", "actors")), None)
        gcol = next((cols[c] for c in cols if c.lower() == "genre"), None)
        ycol = next((cols[c] for c in cols if c.lower() in ("year", "release year")), None)
        rcol = next((cols[c] for c in cols if c.lower().startswith("release") and "year" not in c.lower()), None)
        for _, x in t.iterrows():
            ti = clean(x[tcol])
            if not ti or len(ti) > 120: continue
            y = page_year if not decade else None
            if ycol is not None:
                m = re.search(r"(1[89]\d\d|20\d\d)", str(x[ycol])); y = int(m.group(1)) if m else y
            date = None
            if rcol is not None:
                try:
                    dt = pd.to_datetime(clean(x[rcol]), errors="coerce")
                    if pd.notna(dt) and (y is None or dt.year == y): date = dt.date().isoformat(); y = dt.year
                except Exception: pass
            if y is None and rcol is not None:
                m = re.search(r"(1[89]\d\d|20\d\d)", str(x[rcol])); y = int(m.group(1)) if m else None
            out.append({"title": ti, "year": y, "release_date": date, "director": clean(x[dcol]) if dcol is not None else None,
                        "cast": clean(x[ccol]) if ccol is not None else None, "genre": clean(x[gcol]) if gcol is not None else None,
                        "wikipedia_url": url})
    return out

def fill(slug):
    try: base = pd.read_csv(f"out/{slug}.csv", low_memory=False)
    except FileNotFoundError: base = pd.DataFrame(columns=["title", "year", "original_title", "title_local"])
    keys = {}
    for _, r in base.iterrows():
        for t in (r.get("title"), r.get("original_title")):
            if isinstance(t, str): keys.setdefault(int(r.year) if pd.notna(r.year) else None, set()).add(norm(t))
    pages = []
    for p in PREFIX.get(slug, []): pages += [t for t in pages_for(p) if "film" in t.lower() and "director" not in t.lower()]
    pages = list(dict.fromkeys(pages))
    found = []
    for p in pages:
        found += scrape(p); time.sleep(0.2)
    new, seen = [], set()
    for f in found:
        n = norm(f["title"])
        if not n or (n, f["year"]) in seen: continue
        seen.add((n, f["year"]))
        pool = keys.get(f["year"], set()) | (keys.get(None, set()))
        if n in pool or any(SequenceMatcher(None, n, k).ratio() >= 0.88 for k in pool): continue
        if f["year"] is not None:   # also tolerate a one-year release mismatch
            near = keys.get(f["year"] - 1, set()) | keys.get(f["year"] + 1, set())
            if n in near: continue
        new.append(f)
    df = pd.DataFrame(new)
    if len(df):
        df["title_id"] = [f"{slug}-wp-{(y or 0)}-{norm(t)[:50]}" for t, y in zip(df.title, df.year)]
        df = df.drop_duplicates("title_id")
        df["industry"] = slug; df["type"] = "movie"; df["source"] = "wikipedia"
    df.to_csv(f"out/{slug}_wiki.csv", index=False)
    print(f"{slug}: {len(pages)} Wikipedia pages, {len(found)} rows, {len(df)} new films", flush=True)

if __name__ == "__main__":
    for s in sys.argv[1:]: fill(s)
