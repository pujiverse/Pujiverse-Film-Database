"""
OTT / digital release dates for recent and upcoming films, from TMDB.

For each film released in the last N months (or still upcoming) that has a TMDB id, reads TMDB's release dates
and fills:
  digital_release_date / digital_country   earliest "Digital" release (TMDB type 4) in the film's home country,
                                           else India, else the US, else anywhere
  release_date                             the home-country theatrical date when we only had a year
  watch_regions, streaming_in/us, ...      where to watch now (data by JustWatch)

  TURSO_URL, TURSO_TOKEN (full access) and TMDB_API_KEY in the environment / .env
  python ott_dates.py                 # last 18 months + upcoming
  python ott_dates.py --months 36
"""
import os, sys, json, time, argparse, datetime
from concurrent.futures import ThreadPoolExecutor
from turso_client import query, execute
from enrich_watch import get, regions, HOME

INDIA = {"bollywood", "tollywood", "kollywood", "mollywood", "sandalwood", "bengali-tollywood", "marathi", "pollywood",
         "dhollywood", "ollywood", "jollywood", "bhojiwood", "coastalwood", "konkani", "manipuri"}
OTHER_HOME = {"hollywood": "US", "uk": "GB", "canada": "CA", "australia": "AU", "cuba": "CU", "iran": "IR", "bongowood": "TZ"}
TODAY = datetime.date.today().isoformat()

def home(industry):
    return "IN" if industry in INDIA else HOME.get(industry) or OTHER_HOME.get(industry)

def dates_by_type(rd, kind):
    """{country: earliest date of that release type}"""
    out = {}
    for c in (rd or {}).get("results", []):
        ds = [d["release_date"][:10] for d in c.get("release_dates", []) if d.get("type") == kind and d.get("release_date")]
        if ds: out[c["iso_3166_1"]] = min(ds)
    return out

def one(r):
    m = get(f"/movie/{r['tmdb_id']}", append_to_response="release_dates,watch/providers")
    if not m: return None
    h = home(r["industry"])
    digital = dates_by_type(m.get("release_dates"), 4)
    theatre = dates_by_type(m.get("release_dates"), 3) or dates_by_type(m.get("release_dates"), 2)
    dig_c = next((c for c in (h, "IN", "US") if c and c in digital), None) or (min(digital, key=digital.get) if digital else None)
    th = theatre.get(h) if h else None
    reg = regions((m.get("watch/providers") or {}).get("results", {}), r["industry"])
    ind, us = reg.get("IN", {}), reg.get("US", {})
    return {"title_id": r["title_id"], "digital": digital.get(dig_c) if dig_c else None, "dig_c": dig_c,
            "theatre": th or m.get("release_date") or None,
            "watch": json.dumps(reg, separators=(",", ":")) if reg else None,
            "s_in": ", ".join(ind.get("s", [])) or None, "s_us": ", ".join(us.get("s", [])) or None,
            "rb_us": ", ".join(dict.fromkeys(us.get("r", []) + us.get("b", []))) or None,
            "l_in": ind.get("l"), "l_us": us.get("l"),
            "poster": ("https://image.tmdb.org/t/p/w500" + m["poster_path"]) if m.get("poster_path") else None,
            "overview": m.get("overview") or None,
            "genre": ", ".join(g["name"] for g in m.get("genres", [])) or None,
            "rating": m.get("vote_average"), "votes": m.get("vote_count")}

UPD = """update titles set
  digital_release_date = coalesce(?, digital_release_date), digital_country = coalesce(?, digital_country),
  release_date = case when (release_date is null or substr(release_date, 6) = '01-01') and ? is not null
                      and (year is null or substr(?, 1, 4) = cast(year as text)) then ? else release_date end,
  watch_regions = coalesce(?, watch_regions), streaming_in = coalesce(?, streaming_in), streaming_us = coalesce(?, streaming_us),
  rent_buy_us = coalesce(?, rent_buy_us), watch_link_in = coalesce(?, watch_link_in), watch_link_us = coalesce(?, watch_link_us),
  poster_url = case when poster_url is null or poster_url = '' or poster_url like 'https://commons.wikimedia.org/%' then coalesce(?, poster_url) else poster_url end,
  overview = coalesce(overview, ?), genre = coalesce(genre, ?),
  tmdb_rating = coalesce(?, tmdb_rating), tmdb_votes = coalesce(?, tmdb_votes),
  rating_display = case when coalesce(?, tmdb_votes, 0) >= 10 then coalesce(?, tmdb_rating) else rating_display end,
  status = case when status = 'upcoming' and coalesce(release_date, ?) <= ? then 'released' else status end,
  tmdb_checked_at = datetime('now')
where title_id = ?"""

def save(rows):
    st = [(UPD, [x["digital"], x["dig_c"], x["theatre"], x["theatre"], x["theatre"], x["watch"], x["s_in"], x["s_us"], x["rb_us"],
                 x["l_in"], x["l_us"], x["poster"], x["overview"], x["genre"], x["rating"], x["votes"], x["votes"], x["rating"],
                 x["theatre"], TODAY, x["title_id"]]) for x in rows if x]
    for i in range(0, len(st), 200): execute(st[i:i + 200])

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--months", type=int, default=18); ap.add_argument("--threads", type=int, default=16)
    a = ap.parse_args()
    since = (datetime.date.today() - datetime.timedelta(days=30 * a.months)).isoformat()
    todo = query("""select title_id, industry, tmdb_id from titles where type = 'movie' and tmdb_id is not null
                    and (release_date >= ? or status = 'upcoming' or (release_date is null and year >= ?))""", [since, int(since[:4])])
    print(f"{len(todo)} films to check", flush=True)
    done = got = 0
    with ThreadPoolExecutor(a.threads) as ex:
        for i in range(0, len(todo), 400):
            res = list(ex.map(one, todo[i:i + 400]))
            save(res)
            done += len(res); got += sum(1 for x in res if x and x["digital"])
            print(f"{done}/{len(todo)} checked, {got} with a digital release date", flush=True)
