"""
Find posters for titles that have none, from free sources, then save them to Turso.

Sources, in order:
  1. Wikidata (query service): "film poster" (P3383) or "image" (P18) on Wikimedia Commons, matched by the
     title's Wikidata id or its IMDb id. Commons files are freely licensed.
  2. TMDB images: any language's poster for titles that have a TMDB id but no main poster.
  3. TMDB find: titles that only have an IMDb id.
  4. TMDB search: titles with no ids, matched strictly by title + year (+ original language for Indian industries).
  5. Wikipedia: the infobox image of the film's article (English, else the industry's own language). Slow, because
     Wikipedia rate-limits busy IPs; run it on its own with --only wikipedia.
A real poster (TMDB, Wikidata "film poster", Wikipedia infobox) always replaces a Commons photo found earlier.

Collecting only reads the catalog, so the read-only token works. Saving needs the full-access token.

  TURSO_URL, TURSO_TOKEN and TMDB_API_KEY in the environment / .env
  python fill_posters.py collect --out posters/            # resumable, writes posters/found.jsonl
  python fill_posters.py collect --out posters/ --only wikipedia   # slow; run separately
  python fill_posters.py save --out posters/               # applies found.jsonl (full-access token)
"""
import os, re, sys, json, time, argparse, unicodedata, threading
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher
from urllib.parse import quote
import requests
from turso_client import query, execute

UA = "PujiverseFilms/1.0 (https://cinema.pujiverse.com; poster lookup)"
TMDB = "https://api.themoviedb.org/3"
IMG = "https://image.tmdb.org/t/p/w500"
S = requests.Session(); S.headers["User-Agent"] = UA
S.mount("https://", requests.adapters.HTTPAdapter(pool_connections=32, pool_maxsize=32))
LANG = {"bollywood": "hi", "tollywood": "te", "kollywood": "ta", "mollywood": "ml", "sandalwood": "kn", "bengali-tollywood": "bn",
        "marathi": "mr", "pollywood": "pa", "dhollywood": "gu", "ollywood": "or", "jollywood": "as", "bhojiwood": "bho"}
LOCK = threading.Lock()
RANK = {"tmdb": 4, "wikidata-poster": 3, "wikipedia": 2, "wikidata-image": 1}   # a real poster beats a Commons photo
GOOD = 2   # titles already holding a poster of at least this rank are not searched again

# ---------- catalog ----------
def missing():
    rows, last = [], ""
    while True:
        page = query("""select title_id, title, original_title, title_local, year, industry, type, tmdb_id, imdb_id from titles
                        where (poster_url is null or poster_url = '') and title_id > ? order by title_id limit 5000""", [last])
        if not page: return rows
        rows += page; last = page[-1]["title_id"]
        print(f"  catalog: {len(rows)} titles without a poster", end="\r", flush=True)

# ---------- output ----------
class Store:
    def __init__(self, out):
        os.makedirs(out, exist_ok=True)
        self.found_path, self.done_path = os.path.join(out, "found.jsonl"), os.path.join(out, "checked.jsonl")
        self.found, self.done = {}, set()
        for p, fn in ((self.found_path, self._keep),
                      (self.done_path, lambda d: self.done.add((d["phase"], d["title_id"])))):
            if os.path.exists(p):
                for line in open(p):
                    try: fn(json.loads(line))
                    except ValueError: pass
        self.ff, self.fd = open(self.found_path, "a"), open(self.done_path, "a")

    def _keep(self, d):
        old = self.found.get(d["title_id"])
        if not old or RANK.get(d["source"], 0) > RANK.get(old["source"], 0): self.found[d["title_id"]] = d; return True
        return False

    def has_good(self, title_id):
        d = self.found.get(title_id)
        return bool(d) and RANK.get(d["source"], 0) >= GOOD

    def add(self, title_id, url, source, **extra):
        with LOCK:
            d = {"title_id": title_id, "poster_url": url, "source": source, **extra}
            if self._keep(d): self.ff.write(json.dumps(d) + "\n"); self.ff.flush()

    def checked(self, phase, ids):
        with LOCK:
            for i in ids:
                if (phase, i) not in self.done:
                    self.done.add((phase, i)); self.fd.write(json.dumps({"phase": phase, "title_id": i}) + "\n")
            self.fd.flush()

