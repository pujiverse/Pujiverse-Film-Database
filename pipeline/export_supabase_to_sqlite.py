import requests, sqlite3, time, json, sys
B="https://oxlgnckdwqnitfakvspr.supabase.co/rest/v1/"; K="sb_publishable_ofHABj2WJ0YrfIQfje-f4g_3Frgw0Q2"
H={"apikey":K,"Authorization":f"Bearer {K}"}
COLS=["title_id","title","title_local","title_telugu","original_title","industry","language","type","status","release_date","year",
 "genre","runtime_min","director","cast","production","overview","poster_url","tmdb_rating","tmdb_votes","rating_display",
 "streaming_in","streaming_us","rent_buy_us","watch_link_in","watch_link_us","imdb_id","tmdb_id","wikidata_id","wikipedia_url",
 "source","seasons","episodes","network","last_air_date","series_status","creators","tmdb_checked_at"]
db=sqlite3.connect("catalog.db")
db.execute(f"create table if not exists titles ({', '.join((c if c!='cast' else 'cast_names')+(' text primary key' if c=='title_id' else '') for c in COLS)})")
last=db.execute("select max(title_id) from titles").fetchone()[0] or ""
n=db.execute("select count(*) from titles").fetchone()[0]
sel=",".join('"cast"' if c=="cast" else c for c in COLS)
while True:
    for i in range(6):
        r=requests.get(B+"titles",params={"select":sel,"title_id":f"gt.{last}","order":"title_id","limit":"1000"},headers=H,timeout=90)
        if r.ok: break
        time.sleep(5*(i+1))
    rows=r.json()
    if not rows: break
    db.executemany(f"insert or replace into titles values ({','.join('?'*len(COLS))})",[[x.get(c) for c in COLS] for x in rows])
    db.commit(); n+=len(rows); last=rows[-1]["title_id"]
    if n % 20000 < 1000: print(n, flush=True)
print("done", n)
