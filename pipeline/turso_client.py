"""Tiny Turso (libSQL) HTTP client used by the pipeline scripts.
Needs TURSO_URL (https://<db>-<org>.<region>.turso.io) and TURSO_TOKEN (full-access token, keep it in .env).
"""
import os, sys, time
import requests

def _base():
    url = os.environ.get("TURSO_URL") or sys.exit("Set TURSO_URL")
    return url.replace("libsql://", "https://").rstrip("/") + "/v2/pipeline"

TOKEN = os.environ.get("TURSO_TOKEN") or sys.exit("Set TURSO_TOKEN (full-access token, never commit it)")
S = requests.Session()
S.headers.update({"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})

def _arg(v):
    if v is None or (isinstance(v, float) and v != v): return {"type": "null"}
    if isinstance(v, bool): return {"type": "integer", "value": str(int(v))}
    if isinstance(v, int): return {"type": "integer", "value": str(v)}
    if isinstance(v, float): return {"type": "float", "value": v}
    return {"type": "text", "value": str(v)}

def _val(c):
    t = c.get("type")
    if t == "null": return None
    if t == "integer": return int(c["value"])
    if t == "float": return float(c["value"])
    return c.get("value")

def execute(statements):
    """statements: list of (sql, args). Runs them in one request, in order. Returns list of row-dict lists."""
    reqs = [{"type": "execute", "stmt": {"sql": q, "args": [_arg(a) for a in (args or [])]}} for q, args in statements]
    body = {"requests": reqs + [{"type": "close"}]}
    for i in range(5):
        try:
            r = S.post(_base(), json=body, timeout=180)
            if r.status_code < 500: break
        except requests.RequestException: pass
        time.sleep(3 * (i + 1))
    r.raise_for_status()
    out = []
    for res in r.json()["results"][:len(reqs)]:
        if res["type"] == "error": raise RuntimeError(res["error"]["message"][:300])
        rr = res["response"]["result"]; names = [c["name"] for c in rr["cols"]]
        out.append([dict(zip(names, map(_val, row))) for row in rr["rows"]])
    return out

def query(sql, args=None):
    return execute([(sql, args)])[0]

def refresh_stats(industry):
    """Recompute the year strip counts for one industry."""
    execute([("delete from industry_year_stats where industry = ?", [industry]),
             ("""insert into industry_year_stats (industry, kind, year, films, streaming)
                 select industry, case when type = 'series' then 'series' else 'film' end, year, count(*),
                        sum(case when streaming_in is not null or streaming_us is not null or watch_regions like '%"s":[%' then 1 else 0 end)
                 from titles where industry = ? and year is not null group by 1, 2, 3""", [industry])])
