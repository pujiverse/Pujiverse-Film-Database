"""
Language index: which titles are available in which language, and whether that is the original language.

Builds two tables in Turso:
  title_languages (lang, title_id, kind, is_original, via, orig_lang, year, release_date, votes)
      one row per film/series per language. `via` says how we know:
        original  the title's original language
        version   the same title is also listed under another industry in that language (a dubbed version)
        spoken    TMDB lists the language among the title's languages (multi-language or dubbed release)
  language_stats  (lang, kind, total, original)

Original language comes from TMDB (for titles listed under several industries), else the title's language
field, else the industry's language. The same film listed under several industries counts once per language.

  TURSO_URL, TURSO_TOKEN (full access) and TMDB_API_KEY in the environment / .env
  python build_languages.py
"""
import re, json, argparse
from concurrent.futures import ThreadPoolExecutor
from turso_client import query, execute
from enrich_watch import get

INDUSTRY_LANG = {
    "bollywood": "Hindi", "tollywood": "Telugu", "kollywood": "Tamil", "mollywood": "Malayalam", "sandalwood": "Kannada",
    "bengali-tollywood": "Bengali", "marathi": "Marathi", "pollywood": "Punjabi", "dhollywood": "Gujarati", "ollywood": "Odia",
    "jollywood": "Assamese", "bhojiwood": "Bhojpuri", "chhollywood": "Chhattisgarhi", "coastalwood": "Tulu", "konkani": "Konkani",
    "manipuri": "Manipuri", "rajasthani": "Rajasthani", "haryanvi": "Haryanvi", "lollywood": "Urdu", "dhallywood": "Bengali",
    "nepal": "Nepali", "srilanka": "Sinhala", "china": "Mandarin", "hongkong": "Cantonese", "taiwan": "Mandarin", "korea": "Korean",
    "japan": "Japanese", "thailand": "Thai", "philippines": "Tagalog", "indonesia": "Indonesian", "vietnam": "Vietnamese",
    "malaysia": "Malay", "hollywood": "English", "canada": "English", "mexico": "Spanish", "brazil": "Portuguese",
    "argentina": "Spanish", "colombia": "Spanish", "chile": "Spanish", "cuba": "Spanish", "uk": "English", "france": "French",
    "italy": "Italian", "germany": "German", "spain": "Spanish", "russia": "Russian", "denmark": "Danish", "sweden": "Swedish",
    "norway": "Norwegian", "finland": "Finnish", "iceland": "Icelandic", "poland": "Polish", "czechia": "Czech",
    "ireland": "English", "greece": "Greek", "romania": "Romanian", "nollywood": "English", "ghallywood": "English",
    "riverwood": "English", "bongowood": "Swahili", "southafrica": "English", "egypt": "Arabic", "turkey": "Turkish",
    "iran": "Persian", "israel": "Hebrew", "morocco": "Arabic", "australia": "English", "newzealand": "English"}

ALIAS = {"bangla": "Bengali", "standard chinese": "Mandarin", "chinese": "Mandarin", "mandarin chinese": "Mandarin",
         "yue chinese": "Cantonese", "filipino": "Tagalog", "egyptian arabic": "Arabic", "moroccan arabic": "Arabic",
         "levantine arabic": "Arabic", "modern standard arabic": "Arabic", "oriya": "Odia", "meitei": "Manipuri",
         "meitei language": "Manipuri", "farsi": "Persian", "persian (farsi)": "Persian", "norwegian bokmål": "Norwegian",
         "bokmål": "Norwegian", "flemish": "Dutch", "brazilian portuguese": "Portuguese", "american english": "English",
         "british english": "English", "castilian spanish": "Spanish", "mexican spanish": "Spanish", "swiss german": "German",
         "austrian german": "German", "no language": None, "": None, "xx": None, "zxx": None}
CODES = {}

def load_codes():
    for l in get("/configuration/languages") or []:
        CODES[l["iso_639_1"]] = l["english_name"]
    CODES.update({"zh": "Mandarin", "cn": "Cantonese", "or": "Odia", "tl": "Tagalog", "fil": "Tagalog", "no": "Norwegian",
                  "nb": "Norwegian", "bho": "Bhojpuri", "tcy": "Tulu", "kok": "Konkani", "mni": "Manipuri", "hne": "Chhattisgarhi",
                  "raj": "Rajasthani", "bgc": "Haryanvi", "fa": "Persian", "he": "Hebrew", "ms": "Malay", "bn": "Bengali"})