# ---------- 1. Wikidata ----------
def sparql(q):
    for i in range(6):
        try:
            r = S.post("https://query.wikidata.org/sparql", data={"query": q}, headers={"Accept": "application/sparql-results+json"}, timeout=90)
            if r.status_code == 200: return r.json()["results"]["bindings"]
            time.sleep(int(r.headers.get("retry-after", 5 * (i + 1))))
        except (requests.RequestException, ValueError): time.sleep(5 * (i + 1))
    return None

def commons(file_url):
    name = file_url.rsplit("/", 1)[-1]   # .../Special:FilePath/Some%20File.jpg
    return f"https://commons.wikimedia.org/wiki/Special:FilePath/{name}?width=500"

def wikidata_phase(rows, st):
    by_q, by_imdb = {}, {}
    for r in rows:
        if st.has_good(r["title_id"]) or ("wikidata", r["title_id"]) in st.done: continue
        m = re.search(r"-(Q\d+)$", r["title_id"])
        if m: by_q.setdefault(m.group(1), []).append(r["title_id"])
        elif r.get("imdb_id"): by_imdb.setdefault(r["imdb_id"], []).append(r["title_id"])
    print(f"\nwikidata: {len(by_q)} Wikidata ids, {len(by_imdb)} IMDb ids to look up", flush=True)
    hits = 0

    def pick(b):
        if "poster" in b: return commons(b["poster"]["value"]), "wikidata-poster"
        if "image" in b: return commons(b["image"]["value"]), "wikidata-image"
        return None, None

    qs = list(by_q)
    for i in range(0, len(qs), 300):
        chunk = qs[i:i + 300]
        res = sparql("SELECT ?item ?poster ?image WHERE { VALUES ?item { %s } OPTIONAL { ?item wdt:P3383 ?poster } OPTIONAL { ?item wdt:P18 ?image } }"
                     % " ".join("wd:" + q for q in chunk))
        if res is None: continue
        best = {}
        for b in res:
            q = b["item"]["value"].rsplit("/", 1)[-1]
            url, src = pick(b)
            if url and (q not in best or (src == "wikidata-poster" and best[q][1] != "wikidata-poster")): best[q] = (url, src)
        for q, (url, src) in best.items():
            for t in by_q.get(q, []): st.add(t, url, src); hits += 1
        st.checked("wikidata", [t for q in chunk for t in by_q[q]])
        print(f"wikidata ids: {min(i + 300, len(qs))}/{len(qs)}, posters found {hits}", flush=True)

    ims = list(by_imdb)
    for i in range(0, len(ims), 200):
        chunk = ims[i:i + 200]
        res = sparql('SELECT ?imdb ?poster ?image WHERE { VALUES ?imdb { %s } ?item wdt:P345 ?imdb . OPTIONAL { ?item wdt:P3383 ?poster } OPTIONAL { ?item wdt:P18 ?image } }'
                     % " ".join(f'"{x}"' for x in chunk if re.fullmatch(r"tt\d+", x)))
        if res is None: continue
        for b in res:
            url, src = pick(b)
            if url:
                for t in by_imdb.get(b["imdb"]["value"], []): st.add(t, url, src); hits += 1
        st.checked("wikidata", [t for x in chunk for t in by_imdb[x]])
        print(f"wikidata imdb: {min(i + 200, len(ims))}/{len(ims)}, posters found {hits}", flush=True)

# ---------- 5. Wikipedia infobox images (slow: Wikipedia rate-limits shared IPs) ----------
WIKI = {"bollywood": "hi", "tollywood": "te", "kollywood": "ta", "mollywood": "ml", "sandalwood": "kn", "bengali-tollywood": "bn",
        "marathi": "mr", "pollywood": "pa", "dhollywood": "gu", "ollywood": "or", "jollywood": "as", "china": "zh", "hongkong": "zh",
        "taiwan": "zh", "korea": "ko", "japan": "ja", "thailand": "th", "indonesia": "id", "vietnam": "vi", "france": "fr", "italy": "it",
        "germany": "de", "spain": "es", "russia": "ru", "mexico": "es", "argentina": "es", "brazil": "pt", "turkey": "tr", "iran": "fa",
        "egypt": "ar", "poland": "pl", "sweden": "sv", "denmark": "da", "norway": "no", "finland": "fi", "czechia": "cs", "greece": "el",
        "romania": "ro", "lollywood": "ur", "dhallywood": "bn", "nepal": "ne", "srilanka": "si", "israel": "he", "philippines": "tl"}

