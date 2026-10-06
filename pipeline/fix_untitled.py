"""Replace titles that are only a Wikidata ID (e.g. Q140589630) with the item's real name from Wikidata. Resumable."""
import requests, time, sys
from concurrent.futures import ThreadPoolExecutor
from turso_client import query, execute
UA = {"User-Agent": "PujiverseFilmDB/0.4 (https://movies-pujiverse.vercel.app)"}
PREF = {"tollywood":"te","bollywood":"hi","kollywood":"ta","mollywood":"ml","sandalwood":"kn","bengali-tollywood":"bn","marathi":"mr",
        "pollywood":"pa","dhollywood":"gu","ollywood":"or","jollywood":"as","china":"zh","hongkong":"zh","taiwan":"zh","korea":"ko","japan":"ja",
        "thailand":"th","russia":"ru","france":"fr","germany":"de","italy":"it","spain":"es","mexico":"es","argentina":"es","brazil":"pt",
        "poland":"pl","czechia":"cs","turkey":"tr","iran":"fa","egypt":"ar","greece":"el","sweden":"sv","norway":"nb","denmark":"da","finland":"fi",
        "indonesia":"id","vietnam":"vi","philippines":"tl","israel":"he","romania":"ro","lollywood":"ur","dhallywood":"bn","nepal":"ne"}
rows = query("select title_id, industry, wikidata_id, title_local, original_title from titles where title glob 'Q[0-9]*' and title not glob '*[^0-9Q]*'")
print("to fix:", len(rows), flush=True)
qid = {r["title_id"]: str(r["wikidata_id"] or "").split(",")[0].strip() for r in rows}
ids = sorted({q for q in qid.values() if q.startswith("Q")})
S = requests.Session(); S.headers.update(UA)
def fetch(chunk):
    for i in range(4):
        try:
            r = S.get("https://www.wikidata.org/w/api.php", params={"action":"wbgetentities","ids":"|".join(chunk),"props":"labels","format":"json"}, timeout=60)
            if r.ok: return r.json().get("entities", {})
        except requests.RequestException: pass
        time.sleep(2 * (i + 1))
    return {}
def work(chunk_rows):
    chunk = sorted({qid[r["title_id"]] for r in chunk_rows if qid[r["title_id"]].startswith("Q")})
    ents = fetch(chunk) if chunk else {}
    stmts = []
    for r in chunk_rows:
        lab = ents.get(qid[r["title_id"]], {}).get("labels", {})
        pref = PREF.get(r["industry"])
        pick = (lab.get("en") or lab.get("mul") or (lab.get(pref) if pref else None) or next(iter(lab.values()), None) or {}).get("value")
        name = pick or r["title_local"] or r["original_title"]
        if name and not (name.startswith("Q") and name[1:].isdigit()):
            stmts.append(("update titles set title = ? where title_id = ?", [name, r["title_id"]]))
    if stmts: execute(stmts)
    return len(stmts)
fixed = 0
with ThreadPoolExecutor(6) as ex:
    for i, n in enumerate(ex.map(work, [rows[i:i+50] for i in range(0, len(rows), 50)])):
        fixed += n
        if i % 40 == 0: print(f"batches {i}, fixed {fixed}", flush=True)
left = query("select count(*) n from titles where title glob 'Q[0-9]*' and title not glob '*[^0-9Q]*'")[0]["n"]
print(f"fixed {fixed}, still id-only {left}")
