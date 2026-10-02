# Pujiverse Film Database

**World cinema, year by year.** An open, IMDb-style film database covering 68 film industries, from Bollywood, Tollywood and Kollywood to Hollywood, Nollywood, Korean, Japanese and European cinema. Browse any industry by year or time frame, see where to stream a film, and rate the story yourself.

🔗 **Live site:** https://pujiverse.github.io/Pujiverse-Film-Database/

---

## Features

- **Industry picker:** 68 industries grouped into 7 regions, each with a film count and a sparkline of its output from 1900 to today.
- **Year strip:** one bar per year for the selected industry. Click a bar to list that year's films; the yellow part of each bar shows how many are streaming now.
- **Time-frame browsing:** any year range (for example 1990–1999), or one click for a whole decade. Large ranges load 100 films at a time.
- **Sorting:** release date, newest first, title A–Z, or highest rated.
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
├── index.html                 # the whole website (HTML + CSS + JS, no build step)
├── .nojekyll                  # tells GitHub Pages to serve files as-is
├── .env.example               # template for pipeline secrets (copy to .env, never commit)
├── supabase/
│   ├── schema.sql             # tables, indexes, row level security, views, search function
│   └── seed_industries.sql    # the 68 industries
└── pipeline/
    ├── industries.py          # industry definitions (Wikidata language / country IDs)
    ├── fast_pipeline.py       # step 1: download films from Wikidata
    ├── wiki_fill.py           # step 2: add missing films from Wikipedia year lists
    ├── enrich_all.py          # step 3: posters, stories, ratings, where-to-watch from TMDB (resumable)
    ├── tmdb_series.py         # web series per industry from TMDB
    ├── load_to_supabase.py    # step 4: upload results into Supabase
    └── requirements.txt
```

## Run your own copy

### 1. Database

1. Create a project at [supabase.com](https://supabase.com). The free tier is enough for roughly 300,000 films.
2. In **SQL Editor**, run `supabase/schema.sql`, then `supabase/seed_industries.sql`.
3. In **Authentication → URL Configuration**, set **Site URL** to your website's address so sign-up confirmation emails link back correctly.

### 2. Website

In `index.html`, set your project URL and **publishable** key:

```js
const SUPABASE_URL = "https://your-project-ref.supabase.co";
const SUPABASE_KEY = "sb_publishable_...";
```

The publishable key is meant to be public. Row level security means visitors can only read films and manage their own ratings.

Then push to GitHub and enable **Settings → Pages → Deploy from branch → `main` / root**. There is no build step.

### 3. Data pipeline

```bash
cd pipeline
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# step 1: Wikidata (choose industries, a region, or --all)
python fast_pipeline.py tollywood bollywood
python fast_pipeline.py --group India
python fast_pipeline.py --all          # several hours; safe to stop and rerun, progress is cached

# step 2: Wikipedia gap-fill (writes out/<industry>_wiki.csv)
python wiki_fill.py bollywood kollywood bhojiwood

# step 3: TMDB enrichment (writes straight to Supabase; safe to stop and rerun)
export TMDB_API_KEY=...                # Windows: set TMDB_API_KEY=...
python enrich_all.py --seconds 3600

# web series (writes out/<industry>_series.csv, then upload in step 4)
python tmdb_series.py --all

# step 4: upload
export SUPABASE_URL=https://your-project-ref.supabase.co
export SUPABASE_SERVICE_ROLE_KEY=...   # server-side only
python load_to_supabase.py
```

Uploads are insert-or-ignore on `title_id`, so rerunning never overwrites existing rows or ratings.

## Security

- **Never commit** your Supabase **service role** key or your **TMDB** key. Keep them in `.env`, which `.gitignore` already excludes, or in environment variables.
- Only the Supabase **publishable** key and the Turso **read-only** token belong in `index.html`. Never put a Turso full-access (read-write) token in the website.
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
- **Streaming availability changes weekly** and is only refreshed when the TMDB step is rerun.

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