def wiki_get(host, titles):
    for i in range(12):
        try:
            r = S.get(f"https://{host}/w/api.php", params={"action": "query", "format": "json", "redirects": 1, "prop": "pageimages",
                      "piprop": "thumbnail", "pithumbsize": 500, "titles": "|".join(titles)}, timeout=60)
            if r.status_code == 200: return r.json().get("query", {})
            time.sleep(int(r.headers.get("retry-after", 20)) + 1)
        except (requests.RequestException, ValueError): time.sleep(10)
    return None

def wikipedia_phase(rows, st):
    todo = {}
    for r in rows:
        m = re.search(r"-(Q\d+)$", r["title_id"])
        if m and not st.has_good(r["title_id"]) and ("wikipedia", r["title_id"]) not in st.done:
            todo.setdefault(m.group(1), []).append(r)
    qs = list(todo)
    print(f"\nwikipedia: {len(qs)} Wikidata ids to map to articles", flush=True)
    found = 0
    for i in range(0, len(qs), 300):
        chunk = qs[i:i + 300]
        res = sparql("SELECT ?item ?article WHERE { VALUES ?item { %s } ?article schema:about ?item . }" % " ".join("wd:" + q for q in chunk)) or []
        links = {}
        for b in res:
            q, a = b["item"]["value"].rsplit("/", 1)[-1], b["article"]["value"]
            m = re.match(r"https://([a-z-]+)\.wikipedia\.org/wiki/(.+)", a)
            if m: links.setdefault(q, {})[m.group(1)] = requests.utils.unquote(m.group(2)).replace("_", " ")
        per_host = {}
        for q in chunk:
            l, ind = links.get(q, {}), todo[q][0]["industry"]
            for lang in ("en", WIKI.get(ind)):
                if lang and lang in l:
                    per_host.setdefault(f"{lang}.wikipedia.org", {}).setdefault(l[lang], []).append(q); break
        for host, titles in per_host.items():
            names = list(titles)
            for j in range(0, len(names), 50):
                part = names[j:j + 50]
                res = wiki_get(host, part)
                if res is None: continue
                alias = {n["to"]: n["from"] for n in res.get("normalized", []) + res.get("redirects", [])}
                for page in res.get("pages", {}).values():
                    url = (page.get("thumbnail") or {}).get("source")
                    t = page.get("title"); orig = alias.get(t, t); orig = alias.get(orig, orig)
                    if url and not url.lower().endswith((".svg.png",)):
                        for q in titles.get(orig, titles.get(t, [])):
                            for r in todo[q]: st.add(r["title_id"], url, "wikipedia"); found += 1
                time.sleep(1)
        st.checked("wikipedia", [r["title_id"] for q in chunk for r in todo[q]])
        print(f"wikipedia: {min(i + 300, len(qs))}/{len(qs)} ids, posters found {found}", flush=True)

# ---------- 2-4. TMDB ----------
KEY = os.environ.get("TMDB_API_KEY")

def tmdb(path, **p):
    p["api_key"] = KEY
    for i in range(5):
        try:
            r = S.get(TMDB + path, params=p, timeout=30)
            if r.status_code == 429: time.sleep(1 + 2 * i); continue
            if r.status_code == 404: return None
            if r.ok: return r.json()
        except requests.RequestException: time.sleep(1 + i)
    return None

def best_poster(posters, lang):
    if not posters: return None
    rank = lambda p: (p.get("iso_639_1") in (lang, "en", None), p.get("vote_count", 0), p.get("width", 0))
    return IMG + max(posters, key=rank)["file_path"]

def norm(t):
    t = unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", re.sub(r"\(.*?\)", "", t))

