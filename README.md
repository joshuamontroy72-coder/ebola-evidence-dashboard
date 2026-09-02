# Ebola (Bundibugyo) Evidence Watch

A continuously updated, shareable **evidence dashboard** for Ebola vaccines and
therapeutics, with a focus on the **Bundibugyo species (BDBV)**. It pulls from
peer‑reviewed journals, preprints, clinical trials and grey literature (news,
WHO Disease Outbreak News, Africa CDC / NITAG guidance, pharma press releases),
classifies every item, and presents it in a fast, filterable web page that
**refreshes automatically every day**.

Built to deploy on **GitHub + Vercel** with no build step and no servers to run.

<p align="center"><em>Static site &nbsp;·&nbsp; Python pipeline &nbsp;·&nbsp; daily GitHub Action &nbsp;·&nbsp; Vercel hosting</em></p>

---

## What it monitors

| Dimension | Coverage |
|---|---|
| **Interventions** | Vaccines (ERVEBO / rVSV‑ZEBOV, Ad26.ZEBOV/MVA, ChAd3, ChAdOx1, the new Moderna **mRNA‑1469** Bundibugyo candidate, and any other vaccine), monoclonal antibodies (Inmazeb, Ebanga/ansuvimab, mAb114, ZMapp…), and other therapeutics (antivirals, PEP). |
| **Evidence types** | Journal articles, preprints (bioRxiv/medRxiv), clinical trials, news stories, WHO Disease Outbreak News, guidelines / NITAG & Africa CDC updates, pharma press releases. |
| **Species** | Human/clinical evidence for everything; **animal research is included only for vaccines** (animal therapeutic‑only studies are filtered out, per the team's scope). |
| **Canada** | Canadian evidence (PHAC / National Microbiology Laboratory Winnipeg, NACI, Canadian trials & institutions) is flagged for one‑click filtering. |
| **Attention** | Altmetric attention scores are attached to any item with a DOI. |

### Sources
- **Europe PMC** — PubMed/MEDLINE journals **and** preprints in one API.
- **bioRxiv & medRxiv** — monitored **directly** (subject feeds) so brand-new preprints are caught before Europe PMC indexes them.
- **ClinicalTrials.gov** (API v2).
- **WHO IRIS** (`iris.who.int`) — WHO's publications/technical-guidance repository: TAG/SAGE reports, interim guidance, meeting reports (the NITAG-style guidance channel).
- **WHO Disease Outbreak News**, **CIDRAP**, **CDC Emerging Infectious Diseases**, **Africa CDC** (RSS/Atom feeds).
- **News search** across CBC, STAT, Reuters, and others (Google News RSS), plus pharma press releases.
- **Altmetric** badge API for attention scores.

All sources are free and keyless out of the box. See [Customizing](#customizing-the-dashboard).

---

## Deploy in ~10 minutes (GitHub + Vercel)

You need a free [GitHub](https://github.com) account and a free
[Vercel](https://vercel.com) account.

### 1. Put the code on GitHub
Either use this folder as a new repo:

```bash
cd ebola-evidence-dashboard
git init
git add .
git commit -m "Initial commit: Ebola Bundibugyo evidence dashboard"
git branch -M main
git remote add origin https://github.com/<your-org>/ebola-evidence-dashboard.git
git push -u origin main
```

…or upload the folder through **GitHub ▸ New repository ▸ “uploading an existing file.”**

### 2. Connect it to Vercel
1. Go to **vercel.com ▸ Add New ▸ Project**.
2. **Import** your GitHub repository.
3. Framework Preset: **Other** (it's a static site — no configuration needed).
   Leave Build Command empty and Output Directory as the repo root.
4. Click **Deploy**.

That's it — Vercel gives you a live URL like
`https://ebola-evidence-dashboard.vercel.app` that you can share with the team.
Because Vercel watches your GitHub repo, **every future data update
redeploys the site automatically.**

### 3. Turn on the daily refresh
The daily job is already defined in
[`.github/workflows/update.yml`](.github/workflows/update.yml). To activate it:

1. In your GitHub repo, open the **Actions** tab and, if prompted, click
   **“I understand my workflows, enable them.”**
2. (Recommended) Open **Settings ▸ Actions ▸ General ▸ Workflow permissions**
   and select **“Read and write permissions”** so the job can commit the
   refreshed data.
3. To test it immediately: **Actions ▸ “Update evidence data” ▸ Run workflow.**

From then on it runs **every day at 11:00 UTC** (≈ 7 a.m. Toronto time), fetches
new evidence, commits `data/evidence.json`, and Vercel redeploys. Change the
time by editing the `cron:` line in the workflow (cron is in UTC).

> **First run:** the repo ships with a real seed dataset so the dashboard is
> populated the moment it deploys. The first pipeline run expands it
> substantially and begins attaching Altmetric scores.

---

## How the daily update works

```
GitHub Action (daily cron)
      │
      ▼
pipeline/update.py ──► fetch (Europe PMC, ClinicalTrials, feeds, news)
      │                 classify (intervention / species / BDBV / Canada)
      │                 apply inclusion rule (animal ⇒ vaccine only)
      │                 de-duplicate + MERGE with existing data
      │                 enrich with Altmetric
      ▼
data/evidence.json  ──► git commit ──► push
      │
      ▼
Vercel detects the push ──► redeploys the static site
```

The pipeline **merges** with the existing data, so nothing is ever lost:
- `first_seen` (when an item first appeared) is preserved — it powers the
  **“New / unreviewed”** badge for ~3 weeks.
- Manual review status is preserved (see below).
- History accumulates over time, building a durable evidence base.

### Source coverage panel

The dashboard shows a collapsible **Source coverage** panel (below the summary
tiles) listing every monitored channel — Journals, Preprints (bioRxiv/medRxiv),
ClinicalTrials.gov, WHO IRIS guidance, WHO Disease Outbreak News, other guidance,
News, and Press releases — with how many items each holds and how many the last
run added. A channel sitting at **0 items** turns amber and the header flips to a
warning, so a source that silently stops returning results is visible at a glance
rather than quietly leaving a gap. This is driven by the `coverage` block the
pipeline writes into `data/evidence.json`.

---

## Curation: the “New / unreviewed” workflow

You chose **auto‑appear + review flag**: new items publish immediately but are
tagged **New / unreviewed** so the team can vet them (especially grey
literature). Filter to just these with the **“New / unreviewed only”** toggle.

To mark items as reviewed (clearing the badge), add their `id` to
[`pipeline/reviewed_ids.txt`](pipeline/reviewed_ids.txt), one per line, and
commit. You can find an item's `id` in `data/evidence.json`. Example:

```
3f0e81ad50a40748   # reviewed by K. Young 2026-09-02 — relevant, keep
```

The next pipeline run (or a manual run) clears the badge for those items.

---

## Sharing filtered views

The active filters are encoded in the URL, so any view is shareable. Filter to,
say, **Bundibugyo + Vaccine + Last 90 days**, copy the URL, and send it to a
colleague — they'll open exactly that view.

---

## Adding API keys (optional)

Everything works keyless. Keys only raise rate limits / add polite
identification. To add them for the daily job:

**GitHub ▸ Settings ▸ Secrets and variables ▸ Actions ▸ New repository secret**

| Secret | Purpose | Where to get it |
|---|---|---|
| `NCBI_API_KEY` | Higher PubMed/E‑utilities rate limits | [NCBI account ▸ API Key Management](https://www.ncbi.nlm.nih.gov/account/) |
| `ALTMETRIC_API_KEY` | Higher‑volume Altmetric access | [altmetric.com](https://www.altmetric.com/) |
| `CONTACT_EMAIL` | Polite User‑Agent for public APIs | your team email |

For local runs, copy `.env.example` to `.env` and fill in what you have.

---

## Customizing the dashboard

Almost everything is data‑driven from
[`pipeline/config.py`](pipeline/config.py) — no need to touch the fetching or
UI code:

- **Search terms & queries** — `LITERATURE_QUERIES`, `CLINICALTRIALS_QUERIES`, `NEWS_SEARCH_TERMS`.
- **News/grey‑literature feeds** — `DIRECT_FEEDS` (add any RSS/Atom feed).
- **Outlet name mapping** — `SOURCE_DOMAIN_MAP`, `PHARMA_HOSTS`.
- **Classification keywords** — `VACCINE_KEYWORDS`, `MONOCLONAL_KEYWORDS`, `ANIMAL_KEYWORDS`, `CANADA_KEYWORDS`, `BUNDIBUGYO_KEYWORDS`, etc.
- **Time windows** — `LITERATURE_SINCE`, `NEWS_WINDOW_DAYS`.

To change look & feel, edit `styles.css` (colours are CSS variables at the top,
using a colour‑blind‑safe palette). Labels and filters are in `app.js`.

---

## Run locally

```bash
# serve the site (any static server works)
python3 -m http.server 8080      # then open http://localhost:8080

# regenerate data from live sources (needs internet)
pip install -r pipeline/requirements.txt
python3 pipeline/update.py

# rebuild the initial curated seed instead (offline-friendly)
python3 pipeline/build_seed.py

# run the classification tests
python3 pipeline/test_classify.py
```

> Note: running `update.py` from inside some restricted corporate networks may
> be blocked from reaching the public APIs. It runs cleanly on GitHub Actions.

---

## Project structure

```
ebola-evidence-dashboard/
├── index.html              # dashboard markup
├── styles.css              # design system (light/dark, colour-blind-safe)
├── app.js                  # filtering, search, sort, charts, rendering
├── assets/favicon.svg
├── data/
│   └── evidence.json       # the dataset the site reads (updated daily)
├── pipeline/
│   ├── update.py           # main pipeline (run daily)
│   ├── sources.py          # source fetchers
│   ├── classify.py         # classification + inclusion rule
│   ├── config.py           # queries, feeds, keywords  ← tune me
│   ├── build_seed.py       # builds the initial curated seed
│   ├── reviewed_ids.txt    # curation: mark items reviewed
│   ├── test_classify.py    # tests
│   └── requirements.txt
├── .github/workflows/update.yml   # daily refresh
├── vercel.json
├── .env.example
└── README.md
```

## Data schema (each record)

```jsonc
{
  "id": "3f0e81ad50a40748",
  "title": "…",
  "summary": "…",
  "url": "https://doi.org/…",
  "doi": "10.3201/eid3208.260948",
  "source": "PubMed",                 // outlet / database
  "source_type": "journal_article",   // preprint | clinical_trial | news |
                                      // outbreak_report | guideline | press_release
  "source_type_label": "Journal article",
  "intervention": ["vaccine"],        // vaccine | monoclonal | other_therapeutic
  "intervention_labels": ["Vaccine"],
  "species": "animal",                // human | animal | na
  "bundibugyo": true,
  "canadian": false,
  "published_date": "2026-06-24",
  "first_seen": "2026-06-24",
  "reviewed": false,
  "is_new": true,
  "altmetric_score": 42.5,            // present once enriched (needs a DOI)
  "altmetric_url": "https://…",
  "journal": "Emerging infectious diseases",
  "authors": "Wight J, Schulz H, Banadyga L",
  "extra": { "pmid": "…", "nct_id": "…", "status": "RECRUITING", "phase": ["PHASE1"] }
}
```

---

## Notes & caveats

- This dashboard aggregates **public** evidence for situational awareness; it is
  **not** clinical or policy guidance.
- Automated classification is keyword‑based and occasionally imperfect — the
  “New / unreviewed” workflow exists precisely so a human can vet items.
- Feed URLs change occasionally; if a source goes quiet, update it in
  `DIRECT_FEEDS`.
- Altmetric scores appear only for items with a DOI and existing attention data.

*Alternative to Vercel's auto‑deploy:* if you prefer, create a Vercel **Deploy
Hook** and `curl` it at the end of the workflow instead of relying on the Git
integration.
