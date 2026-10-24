# PhD Finder

Daily search for open PhD positions, ranked for an applicant profile, then **auto-apply** where that is possible.

The checked-in defaults are for **Saeed Samimi** (computational biology / AI / LLMs, Stuttgart-first regions). Someone else can reuse the same code by changing config and personal files — see [Reuse for a different person or career](#reuse-for-a-different-person-or-career).

Region order (default): Stuttgart area, then the rest of Germany, Switzerland and Luxembourg, the rest of Europe, then Australia and Canada. United States listings are dropped. University career pages and national university boards are searched first and ranked above aggregator sites. LinkedIn public job search is included for the same regions (PhD/Doktorand queries only; industry “PhD required” ads are filtered out).

Research tracks (default): computational biology, machine learning, and large language models.

## What is automated vs what still needs you

| Kind of opening | What the pipeline does |
| --- | --- |
| Email / hybrid (PI or HR address found) | Builds the package and **sends the application email** via Gmail when OAuth is configured. |
| Portal-only (no email, online form, CAPTCHA, login) | Builds the CV/letter/checklist package and marks `portal_ready`. **You** submit the form (sites differ and block bots). Then `mark-applied`. |

`pipeline.auto_apply: true` in `config/profile.yaml` turns this on. Set it to `false` if you want the old manual review queue again.

## Daily use

From `D:\Projects\phd finder`:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_daily.ps1
```

That discovers, packages the top matches, auto-approves them, and sends email applications (once Gmail OAuth exists).

Portal-ready packages live under `output\packages\<id>\`. After you submit on the site:

```powershell
.\.venv\Scripts\python.exe -m phd_finder mark-applied <id>
```

## Status values

`new`, `docs_ready`, `awaiting_approval`, `approved`, `email_sent`, `portal_ready`, `applied`, `skipped`, `closed`, `failed`.

## Table columns

`priority_rank`, `score`, `title`, `institution`, `city`, `country`, `region_tier`, `pi_or_contact`, `url`, `source`, `deadline`, `posted_date`, `match_reasons`, `status`, `application_mode`, `package_path`, `email`, `notes`, `id`.

## One-time setup

```powershell
cd "D:\Projects\phd finder"
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
copy config\profile.example.yaml config\profile.yaml
copy phd_finder\docs\templates\cover_letter.example.txt.j2 phd_finder\docs\templates\cover_letter.txt.j2
```

Then edit `config\profile.yaml` and `cover_letter.txt.j2` with your details. Those two files (plus CVs/PDFs, `.env`, and Gmail OAuth JSON) are **gitignored** so personal data is not pushed.

If `files.pythonhosted.org` does not resolve on this network, install from the mirror instead:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn
```

### Gmail (required for auto email apply)

Gmail API uses **OAuth**, not your Google password. Never put the password in `.env` or chat.

1. Open [Google Cloud Console → Credentials](https://console.cloud.google.com/apis/credentials) while signed in as the sender Gmail (default: `saeedsamimi995@gmail.com`).
2. Create/select a project → enable **Gmail API**.
3. Configure the **OAuth consent screen** (External). Add that same Gmail as a test user.
4. **Create credentials → OAuth client ID → Desktop app** → download the JSON.
5. Save it as `config\gmail_credentials.json`.
6. Set `GMAIL_SENDER` in `.env` to that address.
7. Finish auth once:

```powershell
.\.venv\Scripts\python.exe scripts\setup_gmail_oauth.py
```

That opens a browser; sign in and allow send-only access. The token is stored in `data\gmail_token.json`.

Use `python -m phd_finder send --dry-run` to preview without Gmail.

### Optional letter tailoring

Set `OPENAI_API_KEY` in `.env`. If it is empty, cover letters use the local template.

### Schedule 08:00 daily

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\register_task.ps1
```

The task runs `scripts\run_daily.ps1` with auto-apply (email send when Gmail OAuth is set up).

## Commands

| Command | What it does |
| --- | --- |
| `python -m phd_finder daily` | Discover, package the top 15, export the table |
| `python -m phd_finder discover` | Fetch and score only |
| `python -m phd_finder prepare` | Build packages for the current top positions |
| `python -m phd_finder approve --from-queue` | Read decisions from the review file |
| `python -m phd_finder approve --all` | Approve everything waiting |
| `python -m phd_finder send` | Email approved applications |
| `python -m phd_finder export` | Rewrite today's spreadsheet |
| `python -m phd_finder mark-applied <id>` | Record a manual portal submission |

## Sources

University pages are searched first and ranked above job boards. Coverage is Stuttgart and the other German university portals already configured, then EURAXESS PhD listings for every European country plus Australia and Canada, and the university vacancy sites University Positions (Europe), jobs.ac.uk, AcademicTransfer (Netherlands), Wageningen, Aalto, Uppsala, CSIRO, and UniJobs Australia.

Job boards still fill gaps: LinkedIn (public guest search for PhD/Doktorand queries across Germany, Switzerland, Luxembourg, Europe, Australia, and Canada), EURAXESS, DAAD PhDGermany, academics.de, and Nature Careers. A source is skipped if that site is down.

Shared board settings live in `config/sources.yaml`. Your private applicant profile is `config/profile.yaml` (not in git). Previous applications listed in `applied_history_xlsx` are used to avoid ranking the same posting again.

## Personal files vs examples

| Tracked example (safe to commit) | Your private copy (gitignored) |
| --- | --- |
| `config/profile.example.yaml` | `config/profile.yaml` |
| `phd_finder/docs/templates/cover_letter.example.txt.j2` | `phd_finder/docs/templates/cover_letter.txt.j2` |
| `.env.example` | `.env` |
| — | `config/gmail_credentials.json`, `data/gmail_token.json` |
| — | Root `*.pdf` (CVs, manuscript), `personal/`, `data/`, `output/` |

If `cover_letter.txt.j2` is missing, the pipeline falls back to `cover_letter.example.txt.j2`. Optional OpenAI letter facts come from `letter_facts` / `skills_summary` in your `profile.yaml`.

## Reuse for a different person or career

Most of the pipeline is generic. Copy the example files, fill them in, and point paths at your documents. You usually do not need to rewrite the discover/score/CLI code.

### Must change (identity and documents)

| What | Where |
| --- | --- |
| Name, email, phone, address, degree, university, thesis, profile links | `config/profile.yaml` → `applicant` (start from `profile.example.yaml`) |
| Paths to CVs, transcripts, recommendation letters, manuscript, etc. | `config/profile.yaml` → `cv_variants`, `assets`, `about_apply_dir` |
| Prior applications spreadsheet (or point at an empty one) | `config/profile.yaml` → `applied_history_xlsx` |
| Cover letter narrative | `cover_letter.txt.j2` (start from `cover_letter.example.txt.j2`) |
| Optional LLM facts / skills | `config/profile.yaml` → `letter_facts`, `skills_summary` |
| Gmail sender + their own OAuth client | `.env` (`GMAIL_SENDER`) and `config/gmail_credentials.json`, then `scripts/setup_gmail_oauth.py` |
| Clear previous applicant’s run state | Delete or replace `data/phd_finder.db`, `data/gmail_token.json`, and `output/` |

### Must change (career / matching)

| What | Where |
| --- | --- |
| Board/search phrases | `config/profile.yaml` → `search_queries` |
| What counts as a good topic fit | `config/profile.yaml` → `keyword_tracks` |
| Country / city priority | `config/profile.yaml` → `region_weights`, `stuttgart_hotspot_cities`, `exclude_countries` |
| Which sites to scrape | `config/sources.yaml` |
| Apps per day, auto-send, min score | `config/profile.yaml` → `pipeline` |

### Suggested order for a new user

1. `copy config\profile.example.yaml config\profile.yaml` and edit it.  
2. `copy ...\cover_letter.example.txt.j2 ...\cover_letter.txt.j2` and rewrite the story.  
3. Put CVs/transcripts wherever `profile.yaml` points (or under a local `personal/` folder).  
4. Adjust regions/sources if needed.  
5. Set up Gmail OAuth; set `GMAIL_SENDER` in `.env`.  
6. Clear `data/` and `output/` if reusing someone else’s machine state.  
7. Run `python -m phd_finder daily` (or `send --dry-run` first).

Already emailed positions stay `email_sent` and are **not** selected again on later daily runs. Portal submissions you finish should be marked with `mark-applied`.

## What this does not do

It does not fill university portals, solve CAPTCHAs, or contact referees. Those stay manual, with the checklist and copied CV in each package folder.