def tmdb_one(r, phase, st):
    kind = "tv" if r["type"] == "series" else "movie"
    lang = LANG.get(r["industry"])
    try:
        if phase == "tmdb-images":
            d = tmdb(f"/{kind}/{r['tmdb_id']}/images") or {}
            url = best_poster(d.get("posters"), lang)
            if url: st.add(r["title_id"], url, "tmdb")
        elif phase == "tmdb-find":
            f = tmdb(f"/find/{r['imdb_id']}", external_source="imdb_id") or {}
            hits = (f.get("tv_results") if kind == "tv" else f.get("movie_results")) or f.get("movie_results") or f.get("tv_results") or []
            if hits:
                h = hits[0]
                url = IMG + h["poster_path"] if h.get("poster_path") else best_poster((tmdb(f"/{kind}/{h['id']}/images") or {}).get("posters"), lang)
                if url: st.add(r["title_id"], url, "tmdb", tmdb_id=h["id"])
        elif phase == "tmdb-search" and r.get("year") and r.get("title"):
            want = {norm(r["title"]), norm(r.get("original_title")), norm(r.get("title_local"))} - {""}
            params = {"query": r["title"], ("first_air_date_year" if kind == "tv" else "primary_release_year"): r["year"]}
            for c in ((tmdb(f"/search/{kind}", **params) or {}).get("results") or [])[:5]:
                got = {norm(c.get("title") or c.get("name")), norm(c.get("original_title") or c.get("original_name"))} - {""}
                if lang and c.get("original_language") != lang: continue
                if c.get("poster_path") and any(a == b or SequenceMatcher(None, a, b).ratio() >= 0.92 for a in want for b in got):
                    st.add(r["title_id"], IMG + c["poster_path"], "tmdb", tmdb_id=c["id"]); break
    except Exception as e:
        print("err", r["title_id"], str(e)[:100], flush=True); return
    st.checked(phase, [r["title_id"]])

def tmdb_phase(rows, st, phase, threads):
    if not KEY: print(f"{phase}: skipped (set TMDB_API_KEY)"); return
    pick = {"tmdb-images": lambda r: r.get("tmdb_id"),
            "tmdb-find": lambda r: not r.get("tmdb_id") and r.get("imdb_id"),
            "tmdb-search": lambda r: not r.get("tmdb_id") and not r.get("imdb_id")}[phase]
    todo = [r for r in rows if pick(r) and not st.has_good(r["title_id"]) and (phase, r["title_id"]) not in st.done]
    print(f"\n{phase}: {len(todo)} titles", flush=True)
    good = lambda: sum(1 for t in st.found.values() if t["source"] == "tmdb")
    before = good()
    with ThreadPoolExecutor(threads) as ex:
        for i, _ in enumerate(ex.map(lambda r: tmdb_one(r, phase, st), todo), 1):
            if i % 2000 == 0: print(f"{phase}: {i}/{len(todo)}, posters found {good() - before}", flush=True)
    print(f"{phase}: done, posters found {good() - before}", flush=True)

# ---------- save ----------
def save(st):
    rows = list(st.found.values())
    print(f"saving {len(rows)} posters", flush=True)
    sql = """update titles set poster_url = ?, tmdb_id = coalesce(tmdb_id, ?)
             where title_id = ? and (poster_url is null or poster_url = '')"""
    for i in range(0, len(rows), 300):
        execute([(sql, [r["poster_url"], r.get("tmdb_id"), r["title_id"]]) for r in rows[i:i + 300]])
        if i % 15000 == 0: print(f"  saved {i + len(rows[i:i + 300])}/{len(rows)}", flush=True)
    print("saved", flush=True)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["collect", "save"])
    ap.add_argument("--out", default="posters")
    ap.add_argument("--only", choices=["wikidata", "tmdb-images", "tmdb-find", "tmdb-search", "wikipedia"])
    ap.add_argument("--threads", type=int, default=16)
    ap.add_argument("--merge", nargs="*", default=[], help="save: also take posters from these other --out folders")
    a = ap.parse_args()
    st = Store(a.out)
    if a.action == "save":
        for extra in a.merge:
            for d in Store(extra).found.values(): st._keep(d)
        save(st); sys.exit()
    rows = missing()
    print(f"\n{len(rows)} titles without a poster, {len(st.found)} already found", flush=True)
    for ph in ([a.only] if a.only else ["wikidata", "tmdb-images", "tmdb-find", "tmdb-search"]):
        if ph == "wikidata": wikidata_phase(rows, st)
        elif ph == "wikipedia": wikipedia_phase(rows, st)
        else: tmdb_phase(rows, st, ph, a.threads)
    print(f"\nall done: {len(st.found)} posters found in total -> {st.found_path}", flush=True)
