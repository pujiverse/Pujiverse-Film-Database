# Pujiverse Film Database

**World cinema, year by year.** An open, IMDb-style film database covering 68 film industries, from Bollywood, Tollywood and Kollywood to Hollywood, Nollywood, Korean, Japanese and European cinema. Browse any industry by year or time frame, see where to stream a film, and rate the story yourself.

🔗 **Live site:** https://pujiverse.github.io/Pujiverse-Film-Database/

---

## Features

- **Industry picker:** 68 industries grouped into 7 regions, each with a film count and a sparkline of its output from 1900 to today.
- **Year strip:** one bar per year for the selected industry. Click a bar to list that year's films; the lower part of each bar shows how many are streaming now.
- **Time-frame browsing:** any year range (for example 1990–1999), or one click for a whole decade. Large ranges load 100 films at a time.
- **Search and filters on every list:** year lists, decades, web series, search results, language pages, OTT releases and Coming soon all have a "search in this list" box (title, director or actor) and a **Streaming on** filter covering Netflix, Prime Video, Disney+, Max (HBO Max), Apple TV+, Paramount+, Peacock, Hulu, YouTube, Tubi, Pluto TV, The Roku Channel, JioHotstar, ZEE5, SonyLIV, aha, ETV Win, Sun NXT, Crunchyroll, MUBI and more.
- **Filters and sorting:** exact date range (day, month and year), genre, where to watch (any country, India, US, or stream/rent/buy), minimum rating, and six sort orders (oldest or newest release date, most popular, highest rated, title A–Z or Z–A). Titles with an exact release date come first; titles that only have a year are listed after them under a "Date not known" divider, or can be hidden.
- **Chart:** bar height is the number of titles released that year; the lower part ("Streaming now") is how many can be streamed in any tracked country and the upper part ("No streaming data") is the rest. Hovering over a bar shows both numbers.
- **Ranked search across every industry:**
  - Matches title (English and original script), director, or cast.
  - Ranks exact titles first, then partial title matches, then director, then cast, with better-known films first within each group.
  - Filters by industry and year range.