def norm(x):
    x = (x or "").strip()
    if not x: return None
    if re.fullmatch(r"[a-z]{2,3}", x): x = CODES.get(x, x)
    k = x.lower()
    if k in ALIAS: return ALIAS[k]
    if len(x) <= 3: return None          # unknown code
    return x[:1].upper() + x[1:]

def kind(t): return "film" if t in ("movie", "tv_film", "animated") else "series" if t == "series" else "other"

def load_titles():
    rows, last = [], ""
    while True:
        page = query("""select title_id, type, industry, language, languages, tmdb_id, year, release_date, coalesce(tmdb_votes, 0) votes
                        from titles where title_id > ? order by title_id limit 5000""", [last])
        if not page: return rows
        rows += page; last = page[-1]["title_id"]
        print(f"  read {len(rows)} titles", end="\r", flush=True)

def tmdb_original(key):
    typ, tid = key
    d = get(f"/{'tv' if typ == 'series' else 'movie'}/{tid}") or {}
    return key, CODES.get(d.get("original_language")) if d.get("original_language") else None

def main(threads):
    load_codes()
    rows = load_titles(); print(f"\n{len(rows)} titles", flush=True)
    groups = {}
    for r in rows:
        key = (r["type"], r["tmdb_id"]) if r["tmdb_id"] else ("id", r["title_id"])
        groups.setdefault(key, []).append(r)
    multi = [k for k, g in groups.items() if k[0] != "id" and len({r["industry"] for r in g}) > 1]
    print(f"{len(groups)} distinct titles, {len(multi)} listed under several industries: asking TMDB for their original language", flush=True)
    orig_tmdb = {}
    with ThreadPoolExecutor(threads) as ex:
        for k, lang in ex.map(tmdb_original, multi):
            if lang: orig_tmdb[k] = norm(lang)

    out = []
    for key, g in groups.items():
        ind_lang = {r["title_id"]: INDUSTRY_LANG.get(r["industry"]) for r in g}
        first = lambda r: norm((r["language"] or "").split(",")[0])
        orig = orig_tmdb.get(key)
        if not orig:
            # a single listing: its own language field, else its industry's language
            g_sorted = sorted(g, key=lambda r: (r["release_date"] or "9999", r["title_id"]))
            orig = next((first(r) for r in g_sorted if first(r)), None) or next((ind_lang[r["title_id"]] for r in g_sorted if ind_lang[r["title_id"]]), None)
        if not orig: continue
        langs = {orig: "original"}
        for r in g:
            il = ind_lang[r["title_id"]]
            if il and il not in langs: langs[il] = "version"
        for r in g:
            for x in ((r["languages"] or "") + "," + (r["language"] or "")).split(","):
                n = norm(x)
                if n and n not in langs: langs[n] = "spoken"
        for lang, via in langs.items():
            # show the listing made for that language when there is one, else the original-language listing
            rep = next((r for r in g if ind_lang[r["title_id"]] == lang), None) or next((r for r in g if ind_lang[r["title_id"]] == orig), None) or g[0]
            out.append((lang, rep["title_id"], kind(rep["type"]), 1 if via == "original" else 0, via, orig,
                        rep["year"], rep["release_date"], max(r["votes"] for r in g)))
    print(f"{len(out)} title-language rows", flush=True)

    execute([("drop table if exists title_languages_new", []), ("""create table title_languages_new (
        lang text not null, title_id text not null, kind text not null, is_original integer not null, via text not null,
        orig_lang text, year integer, release_date text, votes integer, primary key (lang, title_id)) without rowid""", [])])
    stmts = []
    for i in range(0, len(out), 80):
        chunk = out[i:i + 80]
        stmts.append((f"insert or replace into title_languages_new values {','.join(['(?,?,?,?,?,?,?,?,?)'] * len(chunk))}", [v for row in chunk for v in row]))
    def put(batch): execute(batch)
    batches = [stmts[i:i + 25] for i in range(0, len(stmts), 25)]
    with ThreadPoolExecutor(4) as ex:
        for n, _ in enumerate(ex.map(put, batches), 1):
            if n % 20 == 0: print(f"  wrote {min(n * 25 * 80, len(out))}/{len(out)}", flush=True)
    execute([
        ("drop table if exists title_languages", []),
        ("alter table title_languages_new rename to title_languages", []),
        ("create index if not exists tl_votes on title_languages (lang, kind, votes desc)", []),
        ("create index if not exists tl_date on title_languages (lang, kind, release_date desc)", []),
        ("drop table if exists language_stats", []),
        ("""create table language_stats as select lang, kind, count(*) total, sum(is_original) original
            from title_languages group by lang, kind""", []),
    ])
    print("language index rebuilt", flush=True)

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--threads", type=int, default=24)
    main(ap.parse_args().threads)
