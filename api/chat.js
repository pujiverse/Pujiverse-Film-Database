// Pujiverse Films chat assistant — Vercel serverless function (POST /api/chat)
// The model answers by running read-only SQL against the Turso catalog through one tool: run_sql.
// Environment variables (Vercel → Project → Settings → Environment Variables):
//   TURSO_URL          libsql://pujiverse-films-pujiverse.aws-us-east-1.turso.io
//   TURSO_READ_TOKEN   a READ-ONLY Turso token
//   GEMINI_API_KEY     (free tier at aistudio.google.com)   — or —   ANTHROPIC_API_KEY
//   LLM_MODEL          optional; defaults: gemini-3.5-flash-lite / claude-haiku-4-5-20251001

const ALLOWED_ORIGINS = ["https://cinema.pujiverse.com", "https://movies.pujiverse.com", "https://pujiverse.github.io", "https://movies-pujiverse.vercel.app", "http://localhost:8000"];
const MAX_ROUNDS = 6, ROW_LIMIT = 60, MAX_RESULT_CHARS = 14000;
const hits = new Map();                                     // best-effort per-IP rate limit

const INDUSTRIES = `bollywood=Bollywood (Hindi cinema (Mumbai)); tollywood=Tollywood (Telugu cinema (Hyderabad)); kollywood=Kollywood (Tamil cinema (Chennai)); mollywood=Mollywood (Malayalam cinema (Kochi)); sandalwood=Sandalwood (Kannada cinema (Bengaluru)); bengali-tollywood=Tollywood (Bengali) (Bengali cinema (Kolkata)); marathi=Marathi cinema (Marathi cinema (Mumbai, Pune)); pollywood=Pollywood (Punjabi cinema); dhollywood=Dhollywood (Gujarati cinema); ollywood=Ollywood (Odia cinema); jollywood=Jollywood (Assamese cinema); bhojiwood=Bhojiwood (Bhojpuri cinema); chhollywood=Chhollywood (Chhattisgarhi cinema); coastalwood=Coastalwood (Tulu cinema); konkani=Konkani cinema (Konkani cinema (Goa)); manipuri=Manipuri cinema (Meitei cinema (Manipur)); rajasthani=Rajasthani cinema (Rajasthani cinema); haryanvi=Haryanvi cinema (Haryanvi cinema); lollywood=Lollywood (Pakistan (Lahore, Karachi)); dhallywood=Dhallywood (Bangladesh (Dhaka)); nepal=Kollywood (Nepal) (Nepal (Kathmandu)); srilanka=Sri Lankan cinema (Sri Lanka (Sinhala and Tamil)); china=Chinese cinema (Mainland China); hongkong=Hong Kong cinema (Hong Kong); taiwan=Taiwanese cinema (Taiwan); korea=Korean cinema (South Korea (Chungmuro)); japan=Japanese cinema (Japan); thailand=Thai cinema (Thailand); philippines=Philippine cinema (Philippines); indonesia=Indonesian cinema (Indonesia); vietnam=Vietnamese cinema (Vietnam); malaysia=Malaysian cinema (Malaysia); hollywood=Hollywood (United States (Los Angeles)); canada=Canadian cinema (Canada (English and Québécois)); mexico=Mexican cinema (Mexico); brazil=Brazilian cinema (Brazil); argentina=Argentine cinema (Argentina); colombia=Colombian cinema (Colombia); chile=Chilean cinema (Chile); cuba=Cuban cinema (Cuba); uk=British cinema (United Kingdom); france=French cinema (France); italy=Italian cinema (Italy); germany=German cinema (Germany); spain=Spanish cinema (Spain); russia=Russian cinema (Russia and the Soviet Union); denmark=Danish cinema (Denmark); sweden=Swedish cinema (Sweden); norway=Norwegian cinema (Norway); finland=Finnish cinema (Finland); iceland=Icelandic cinema (Iceland); poland=Polish cinema (Poland); czechia=Czech cinema (Czech Republic and Czechoslovakia); ireland=Irish cinema (Ireland); greece=Greek cinema (Greece); romania=Romanian cinema (Romania); nollywood=Nollywood (Nigeria); ghallywood=Ghallywood (Ghana); riverwood=Riverwood (Kenya); bongowood=Bongowood (Tanzania); southafrica=South African cinema (South Africa); egypt=Egyptian cinema (Egypt); turkey=Turkish cinema (Turkey (Yeşilçam)); iran=Iranian cinema (Iran); israel=Israeli cinema (Israel); morocco=Moroccan cinema (Morocco); australia=Australian cinema (Australia); newzealand=New Zealand cinema (New Zealand)`;

