"""
Classification & filtering for evidence records.

Given a raw record (title, abstract/summary, etc.), we derive:
  * intervention tags: {vaccine, monoclonal, other_therapeutic}
  * species: human | animal | na
  * bundibugyo relevance (bool)
  * canadian relevance (bool)

And we enforce the team's inclusion rule:
  * Keep human evidence for any intervention.
  * Keep animal evidence ONLY when it concerns a vaccine.
  * Drop animal-only therapeutic studies.
"""

from __future__ import annotations

import re

from config import (
    VACCINE_KEYWORDS,
    MONOCLONAL_KEYWORDS,
    OTHER_THERAPEUTIC_KEYWORDS,
    BUNDIBUGYO_KEYWORDS,
    ANIMAL_KEYWORDS,
    HUMAN_KEYWORDS,
    CANADA_KEYWORDS,
)


def _contains_any(text: str, keywords) -> list[str]:
    """Return the list of keywords found in text (whole-word-ish matching)."""
    found = []
    for kw in keywords:
        # Word boundary match; keywords with punctuation (e.g. 'ad26.zebov')
        # fall back to a plain substring search.
        if re.search(r"[^a-z0-9]", kw):
            if kw in text:
                found.append(kw)
        else:
            if re.search(rf"\b{re.escape(kw)}\b", text):
                found.append(kw)
    return found


def classify(record: dict) -> dict:
    """Annotate a record in place with derived fields and return it."""
    text = " ".join(
        str(record.get(f, "") or "")
        for f in ("title", "summary", "journal", "keywords", "intervention_raw")
    ).lower()

    # --- intervention tags -------------------------------------------------
    interventions: list[str] = []
    matched: list[str] = []

    vac = _contains_any(text, VACCINE_KEYWORDS)
    mab = _contains_any(text, MONOCLONAL_KEYWORDS)
    oth = _contains_any(text, OTHER_THERAPEUTIC_KEYWORDS)

    if vac:
        interventions.append("vaccine")
        matched += vac
    if mab:
        interventions.append("monoclonal")
        matched += mab
    # Only tag "other_therapeutic" if there's a concrete antiviral/drug signal
    # and it isn't already captured as vaccine/monoclonal noise.
    concrete_other = [k for k in oth if k not in ("therapeutic", "treatment", "drug")]
    if concrete_other:
        interventions.append("other_therapeutic")
        matched += concrete_other
    elif oth and not interventions:
        # generic "treatment/therapeutic" with no vaccine/mab context
        interventions.append("other_therapeutic")
        matched += oth

    if not interventions:
        interventions.append("unspecified")

    # --- species -----------------------------------------------------------
    animal_hits = _contains_any(text, ANIMAL_KEYWORDS)
    human_hits = _contains_any(text, HUMAN_KEYWORDS)

    if animal_hits and not human_hits:
        species = "animal"
    elif animal_hits and human_hits:
        # Mixed signals: preclinical + clinical mention. Treat clinical-context
        # types (trials, news, guidance) as human; otherwise animal-leaning.
        species = "human" if record.get("source_type") in (
            "clinical_trial", "news", "guideline", "outbreak_report", "press_release"
        ) else "animal"
    elif human_hits:
        species = "human"
    else:
        species = "na"

    # --- bundibugyo & canada flags ----------------------------------------
    bundibugyo = bool(_contains_any(text, BUNDIBUGYO_KEYWORDS))
    canadian = bool(_contains_any(text, CANADA_KEYWORDS))
    # Affiliation / author field boosts Canadian detection.
    aff = str(record.get("affiliations", "") or "").lower()
    if aff and _contains_any(aff, CANADA_KEYWORDS):
        canadian = True

    record["intervention"] = interventions
    record["species"] = species
    record["bundibugyo"] = bundibugyo
    record["canadian"] = canadian
    record["keywords_matched"] = sorted(set(matched))
    return record


def passes_inclusion(record: dict) -> bool:
    """
    Enforce the team's inclusion rule:
      * animal research is kept ONLY when it concerns a vaccine
      * everything else (human / na species) is kept
    """
    if record.get("species") == "animal":
        return "vaccine" in record.get("intervention", [])
    return True


def is_relevant(record: dict) -> bool:
    """
    Guard against obviously off-topic items that slip through broad news
    searches. An item is relevant if it references Ebola/Bundibugyo/filovirus
    AND at least one intervention signal (vaccine/therapeutic), OR it is
    explicitly Bundibugyo-related.
    """
    text = " ".join(
        str(record.get(f, "") or "") for f in ("title", "summary")
    ).lower()

    ebola_signal = any(
        t in text for t in ("ebola", "ebolavirus", "bundibugyo", "filovirus", "bdbv")
    )
    if not ebola_signal:
        return False

    if record.get("bundibugyo"):
        return True

    intervention_signal = record.get("intervention", ["unspecified"]) != ["unspecified"]
    # For literature/trials we already searched on-topic, so accept.
    if record.get("source_type") in ("journal_article", "preprint", "clinical_trial"):
        return True
    # For news/grey lit, require an intervention signal to cut noise.
    return intervention_signal
