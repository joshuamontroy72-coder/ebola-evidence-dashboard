"""
Central configuration for the Ebola (Bundibugyo) Evidence Dashboard pipeline.

Everything the pipeline "knows" — what to search for, how to classify results,
which news sources to watch — lives here so you can tune the dashboard without
touching the fetching/classification logic.

Focus of this dashboard (set by the PHAC team):
  * Interventions for Ebola disease, with special interest in the Bundibugyo
    species (BDBV) and the ERVEBO (rVSV-ZEBOV) vaccine.
  * Vaccines (ANY vaccine) and other therapeutics (monoclonal antibodies,
    antivirals, etc.).
  * Evidence types: peer-reviewed journal articles, preprints, clinical trials,
    grey literature (news, WHO Disease Outbreak News, Africa CDC / NITAG
    guidance, pharma press releases).
  * Animal research is included ONLY for vaccines (animal therapeutic-only
    studies are filtered out).
  * Canadian evidence is flagged for easy filtering.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# General settings
# ---------------------------------------------------------------------------

# How far back literature searches reach on a *full* run (used for the initial
# backfill / seed). Daily runs still use this window but merge into history, so
# nothing already collected is ever lost.
LITERATURE_SINCE = "2014-01-01"

# How far back news / grey-literature searches reach. News is time-sensitive,
# so we keep a rolling window and let older items persist through history merge.
NEWS_WINDOW_DAYS = 120

# Max results to request per literature query (paged).
MAX_PER_QUERY = 300

# Optional API keys (raise rate limits / unlock features). Read from env so you
# can add them in GitHub -> Settings -> Secrets, or a local .env, at any time.
# The pipeline works fully WITHOUT any of these.
import os

NCBI_API_KEY = os.environ.get("NCBI_API_KEY", "").strip()
ALTMETRIC_API_KEY = os.environ.get("ALTMETRIC_API_KEY", "").strip()
CONTACT_EMAIL = os.environ.get("CONTACT_EMAIL", "ebola-dashboard@phac-aspc.gc.ca").strip()

USER_AGENT = f"EbolaEvidenceDashboard/1.0 (mailto:{CONTACT_EMAIL})"

# ---------------------------------------------------------------------------
# Literature queries (Europe PMC — covers PubMed/MEDLINE + preprints such as
# bioRxiv / medRxiv / Research Square in one API).
#
# Europe PMC query syntax reference:
# https://europepmc.org/searchsyntax
# ---------------------------------------------------------------------------

# Core disease scope. Bundibugyo-specific terms are boosted separately below.
_EBOLA_SCOPE = (
    '(ebola OR ebolavirus OR "ebola virus" OR "ebola virus disease" OR '
    'bundibugyo OR "sudan virus" OR "sudan ebolavirus" OR filovirus OR filoviridae)'
)

_VACCINE_TERMS = (
    '(vaccine OR vaccination OR vaccines OR immunization OR immunisation OR '
    'ERVEBO OR "rVSV-ZEBOV" OR "rVSVdeltaG-ZEBOV" OR "V920" OR "Ad26.ZEBOV" OR '
    'Zabdeno OR Mvabea OR "MVA-BN-Filo" OR ChAd3 OR ChAdOx1 OR "mRNA-1469" OR '
    '"Ad5-EBOV" OR GamEvac OR "prime-boost")'
)

_THERAPEUTIC_TERMS = (
    '("monoclonal antibody" OR "monoclonal antibodies" OR Inmazeb OR Ebanga OR '
    'ansuvimab OR atoltivimab OR maftivimab OR odesivimab OR mAb114 OR "MAb114" OR '
    '"REGN-EB3" OR ZMapp OR remdesivir OR favipiravir OR galidesivir OR '
    'antiviral OR therapeutic OR "post-exposure prophylaxis")'
)

# Each query is fetched, then results are classified & filtered downstream.
LITERATURE_QUERIES = [
    {
        "label": "Ebola vaccines",
        "query": f"{_EBOLA_SCOPE} AND {_VACCINE_TERMS}",
    },
    {
        "label": "Ebola therapeutics / monoclonals",
        "query": f"{_EBOLA_SCOPE} AND {_THERAPEUTIC_TERMS}",
    },
    {
        # Catch anything Bundibugyo-specific even if it doesn't obviously mention
        # an intervention term, so the team never misses BDBV literature.
        "label": "Bundibugyo (all)",
        "query": '(bundibugyo OR "bundibugyo virus" OR BDBV)',
    },
]

# ---------------------------------------------------------------------------
# ClinicalTrials.gov (API v2) queries
# ---------------------------------------------------------------------------

CLINICALTRIALS_QUERIES = [
    {
        "label": "Ebola vaccine trials",
        "cond": "Ebola OR Ebolavirus OR Bundibugyo OR Filovirus",
        "intr": "vaccine OR ERVEBO OR rVSV OR Ad26.ZEBOV OR mRNA-1469 OR ChAd3",
    },
    {
        "label": "Ebola therapeutic trials",
        "cond": "Ebola OR Ebolavirus OR Bundibugyo",
        "intr": "monoclonal antibody OR Inmazeb OR Ebanga OR ansuvimab OR mAb114 OR remdesivir OR ZMapp",
    },
]

# ---------------------------------------------------------------------------
# News & grey literature.
#
# Two mechanisms:
#   1. Google News RSS searches (keyless, aggregates across outlets). We tag the
#      real source from the article's own domain.
#   2. Direct RSS/Atom feeds from priority outlets (more reliable than search
#      for those specific sources).
#
# Preferred outlets called out by the team: CBC, CIDRAP, STAT, Reuters,
# WHO Disease Outbreak News, Africa CDC, plus pharma press releases.
# ---------------------------------------------------------------------------

# Google News RSS search terms. Kept tight to Ebola interventions so the feed
# stays relevant. `hl`/`gl`/`ceid` bias toward English + include Canada.
NEWS_SEARCH_TERMS = [
    "Ebola vaccine",
    "Bundibugyo Ebola",
    "ERVEBO Ebola vaccine",
    "Ebola monoclonal antibody",
    "Ebola treatment Inmazeb OR Ebanga",
    "Ebola outbreak Congo vaccine",
    "Ebola vaccine Canada",
    # guidance / advisory coverage (NITAG-style recommendations)
    "WHO Ebola vaccine recommendation OR prioritization",
    "SAGE OR NITAG OR TAG-CVP Ebola vaccine",
    "Africa CDC Ebola vaccine guidance",
]

# Direct feeds. `source` is the label we attach; `type` is the evidence type.
# NOTE: feed URLs occasionally change; if one goes quiet, update it here.
DIRECT_FEEDS = [
    {
        "source": "CIDRAP",
        "url": "https://www.cidrap.umn.edu/taxonomy/term/28/feed",
        "type": "news",
    },
    # NOTE: The legacy WHO DON RSS feed (https://www.who.int/feeds/entity/csr/don/en/rss.xml)
    # was retired and returns 0 items. WHO Disease Outbreak News is now fetched by the
    # dedicated fetch_who_don() function in sources.py, which uses targeted Google News
    # searches to find WHO DON pages about Ebola and classifies them as outbreak_report.
    {
        "source": "WHO News",
        "url": "https://www.who.int/rss-feeds/news-english.xml",
        "type": "news",
    },
    {
        "source": "CDC EID Journal",
        "url": "https://wwwnc.cdc.gov/eid/rss/ahead-of-print.xml",
        "type": "journal_article",
    },
    {
        "source": "Africa CDC",
        "url": "https://news.google.com/rss/search?q=Ebola%20vaccine%20site:africacdc.org&hl=en-US&gl=US&ceid=US:en",
        "type": "guideline",
    },
    # --- Preprint servers, monitored DIRECTLY (subject collections) ---------
    # Europe PMC also indexes preprints, but only after an ingestion lag of
    # days-to-weeks. These native bioRxiv/medRxiv subject feeds surface brand-
    # new preprints immediately; the off-topic majority is dropped by the
    # relevance filter, which requires an Ebola/Bundibugyo + intervention signal.
    {
        "source": "bioRxiv",
        "url": "https://connect.biorxiv.org/biorxiv_xml.php?subject=microbiology",
        "type": "preprint",
    },
    {
        "source": "bioRxiv",
        "url": "https://connect.biorxiv.org/biorxiv_xml.php?subject=immunology",
        "type": "preprint",
    },
    {
        "source": "medRxiv",
        "url": "https://connect.medrxiv.org/medrxiv_xml.php?subject=infectious_diseases",
        "type": "preprint",
    },
]

# ---------------------------------------------------------------------------
# WHO IRIS — the WHO publications / technical-guidance repository
# (iris.who.int). This is a SEPARATE channel from Disease Outbreak News and the
# WHO newsroom: it holds Technical Advisory Group (TAG/SAGE) reports, interim
# guidance, meeting reports, and other recommendation documents — i.e. the
# NITAG-style guidance the team wants. Queried via the DSpace REST search API.
# ---------------------------------------------------------------------------
WHO_IRIS_API = "https://iris.who.int/server/api/discover/search/objects"
WHO_IRIS_QUERIES = ["Bundibugyo", "Ebola vaccine", "Ebola therapeutic"]
# Only keep IRIS documents issued within this many days (avoids old archives).
WHO_IRIS_SINCE_DAYS = 1460  # ~4 years

# Map a URL host -> a clean, human-readable outlet name for display/filtering.
SOURCE_DOMAIN_MAP = {
    "cbc.ca": "CBC News",
    "cidrap.umn.edu": "CIDRAP",
    "statnews.com": "STAT",
    "reuters.com": "Reuters",
    "who.int": "WHO",
    "iris.who.int": "WHO IRIS",
    "biorxiv.org": "bioRxiv",
    "medrxiv.org": "medRxiv",
    "africacdc.org": "Africa CDC",
    "aljazeera.com": "Al Jazeera",
    "euronews.com": "Euronews",
    "apnews.com": "AP News",
    "theguardian.com": "The Guardian",
    "nature.com": "Nature",
    "science.org": "Science",
    "thelancet.com": "The Lancet",
    "nejm.org": "NEJM",
    "merck.com": "Merck (press release)",
    "modernatx.com": "Moderna (press release)",
    "regeneron.com": "Regeneron (press release)",
    "canada.ca": "Government of Canada",
    "healthycanadians.gc.ca": "Government of Canada",
    "gavi.org": "Gavi",
    "cepi.net": "CEPI",
}

# Hosts we treat as pharma press releases (evidence type = press_release).
PHARMA_HOSTS = {
    "merck.com", "modernatx.com", "regeneron.com", "jnj.com", "gsk.com",
    "bavarian-nordic.com", "iavi.org",
}

# ---------------------------------------------------------------------------
# Classification keyword banks (lower-cased matching against title + abstract)
# ---------------------------------------------------------------------------

VACCINE_KEYWORDS = [
    "vaccine", "vaccination", "vaccinated", "immunization", "immunisation",
    "ervebo", "rvsv", "zebov", "v920", "ad26.zebov", "ad26", "zabdeno",
    "mvabea", "mva-bn", "chad3", "chadox", "mrna-1469", "ad5-ebov", "gamevac",
    "prime-boost", "immunogenicity", "booster", "prophylactic vaccine",
]

# Monoclonal antibody / biologic therapeutics.
# Kept precise (named products + "monoclonal") so that vaccine immunogenicity
# papers — which routinely *measure* antibodies — aren't mislabelled as
# monoclonal-antibody therapeutics.
MONOCLONAL_KEYWORDS = [
    "monoclonal", "monoclonal antibody", "monoclonal antibodies",
    "inmazeb", "ebanga", "ansuvimab", "atoltivimab", "maftivimab",
    "odesivimab", "mab114", "regn-eb3", "zmapp", "gamezumab",
    "bispecific antibody", "neutralizing antibody therapy", "convalescent plasma",
]

# Other (small-molecule / antiviral) therapeutics
OTHER_THERAPEUTIC_KEYWORDS = [
    "remdesivir", "favipiravir", "galidesivir", "antiviral", "small molecule",
    "therapeutic", "treatment", "post-exposure prophylaxis", "drug",
]

BUNDIBUGYO_KEYWORDS = ["bundibugyo", "bdbv", "ebola-bundibugyo"]

# Animal-study signals (used to enforce "animal research only for vaccines").
ANIMAL_KEYWORDS = [
    "mice", "mouse", "murine", "ferret", "ferrets", "guinea pig", "guinea pigs",
    "nonhuman primate", "non-human primate", "nhp", "macaque", "macaques",
    "cynomolgus", "rhesus", "rodent", "hamster", "in vivo animal", "animal model",
    "animal models", "preclinical", "pre-clinical", "challenge model",
]

# Human-study signals (help distinguish from pure animal work).
HUMAN_KEYWORDS = [
    "patients", "participants", "healthy adults", "healthy volunteers",
    "clinical trial", "phase 1", "phase 2", "phase 3", "phase i", "phase ii",
    "phase iii", "vaccinees", "recipients", "human", "adults", "children",
    "infants", "pregnant", "cohort", "randomized", "randomised", "case",
    "outbreak", "ring vaccination",
]

# Canadian relevance signals.
CANADA_KEYWORDS = [
    "canada", "canadian", "phac", "public health agency of canada",
    "national microbiology laboratory", "winnipeg", "nml", "manitoba",
    "naci", "national advisory committee on immunization", "dalhousie",
    "university of toronto", "mcmaster", "ubc", "université laval", "quebec",
    "ontario", "vido", "saskatchewan", "health canada",
]