function systemPrompt() {
  const today = new Date().toISOString().slice(0, 10);
  return `You are the Pujiverse Films assistant. You answer questions about films and web series using ONLY the Pujiverse Films database, which you query with the run_sql tool (SQLite). Today is ${today}.

Tables:
- titles(title_id TEXT primary key, title, title_local (title in original script), title_telugu, original_title, industry (slug, see list), language (original language; ISO code like 'te' or a name), languages (spoken languages from TMDB, comma list), type ('movie','short','animated','tv_film','documentary','series'), status ('released','upcoming','unknown'), release_date 'YYYY-MM-DD' (NULL, or a date ending in '-01-01', means only the year is known), year INTEGER, genre, runtime_min, director, cast_names (comma list), production, overview, poster_url, tmdb_rating, tmdb_votes, rating_display (TMDB rating, only when tmdb_votes >= 10), streaming_in, streaming_us (comma lists of services), rent_buy_us, imdb_id, tmdb_id, seasons, episodes, network, series_status, creators)
- industries(slug, name, region, description)
- industry_year_stats(industry, kind 'film'|'series', year, films, streaming)  -- fast counts per year
- titles_fts: FTS5 index over (title, title_local, title_telugu, original_title, director, cast_names). For names and titles prefer:
  select t.title_id, t.title, t.year from titles_fts f join titles t on t.rowid = f.rowid where titles_fts match '"rajinikanth"' limit 20

Industries (slug=name (description)): ${INDUSTRIES}

Rules:
- Always query before answering factual questions. Use only SELECT (or WITH ... SELECT). Results are capped at ${ROW_LIMIT} rows; use COUNT/GROUP BY for totals.
- "Upcoming" means release_date > '${today}'. "Released in <year>" means year = <year>. Web series are type = 'series'; films are type <> 'series'.
- For "best"/"top rated", rank by weighted rating: (rating_display*tmdb_votes + 6.5*250.0)/(tmdb_votes+250.0) desc, among rows with rating_display not null.
- The same film can appear under several industries (dubbed versions share tmdb_id or imdb_id).
- Link every film or series you mention as [Title (year)](#/film/<title_id>).
- Be concise and friendly. If the database has no answer, say so plainly; never invent films, dates, cast or streaming services.
- Only answer questions about films, series, people in them and this site.`;
}

const TOOL_DESC = "Run one read-only SQLite query (SELECT or WITH ... SELECT) against the Pujiverse Films catalog. Returns up to " + ROW_LIMIT + " rows as JSON.";

