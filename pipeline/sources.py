"""
Source fetchers for the evidence pipeline.

Each fetcher returns a list of *raw* record dicts with a common shape:

    {
        "title": str,
        "summary": str,              # abstract / snippet
        "url": str,
        "doi": str | "",
        "source": str,               # human-readable outlet / database
        "source_type": str,          # journal_article | preprint | clinical_trial
                                     # | news | outbreak_report | guideline | press_release
        "published_date": "YYYY-MM-DD" | "",
        "journal": str,              # journal / venue (optional)
        "authors": str,              # author string (optional)
        "affiliations": str,         # for Canadian detection (optional)
        "extra": dict,               # source-specific extras (phase, status, ...)
    }

Downstream, classify.py adds intervention/species/flags and the pipeline adds
id / first_seen / altmetric / reviewed.

Every fetcher is defensive: network or parsing errors are caught and logged so
one failing source never breaks the daily run.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import time
import urllib.parse
from typing import Callable

import requests

try:
    import feedparser  # type: ignore
except Exception:  # pragma: no cover
    feedparser = None

from config import (
    LITERATURE_QUERIES,
    LITERATURE_SINCE,
    MAX_PER_QUERY,
    CLINICALTRIALS_QUERIES,
    NEWS_SEARCH_TERMS,
    NEWS_WINDOW_DAYS,
    DIRECT_FEEDS,
    SOURCE_DOMAIN_MAP,
    PHARMA_HOSTS,
    USER_AGENT,
    NCBI_API_KEY,
    ALTMETRIC_API_KEY,
    WHO_IRIS_API,
    WHO_IRIS_QUERIES,
    WHO_IRIS_SINCE_DAYS,
)

TODAY = dt.date.today()
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": USER_AGENT})
TIMEOUT = 30


def _log(msg: str) -> None:
    print(f"[sources] {msg}", flush=True)


def _get(url: str, params: dict | None = None, **kw):
    return SESSION.get(url, params=params, timeout=TIMEOUT, **kw)


def stable_id(*parts: str) -> str:
    raw = "|".join(p for p in parts if p).lower().strip()
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def host_of(url: str) -> str:
    try:
        netloc = urllib.parse.urlparse(url).netloc.lower()
        return netloc[4:] if netloc.startswith("www.") else netloc
    except Exception:
        return ""


def outlet_name(url: str, default: str) -> str:
    return SOURCE_DOMAIN_MAP.get(host_of(url), default)


# ---------------------------------------------------------------------------
# 1. Europe PMC — peer-reviewed journals + preprints (bioRxiv/medRxiv/etc.)
# ---------------------------------------------------------------------------

EUROPEPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"


def fetch_europepmc() -> list[dict]:
    records: list[dict] = []
    seen_ids: set[str] = set()
    date_clause = f"(FIRST_PDATE:[{LITERATURE_SINCE} TO {TODAY.isoformat()}])"

    for q in LITERATURE_QUERIES:
        query = f"({q['query']}) AND {date_clause}"
        _log(f"Europe PMC: {q['label']}")
        cursor = "*"
        got = 0
        while got < MAX_PER_QUERY:
            params = {
                "query": query,
                "format": "json",
                "pageSize": 100,
                "cursorMark": cursor,
                "resultType": "core",
                "sort": "P_PDATE_D desc",
            }
            try:
                r = _get(EUROPEPMC, params=params)
                r.raise_for_status()
                data = r.json()
            except Exception as e:  # noqa: BLE001
                _log(f"  ! Europe PMC error: {e}")
                break

            results = data.get("resultList", {}).get("result", [])
            if not results:
                break

            for it in results:
                epmc_id = f"{it.get('source','')}:{it.get('id','')}"
                if epmc_id in seen_ids:
                    continue
                seen_ids.add(epmc_id)

                doi = (it.get("doi") or "").strip()
                src = it.get("source", "")
                is_preprint = src == "PPR" or "preprint" in " ".join(
                    (it.get("pubTypeList", {}) or {}).get("pubType", [])
                ).lower()

                if doi:
                    url = f"https://doi.org/{doi}"
                elif it.get("pmid"):
                    url = f"https://pubmed.ncbi.nlm.nih.gov/{it['pmid']}/"
                else:
                    url = f"https://europepmc.org/article/{src}/{it.get('id','')}"

                journal = (it.get("journalInfo", {}) or {}).get("journal", {}).get(
                    "title", ""
                ) or it.get("journalTitle", "") or (
                    "Preprint" if is_preprint else ""
                )
                # bioRxiv/medRxiv servers show up in bookOrReportDetails / publisher
                if is_preprint and not journal:
                    journal = it.get("publisher", "") or "Preprint"

                records.append(
                    {
                        "title": (it.get("title") or "").strip().rstrip("."),
                        "summary": (it.get("abstractText") or "").strip(),
                        "url": url,
                        "doi": doi,
                        "source": "Europe PMC",
                        "source_type": "preprint" if is_preprint else "journal_article",
                        "published_date": _first_date(it),
                        "journal": journal,
                        "authors": it.get("authorString", ""),
                        "affiliations": _epmc_affiliations(it),
                        "extra": {
                            "pmid": it.get("pmid", ""),
                            "cited_by": it.get("citedByCount", 0),
                            "open_access": it.get("isOpenAccess", "N") == "Y",
                            "preprint_server": journal if is_preprint else "",
                        },
                    }
                )
                got += 1

            cursor = data.get("nextCursorMark", "")
            if not cursor or cursor == params["cursorMark"]:
                break
            time.sleep(0.34)

    _log(f"Europe PMC total: {len(records)}")
    return records


def _first_date(it: dict) -> str:
    for k in ("firstPublicationDate", "electronicPublicationDate", "pubDate"):
        v = it.get(k)
        if v:
            return v[:10]
    y = it.get("pubYear")
    return f"{y}-01-01" if y else ""


def _epmc_affiliations(it: dict) -> str:
    affs = []
    for a in (it.get("authorList", {}) or {}).get("author", []) or []:
        for aff in (a.get("authorAffiliationDetailsList", {}) or {}).get(
            "authorAffiliation", []
        ) or []:
            if aff.get("affiliation"):
                affs.append(aff["affiliation"])
    # Fallback single affiliation string
    if not affs and it.get("affiliation"):
        affs.append(it["affiliation"])
    return " | ".join(affs[:8])


# ---------------------------------------------------------------------------
# 2. ClinicalTrials.gov API v2
# ---------------------------------------------------------------------------

CTGOV = "https://clinicaltrials.gov/api/v2/studies"


def fetch_clinicaltrials() -> list[dict]:
    records: list[dict] = []
    seen: set[str] = set()

    for q in CLINICALTRIALS_QUERIES:
        _log(f"ClinicalTrials.gov: {q['label']}")
        page_token = None
        got = 0
        while got < MAX_PER_QUERY:
            params = {
                "query.cond": q["cond"],
                "query.intr": q["intr"],
                "pageSize": 100,
                "format": "json",
            }
            if page_token:
                params["pageToken"] = page_token
            try:
                r = _get(CTGOV, params=params)
                r.raise_for_status()
                data = r.json()
            except Exception as e:  # noqa: BLE001
                _log(f"  ! ClinicalTrials error: {e}")
                break

            studies = data.get("studies", [])
            if not studies:
                break

            for s in studies:
                ps = s.get("protocolSection", {})
                idm = ps.get("identificationModule", {})
                nct = idm.get("nctId", "")
                if not nct or nct in seen:
                    continue
                seen.add(nct)

                status_m = ps.get("statusModule", {})
                design_m = ps.get("designModule", {})
                cond_m = ps.get("conditionsModule", {})
                arms_m = ps.get("armsInterventionsModule", {})
                spon_m = ps.get("sponsorCollaboratorsModule", {})
                desc_m = ps.get("descriptionModule", {})
                loc_m = ps.get("contactsLocationsModule", {})

                interventions = [
                    i.get("name", "")
                    for i in arms_m.get("interventions", []) or []
                ]
                countries = sorted(
                    {
                        loc.get("country", "")
                        for loc in loc_m.get("locations", []) or []
                        if loc.get("country")
                    }
                )
                phases = design_m.get("phases", []) or []
                sponsor = spon_m.get("leadSponsor", {}).get("name", "")

                last_update = (
                    status_m.get("lastUpdatePostDateStruct", {}).get("date", "")
                    or status_m.get("startDateStruct", {}).get("date", "")
                )

                records.append(
                    {
                        "title": idm.get("briefTitle", "") or idm.get("officialTitle", ""),
                        "summary": desc_m.get("briefSummary", "")[:1200],
                        "url": f"https://clinicaltrials.gov/study/{nct}",
                        "doi": "",
                        "source": "ClinicalTrials.gov",
                        "source_type": "clinical_trial",
                        "published_date": _norm_date(last_update),
                        "journal": "",
                        "authors": sponsor,
                        "affiliations": sponsor + " | " + ", ".join(countries),
                        "intervention_raw": " ".join(interventions),
                        "extra": {
                            "nct_id": nct,
                            "status": status_m.get("overallStatus", ""),
                            "phase": phases,
                            "conditions": cond_m.get("conditions", []),
                            "interventions": interventions,
                            "sponsor": sponsor,
                            "countries": countries,
                            "enrollment": design_m.get("enrollmentInfo", {}).get("count"),
                        },
                    }
                )
                got += 1

            page_token = data.get("nextPageToken")
            if not page_token:
                break
            time.sleep(0.34)

    _log(f"ClinicalTrials total: {len(records)}")
    return records


def _norm_date(d: str) -> str:
    if not d:
        return ""
    # CT.gov dates can be YYYY-MM or YYYY-MM-DD
    parts = d.split("-")
    if len(parts) == 2:
        return f"{d}-01"
    return d[:10]


# ---------------------------------------------------------------------------
# 3. Direct RSS/Atom feeds (CIDRAP, WHO DON, EID, Africa CDC ...)
# ---------------------------------------------------------------------------


def _parse_feed(url: str):
    if feedparser is not None:
        return feedparser.parse(url, agent=USER_AGENT)
    # Minimal fallback if feedparser unavailable
    r = _get(url)
    return feedparser.parse(r.content) if feedparser else None


def fetch_direct_feeds() -> list[dict]:
    records: list[dict] = []
    if feedparser is None:
        _log("feedparser not installed; skipping direct feeds")
        return records

    cutoff = TODAY - dt.timedelta(days=NEWS_WINDOW_DAYS)

    for feed in DIRECT_FEEDS:
        _log(f"Feed: {feed['source']}")
        try:
            parsed = feedparser.parse(feed["url"], agent=USER_AGENT)
        except Exception as e:  # noqa: BLE001
            _log(f"  ! feed error: {e}")
            continue

        for entry in parsed.entries[:60]:
            link = entry.get("link", "")
            pub = _entry_date(entry)
            if pub and _to_date(pub) and _to_date(pub) < cutoff:
                continue
            title = entry.get("title", "").strip()
            summary = _clean_html(entry.get("summary", "") or entry.get("description", ""))
            # Prefer the real outlet name from the destination domain
            src_name = outlet_name(link, feed["source"])
            stype = feed["type"]
            if host_of(link) in PHARMA_HOSTS:
                stype = "press_release"
            records.append(
                {
                    "title": title,
                    "summary": summary[:800],
                    "url": link,
                    "doi": "",
                    "source": src_name,
                    "source_type": stype,
                    "published_date": pub,
                    "journal": "",
                    "authors": "",
                    "affiliations": "",
                    "extra": {"feed": feed["source"]},
                }
            )
    _log(f"Direct feeds total: {len(records)}")
    return records


# ---------------------------------------------------------------------------
# 4. Google News RSS searches (aggregates CBC / STAT / Reuters / etc.)
# ---------------------------------------------------------------------------

GNEWS = "https://news.google.com/rss/search"


def fetch_google_news() -> list[dict]:
    records: list[dict] = []
    if feedparser is None:
        _log("feedparser not installed; skipping Google News")
        return records

    cutoff = TODAY - dt.timedelta(days=NEWS_WINDOW_DAYS)

    for term in NEWS_SEARCH_TERMS:
        q = urllib.parse.quote(f'{term} when:{NEWS_WINDOW_DAYS}d')
        url = f"{GNEWS}?q={q}&hl=en-CA&gl=CA&ceid=CA:en"
        _log(f"Google News: {term}")
        try:
            parsed = feedparser.parse(url, agent=USER_AGENT)
        except Exception as e:  # noqa: BLE001
            _log(f"  ! news error: {e}")
            continue

        for entry in parsed.entries[:40]:
            link = entry.get("link", "")
            pub = _entry_date(entry)
            if pub and _to_date(pub) and _to_date(pub) < cutoff:
                continue
            title = entry.get("title", "").strip()
            # Google News appends " - Outlet" to titles; extract the outlet.
            outlet = ""
            if " - " in title:
                title_main, outlet = title.rsplit(" - ", 1)
                title = title_main.strip()
            src_name = outlet or outlet_name(link, "News")
            host = host_of(link)
            stype = "press_release" if host in PHARMA_HOSTS else "news"
            records.append(
                {
                    "title": title,
                    "summary": _clean_html(entry.get("summary", ""))[:500],
                    "url": link,
                    "doi": "",
                    "source": src_name.strip(),
                    "source_type": stype,
                    "published_date": pub,
                    "journal": "",
                    "authors": "",
                    "affiliations": "",
                    "extra": {"search_term": term},
                }
            )
    _log(f"Google News total: {len(records)}")
    return records


# ---------------------------------------------------------------------------
# 5. WHO IRIS — WHO publications / technical-guidance repository (DSpace REST)
# ---------------------------------------------------------------------------


def _iris_meta(md: dict, key: str) -> str:
    """DSpace metadata is {key: [{'value': ...}, ...]}; return the first value."""
    vals = md.get(key)
    if isinstance(vals, list) and vals:
        return vals[0].get("value", "") or ""
    return ""


def _iris_record(title, summary, uri, doi, date, handle):
    if len(date) == 4:
        date += "-01-01"
    return {
        "title": (title or "").strip().rstrip("."),
        "summary": _clean_html(summary or "")[:800],
        "url": uri,
        "doi": doi or "",
        "source": "WHO IRIS",
        "source_type": "guideline",
        "published_date": date[:10],
        "journal": "World Health Organization",
        "authors": "World Health Organization",
        "affiliations": "World Health Organization",
        "extra": {"handle": handle, "repository": "WHO IRIS"},
    }


def _iris_via_rest(query: str) -> list[dict]:
    """DSpace 7 REST discover API (primary)."""
    out = []
    params = {"query": query, "sort": "dc.date.issued,DESC", "size": 40, "dsoType": "item"}
    r = _get(WHO_IRIS_API, params=params, headers={"Accept": "application/json"})
    r.raise_for_status()
    data = r.json()
    objs = (
        data.get("_embedded", {}).get("searchResult", {})
        .get("_embedded", {}).get("objects", [])
    )
    for wrapper in objs:
        io = wrapper.get("_embedded", {}).get("indexableObject", {}) or wrapper.get("indexableObject", {})
        md = io.get("metadata", {}) or {}
        handle = io.get("handle", "")
        uri = _iris_meta(md, "dc.identifier.uri") or (f"https://iris.who.int/handle/{handle}" if handle else "")
        if not uri:
            continue
        out.append(_iris_record(
            _iris_meta(md, "dc.title"), _iris_meta(md, "dc.description.abstract"),
            uri, _iris_meta(md, "dc.identifier.doi"), _iris_meta(md, "dc.date.issued"), handle,
        ))
    return out


def _iris_via_opensearch(query: str) -> list[dict]:
    """DSpace OpenSearch Atom endpoint (fallback). Tries known path variants."""
    if feedparser is None:
        return []
    out = []
    for base in ("https://iris.who.int/server/opensearch/search",
                 "https://iris.who.int/opensearch/search"):
        url = f"{base}?query={urllib.parse.quote(query)}&format=atom&rpp=40&sort_by=dc.date.issued_dt&order=DESC"
        try:
            parsed = feedparser.parse(url, agent=USER_AGENT)
        except Exception:  # noqa: BLE001
            continue
        if not parsed.entries:
            continue
        for e in parsed.entries[:40]:
            link = e.get("link", "")
            if not link:
                continue
            out.append(_iris_record(
                e.get("title", ""), e.get("summary", ""), link, "",
                _entry_date(e) or "", "",
            ))
        if out:
            break
    return out


def fetch_who_iris() -> list[dict]:
    """
    WHO IRIS publications/guidance. Tries the DSpace REST API first, then the
    OpenSearch Atom endpoint as a fallback, so a change to one API shape does not
    silently drop this (important) guidance channel. Every path fails gracefully.
    """
    records: list[dict] = []
    seen: set[str] = set()
    cutoff = (TODAY - dt.timedelta(days=WHO_IRIS_SINCE_DAYS)).isoformat()

    for q in WHO_IRIS_QUERIES:
        _log(f"WHO IRIS: {q}")
        got = []
        for strategy in (_iris_via_rest, _iris_via_opensearch):
            try:
                got = strategy(q)
            except Exception as e:  # noqa: BLE001
                _log(f"  ! {strategy.__name__} failed: {e}")
                got = []
            if got:
                break
        for rec in got:
            uri = rec["url"]
            if uri in seen:
                continue
            if rec["published_date"] and rec["published_date"] < cutoff:
                continue
            seen.add(uri)
            records.append(rec)
    _log(f"WHO IRIS total: {len(records)}")
    return records


# ---------------------------------------------------------------------------
# 6. Altmetric enrichment (keyless badge API)
# ---------------------------------------------------------------------------

ALTMETRIC = "https://api.altmetric.com/v1/doi/"


def enrich_altmetric(records: list[dict], max_lookups: int = 400) -> None:
    """Attach altmetric_score / altmetric_url to records that have a DOI."""
    done = 0
    for rec in records:
        doi = rec.get("doi")
        if not doi or done >= max_lookups:
            continue
        try:
            url = ALTMETRIC + urllib.parse.quote(doi)
            params = {"key": ALTMETRIC_API_KEY} if ALTMETRIC_API_KEY else None
            r = _get(url, params=params)
            done += 1
            if r.status_code == 200:
                d = r.json()
                rec["altmetric_score"] = round(d.get("score", 0), 1)
                rec["altmetric_url"] = d.get("details_url", "")
                rec["altmetric_reads"] = d.get("readers_count", 0)
                rec["altmetric_mentions"] = d.get("cited_by_posts_count", 0)
            # 404 => no altmetric data; leave as None
        except Exception:  # noqa: BLE001
            pass
        time.sleep(0.2)  # be polite to the keyless endpoint
    _log(f"Altmetric lookups performed: {done}")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

import re
from html import unescape


def _clean_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _entry_date(entry) -> str:
    for k in ("published_parsed", "updated_parsed"):
        t = entry.get(k)
        if t:
            return dt.date(t.tm_year, t.tm_mon, t.tm_mday).isoformat()
    return ""


def _to_date(s: str):
    try:
        return dt.date.fromisoformat(s[:10])
    except Exception:
        return None


ALL_FETCHERS: list[tuple[str, Callable[[], list[dict]]]] = [
    ("Europe PMC (journals + preprints)", fetch_europepmc),
    ("ClinicalTrials.gov", fetch_clinicaltrials),
    ("WHO IRIS (guidance/technical reports)", fetch_who_iris),
    ("Direct feeds (CIDRAP/WHO/EID/Africa CDC/bioRxiv/medRxiv)", fetch_direct_feeds),
    ("Google News (CBC/STAT/Reuters/...)", fetch_google_news),
]