- **Web series section for every industry:** a Films | Web series tab on each industry page, with its own year strip, sorting and time-frame filters. A show counts as a web series when its original network is a streaming service (Netflix, Prime Video, JioHotstar, aha, ZEE5, SonyLIV, and others); TV-channel serials and adult-content platforms are excluded.
- **Film and series pages:** poster, story, cast and crew, runtime, seasons and episodes for series, and where to watch in India and the US.
- **Where-to-watch links:** each platform opens a search for the title on that service (or the TMDB/JustWatch page), with "See all options" links per country, plus IMDb and TMDB links.
- **Community ratings:** signed-in users give an overall score and a separate story score (1–10) with an optional review. One rating per user per film, editable.
- **Duplicate reporting:** users can flag a film listed twice.
- **Original-script titles:** Telugu, Hindi, Tamil, Korean, Japanese and others appear next to the English title.
- **Where to watch, by country:** India, US, UK, Canada, Australia and the title's home country, split into Stream / Rent / Buy, with links that open a search for the title on each service. Every film page also has **Where to watch on Google**, **Search on Google** and **JustWatch** buttons (new tab), and list rows without data link straight to a Google where-to-watch search.
- **Release calendar:** click any year on the bar chart and a month-by-month calendar appears above the list. Pick a month, then a day, to see everything released that day. Titles that only have a known year stay in the full list.
- **Coming soon:** a site-wide upcoming page (`#/upcoming`) and a Coming soon tab on every industry, with a calendar, a month-by-month list, "In N days" badges and **Add to calendar** (.ics) buttons.
- **Browse by language** (`#/languages`): every language with its title count, and a page per language listing all films, web series and shorts available in it, both titles made in that language and ones dubbed into it. Dubbed titles carry a "Dubbed · original Tamil" style badge (or "Multi-language" when TMDB lists the language among a film's releases). Filter to original-language or dubbed titles only, and sort by popularity, date or title.
- **Trending on streaming:** every industry page and language page shows the most popular titles right now on the main services in that market (for example Netflix, Prime Video, Zee5 and JioHotstar in India), as a ranked poster row per service. Ranking is TMDB popularity among titles streaming on that service (JustWatch data), refreshed daily; it is not the services' official top-10 lists.
- **OTT releases:** a page (`#/ott`) listing films and web series as they reach streaming, in two tabs (Coming to OTT, Recently on OTT) with an industry filter. Each row shows the movie, theatre release date, digital release date (with an "In N days" note), streaming partner, category (language, movie or web series, genre) and a **Trailer** button that opens a YouTube search for the trailer. Clicking a streaming service opens that service's own search for the title. Film pages also show the digital release date.
- **Posters from free sources:** TMDB (any language's poster), Wikidata's "film poster" and image on Wikimedia Commons, and the Wikipedia article's infobox image. Titles with no poster get a title card instead of an empty box.
- **Languages:** each film shows how many languages it's available in, combining TMDB's spoken languages with versions of the same film listed under other industries (for example a Telugu film also released in Tamil).
- **Ask about any film:** a chat assistant that answers questions from the database itself. It writes read-only SQL against the Turso catalog through one tool, so answers come from your data, with links to each film.
- **Light and dark mode, mobile layout, keyboard accessible.**

## Coverage

| Region | Industries |
|---|---|
| India | Bollywood (Hindi), Tollywood (Telugu), Kollywood (Tamil), Mollywood (Malayalam), Sandalwood (Kannada), Tollywood (Bengali), Marathi, Pollywood (Punjabi), Dhollywood (Gujarati), Ollywood (Odia), Jollywood (Assamese), Bhojiwood (Bhojpuri), Chhollywood (Chhattisgarhi), Coastalwood (Tulu), Konkani, Manipuri, Rajasthani, Haryanvi |
| South Asia | Lollywood (Pakistan), Dhallywood (Bangladesh), Kollywood (Nepal), Sri Lanka |
| East & Southeast Asia | China, Hong Kong, Taiwan, South Korea, Japan, Thailand, Philippines, Indonesia, Vietnam, Malaysia |
| Americas | Hollywood, Canada, Mexico, Brazil, Argentina, Colombia, Chile, Cuba |
| Europe | UK, France, Italy, Germany, Spain, Russia, Denmark, Sweden, Norway, Finland, Iceland, Poland, Czechia, Ireland, Greece, Romania |
| Middle East & Africa | Nollywood (Nigeria), Ghallywood (Ghana), Riverwood (Kenya), Bongowood (Tanzania), South Africa, Egypt, Turkey, Iran, Israel, Morocco |
| Oceania | Australia, New Zealand |

The database is still being filled. Industries without data yet show **"Soon"** on the picker. Streaming, posters and story summaries are currently complete for Telugu cinema and are being added for the rest.

## How it works

```
 Wikidata (SPARQL + entity API) ─┐                         ┌─► Turso (SQLite + FTS5): catalog ◄──┐
 Wikipedia "List of X films of YEAR" ─┼─► Python pipeline ──┤                                     ├── index.html on GitHub Pages
 TMDB API (+ JustWatch providers) ─┘                         └─► Supabase (Postgres): accounts, ratings ◄──┘
```

1. **Wikidata** supplies the base list for each industry: titles, dates, directors, cast, genres, runtimes, and IMDb/TMDB IDs. Indian industries are matched by original language; others by country of origin, including historical states such as the Soviet Union, Czechoslovakia and West/East Germany.
2. **Wikipedia year lists** fill in films that Wikidata is missing. This added about 21,000 Indian and South Asian films, for example taking Bhojpuri from 37 films to over 500.
3. **TMDB** adds the story summary, poster, rating, and where-to-watch data (from JustWatch) for India and the US.
4. The **film and series catalog** (about 430,000 titles, ~290 MB with full-text search) lives in **Turso** (SQLite, free 5 GB tier). The website reads it with a **read-only** token, so visitors can't change anything.
5. **Accounts, ratings, reviews and duplicate reports** live in **Supabase** (a few MB, well inside its free 500 MB).
The website is a single static `index.html` that queries both directly from the browser.

## Repository structure

```
├── index.html                     # the whole website (HTML + CSS + JS, no build step)
├── api/chat.js                    # chat assistant (Vercel serverless function, read-only SQL tool)
├── vercel.json, .vercelignore     # deploy as a static site plus the /api function
├── .github/workflows/             # scheduled data refresh: where-to-watch (daily), upcoming (weekly)
├── .nojekyll                      # tells GitHub Pages to serve files as-is
├── .env.example                   # template for pipeline secrets (copy to .env, never commit)
├── turso/
│   ├── schema.sql                 # catalog: titles, industries, year counts, full-text search + sync triggers
│   ├── seed_industries.sql        # the 68 industries
│   └── migrate_001_sync_triggers.sql  # one-time upgrade for databases created before the triggers existed
├── supabase/
│   └── schema.sql                 # accounts data only: user_ratings, duplicate_reports (+ row level security)
└── pipeline/
    ├── industries.py              # industry definitions (Wikidata language / country IDs)
    ├── fast_pipeline.py           # 1. films from Wikidata            -> out/<industry>.csv
    ├── wiki_fill.py               # 2. missing films from Wikipedia   -> out/<industry>_wiki.csv
    ├── tmdb_series.py             # 3. web series from TMDB           -> out/<industry>_series.csv
    ├── load_to_turso.py           # 4. upload CSVs into Turso and refresh year counts
    ├── enrich_turso.py            # 5. posters, stories, ratings, where-to-watch from TMDB (resumable)
    ├── enrich_watch.py            # per-country where-to-watch + posters/stories from TMDB (resumable)
    ├── fetch_upcoming.py          # 6. upcoming releases per industry from TMDB (run monthly)
    ├── wiki_dates.py              # exact Indian release dates from Wikipedia year lists
    ├── fix_untitled.py            # replace titles that are only a Wikidata ID with real names
    ├── turso_client.py            # small Turso HTTP client used by the scripts
    └── requirements.txt
```

## Run your own copy

### 1. Catalog database (Turso, free 5 GB)

1. Create a database at [turso.tech](https://turso.tech) (US East (Virginia) suits a US audience).
2. Run `turso/schema.sql`, then `turso/seed_industries.sql` (Turso CLI: `turso db shell <db> < turso/schema.sql`).
3. Create two tokens: a **read-only** token for the website, and a **full-access** token for the pipeline (keep it in `.env`).

### 2. Accounts database (Supabase, free 500 MB)

1. Create a project at [supabase.com](https://supabase.com) and run `supabase/schema.sql` in the SQL Editor.
2. In **Authentication → URL Configuration**, set **Site URL** to your website address.

### 3. Website

In `index.html` set:

```js
const SUPABASE_URL = "https://your-project-ref.supabase.co";
const SUPABASE_KEY = "sb_publishable_...";                 // public by design
const TURSO_URL    = "https://<db>-<org>.<region>.turso.io/v2/pipeline";
const TURSO_TOKEN  = "<read-only token>";                    // must be read-only
```

Push to GitHub and enable **Settings → Pages → Deploy from branch → `main` / root**. No build step.

### 4. Data pipeline

```bash
cd pipeline
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
# load .env into the environment (or set the three variables by hand)

python fast_pipeline.py --group India      # or specific industries, or --all (hours; resumable)
python wiki_fill.py bollywood kollywood    # films Wikidata is missing
python tmdb_series.py --all                # web series
python load_to_turso.py                    # upload everything in out/

python enrich_turso.py --dry-run           # check matching without writing
python enrich_turso.py --seconds 3600      # posters, stories, streaming (rerun until "nothing left")
python enrich_turso.py --seconds 3600 --search   # then titles without IDs, by title + year
```

Uploads are insert-or-ignore on `title_id`, and enrichment only fills empty fields, so reruns are always safe.

### 5. Chat assistant (optional)

The assistant runs as a Vercel serverless function (`api/chat.js`), so it works on the Vercel deployment and the GitHub Pages site calls it there. In **Vercel → Project → Settings → Environment Variables** add:

| Name | Value |
|---|---|
| `TURSO_URL` | `libsql://<db>-<org>.<region>.turso.io` |
| `TURSO_READ_TOKEN` | a **read-only** Turso token |
| `GEMINI_API_KEY` | free key from [aistudio.google.com](https://aistudio.google.com) (or set `ANTHROPIC_API_KEY` instead) |
| `LLM_MODEL` | optional model override; defaults are `gemini-3.5-flash-lite` (falls back to `gemini-3.1-flash-lite`) / `claude-haiku-4-5-20251001` |

Redeploy after adding them. In `index.html`, `CHAT_API` points GitHub Pages visitors to `https://<your-project>.vercel.app/api/chat`; the allowed origins are listed at the top of `api/chat.js`. The function only accepts single `SELECT` queries, caps results at 60 rows, and rate-limits each visitor to 20 questions per 10 minutes.

### 6. Keeping upcoming releases fresh

```bash
python fetch_upcoming.py            # every industry, next 18 months, month by month
```
Run it every few weeks. It adds newly announced films and updates dates, stories, posters and languages for ones already listed.

### 7. Automatic data refresh (GitHub Actions)

Two scheduled workflows keep the catalog current without your computer:

- **Daily update** (`.github/workflows/daily-update.yml`, every day at 04:23 UTC):
  1. `tmdb_changes.py` asks TMDB which movies and shows changed in the last two days and refreshes the ones in the catalog (rating, votes, release date, genre, languages, where to watch).
  2. `ott_dates.py` refreshes digital (OTT) release dates and streaming partners for films from the last 18 months and upcoming ones.
  3. `fetch_upcoming.py` adds newly announced films for every industry and updates their dates.
  4. `build_languages.py` rebuilds the language index (original and dubbed languages for every title).
  5. `platform_trends.py` refreshes "Trending on streaming" for every industry and language.
  6. Year-strip counts are recalculated.
- **Weekly posters and where to watch** (`.github/workflows/weekly-posters.yml`, Sundays): `fill_posters.py` looks for posters for titles that still have none (Wikidata / Wikimedia Commons, TMDB, Wikipedia), then `enrich_watch.py` checks where to watch for titles never checked.

Add three repository secrets in **GitHub → Settings → Secrets and variables → Actions**: `TURSO_URL`, `TURSO_TOKEN` (a **full-access** Turso token with no expiry, used only here) and `TMDB_API_KEY`. Start either workflow right away from the **Actions** tab with **Run workflow**.

You can run the same scripts by hand:

```bash
python tmdb_changes.py --days 7          # catch up after a break (TMDB keeps up to 14 days of changes)
python ott_dates.py --months 24
python fill_posters.py collect --out posters && python fill_posters.py save --out posters
```

## Security

- The site reads the catalog with a **read-only** Turso token; writes are rejected by the database itself. The full-access token lives only in GitHub Actions secrets.
- Supabase tables use row-level security: visitors can read ratings and reviews (not who wrote them); only signed-in users can add or change their own rating.
- The chat assistant runs read-only, single-statement SELECTs (no comments, balanced parentheses, 60-row cap) and is rate-limited per visitor. For extra protection, add a rate-limit rule in Vercel → Firewall and set a usage alert in Turso.

- **Never commit** your Supabase **service role** key or your **TMDB** key. Keep them in `.env`, which `.gitignore` already excludes, or in environment variables.
- Only the Supabase **publishable** key and the Turso **read-only** token belong in `index.html`. Never put a Turso full-access (read-write) token in the website.\n- Turso does not list tokens after creating them. To revoke a leaked token, use **Invalidate All Tokens** on the database page, then create a new read-only token and update `index.html`.
- If a key is ever exposed (pasted in a chat, screenshot or commit), regenerate it: TMDB under **Settings → API → Regenerate Key**, Supabase under **Project Settings → API Keys**.
- Row level security is enabled on every table. Users can only create, edit or delete their own ratings and reports.

## Data sources and attribution

| Source | Used for | License / terms |
|---|---|---|
| [Wikidata](https://www.wikidata.org) | Film lists, dates, crew, cast, IDs | CC0 (public domain) |
| [Wikipedia](https://en.wikipedia.org) | Missing films from yearly film lists | CC BY-SA 4.0. Each film links back to its source page. |
| [TMDB](https://www.themoviedb.org) | Posters, summaries, ratings | [TMDB API Terms](https://www.themoviedb.org/api-terms-of-use) |
| [JustWatch](https://www.justwatch.com) (via TMDB) | Where-to-watch availability | Attribution required |

> This product uses the TMDB API but is not endorsed or certified by TMDB.

TMDB's free developer key covers **non-commercial** use. Running ads, paid features, or other monetization requires a TMDB commercial license. Check their current terms before launching commercially. The TMDB terms also restrict using TMDB content in AI/ML applications.

## Known limitations

- **Thin coverage for smaller industries.** Chhattisgarhi, Rajasthani, Konkani and Nepali cinema are thinly covered on both Wikidata and Wikipedia.
- **Some duplicates remain.** The same film can appear twice when sources spell it differently. Bilingual films may appear under two industries. Use "Report a duplicate".
- **Years without exact dates.** Films with only a known year appear in that year's list without a day and month.
- **Streaming availability changes often.** The daily update refreshes titles TMDB reports as changed; others are rechecked by the weekly job.
- **Digital release dates depend on TMDB.** Many Indian films have no OTT date on TMDB until they start streaming, so "Coming to OTT" is thinner than announcements in the press.

## Roadmap

- [ ] Finish loading every industry, then run a cross-industry duplicate check
- [ ] TMDB enrichment beyond Telugu (posters, stories, streaming)
- [x] Web series section for every industry
- [ ] Anime and short-film sections
- [ ] Scheduled weekly refresh of new releases and streaming data
- [ ] Per-film pages that search engines can index

## License

Code: add the license of your choice (for example MIT) as a `LICENSE` file.
Data: remains under the licenses of its sources listed above.

---

Built by **Pujith Chowdary Sakhamuri** as part of the **Pujiverse Network**.