function cleanSql(sql) {
  let s = String(sql || "").trim().replace(/;+\s*$/, "");
  if (!/^(select|with)\b/i.test(s)) throw new Error("Only SELECT queries are allowed.");
  if (s.includes(";")) throw new Error("Only one statement is allowed.");
  if (/\b(insert|update|delete|drop|alter|create|attach|detach|pragma|vacuum|reindex)\b/i.test(s.replace(/'[^']*'/g, "''")))
    throw new Error("Only read-only queries are allowed.");
  return `select * from (${s}) limit ${ROW_LIMIT}`;
}

async function runSql(sql) {
  const url = process.env.TURSO_URL.replace(/^libsql:\/\//, "https://").replace(/\/$/, "") + "/v2/pipeline";
  const ctl = new AbortController(); const timer = setTimeout(() => ctl.abort(), 15000);
  try {
    const r = await fetch(url, { method: "POST", signal: ctl.signal,
      headers: { Authorization: `Bearer ${process.env.TURSO_READ_TOKEN}`, "Content-Type": "application/json" },
      body: JSON.stringify({ requests: [{ type: "execute", stmt: { sql: cleanSql(sql) } }, { type: "close" }] }) });
    const res = (await r.json()).results?.[0];
    if (!res) throw new Error(`Database request failed (${r.status})`);
    if (res.type === "error") throw new Error(res.error.message);
    const { cols, rows } = res.response.result;
    const out = rows.map(row => Object.fromEntries(cols.map((c, i) => {
      let v = row[i].type === "null" ? null : row[i].value;
      if (typeof v === "string" && v.length > 300) v = v.slice(0, 300) + "…";
      return [c.name, v];
    })));
    let json = JSON.stringify({ rows: out, row_count: out.length });
    if (json.length > MAX_RESULT_CHARS) json = json.slice(0, MAX_RESULT_CHARS) + '…(truncated)';
    return json;
  } catch (e) {
    return JSON.stringify({ error: String(e.message || e) });
  } finally { clearTimeout(timer); }
}

async function askAnthropic(history) {
  const model = process.env.LLM_MODEL || "claude-haiku-4-5-20251001";
  const messages = history.map(m => ({ role: m.role, content: m.content }));
  const tools = [{ name: "run_sql", description: TOOL_DESC,
    input_schema: { type: "object", properties: { sql: { type: "string" } }, required: ["sql"] } }];
  for (let round = 0; round < MAX_ROUNDS; round++) {
    const r = await fetch("https://api.anthropic.com/v1/messages", { method: "POST",
      headers: { "x-api-key": process.env.ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json" },
      body: JSON.stringify({ model, max_tokens: 1200, system: systemPrompt(), tools, messages }) });
    const data = await r.json();
    if (!r.ok) throw new Error(data.error?.message || `Anthropic API error ${r.status}`);
    const uses = data.content.filter(b => b.type === "tool_use");
    if (!uses.length) return data.content.filter(b => b.type === "text").map(b => b.text).join("\n").trim();
    messages.push({ role: "assistant", content: data.content });
    const results = [];
    for (const u of uses) results.push({ type: "tool_result", tool_use_id: u.id, content: await runSql(u.input?.sql) });
    messages.push({ role: "user", content: results });
  }
  return "That question needed too many lookups. Try asking something more specific.";
}

async function askGemini(history) {
  const models = [...new Set([process.env.LLM_MODEL || "gemini-3.5-flash-lite", "gemini-3.8-flash", "gemini-3.1-flash-lite"])];
  const contents = history.map(m => ({ role: m.role === "assistant" ? "model" : "user", parts: [{ text: m.content }] }));
  const tools = [{ functionDeclarations: [{ name: "run_sql", description: TOOL_DESC,
    parameters: { type: "object", properties: { sql: { type: "string" } }, required: ["sql"] } }] }];
  for (let round = 0; round < MAX_ROUNDS; round++) {
    let r, data;
    for (const model of models) {   // if the main model is out of free quota, try the backup model once
      r = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent`, { method: "POST",
        headers: { "x-goog-api-key": process.env.GEMINI_API_KEY, "content-type": "application/json" },
        body: JSON.stringify({ systemInstruction: { parts: [{ text: systemPrompt() }] }, contents, tools,
          generationConfig: { temperature: 0.2, maxOutputTokens: 1200 } }) });
      data = await r.json().catch(() => ({}));
      if (r.ok) break;   // quota hit, model retired or unavailable: try the next one
    }
    if (r.status === 429 || r.status === 503) { const e = new Error("busy"); e.busy = true; throw e; }
    if (!r.ok) throw new Error(data.error?.message || `Gemini API error ${r.status}`);
    const content = data.candidates?.[0]?.content;
    if (!content?.parts?.length) return "I couldn't produce an answer for that. Try rephrasing.";
    const calls = content.parts.filter(p => p.functionCall);
    if (!calls.length) return content.parts.map(p => p.text || "").join("").trim();
    contents.push(content);
    const parts = [];
    for (const c of calls) parts.push({ functionResponse: { name: c.functionCall.name,
      response: JSON.parse(await runSql(c.functionCall.args?.sql)) } });
    contents.push({ role: "user", parts });
  }
  return "That question needed too many lookups. Try asking something more specific.";
}

module.exports = async (req, res) => {
  const origin = req.headers.origin || "";
  if (ALLOWED_ORIGINS.includes(origin)) res.setHeader("Access-Control-Allow-Origin", origin);
  res.setHeader("Vary", "Origin");
  res.setHeader("Access-Control-Allow-Methods", "POST, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");
  if (req.method === "OPTIONS") return res.status(204).end();
  if (req.method !== "POST") return res.status(405).json({ error: "Use POST." });
  if (!process.env.TURSO_URL || !process.env.TURSO_READ_TOKEN || !(process.env.GEMINI_API_KEY || process.env.ANTHROPIC_API_KEY))
    return res.status(503).json({ error: "The assistant isn't set up yet." });

  const ip = (req.headers["x-forwarded-for"] || "").split(",")[0].trim() || "anon";
  const now = Date.now(), recent = (hits.get(ip) || []).filter(t => now - t < 10 * 60 * 1000);
  if (recent.length >= 20) return res.status(429).json({ error: "Too many questions. Wait a few minutes and try again." });
  hits.set(ip, [...recent, now]);

  let body = req.body;
  if (typeof body === "string") { try { body = JSON.parse(body); } catch { body = {}; } }
  const history = (Array.isArray(body?.messages) ? body.messages : [])
    .filter(m => (m.role === "user" || m.role === "assistant") && typeof m.content === "string" && m.content.trim())
    .slice(-12).map(m => ({ role: m.role, content: m.content.slice(0, 2000) }));
  if (!history.length || history[history.length - 1].role !== "user") return res.status(400).json({ error: "Send a question." });
  while (history[0].role !== "user") history.shift();

  try {
    const answer = process.env.ANTHROPIC_API_KEY ? await askAnthropic(history) : await askGemini(history);
    res.status(200).json({ answer });
  } catch (e) {
    if (e.busy) return res.status(429).json({ error: "The assistant is busy right now (free daily limit reached). Please try again later." });
    res.status(502).json({ error: "The assistant couldn't answer right now: " + String(e.message || e).slice(0, 200) });
  }
};

module.exports.cleanSql = cleanSql;
module.exports.runSql = runSql;
