#!/usr/bin/env python3
"""
Build the INITIAL seed data/evidence.json from real records gathered via
curated sources (PubMed metadata + ClinicalTrials.gov + verified grey
literature), run through the SAME classification/inclusion logic the live
pipeline uses.

This exists only to give the dashboard a real, populated starting point.
Once deployed, pipeline/update.py refreshes and greatly expands the corpus
automatically each day. You never need to run this again.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import sys

sys.path.insert(0, os.path.dirname(__file__))

from classify import classify, passes_inclusion, is_relevant
from update import finalize, record_key, _counts, channel_of, CHANNELS
import sources

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA_FILE = ROOT / "data" / "evidence.json"
LIT_FILE = pathlib.Path(__file__).resolve().parent / "seed_literature.json"

MONTHS = {m: f"{i:02d}" for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


def norm_date(s: str) -> str:
    if not s:
        return ""
    s = s.strip()
    parts = s.split("-")
    y = parts[0]
    mo = parts[1] if len(parts) > 1 else "01"
    da = parts[2] if len(parts) > 2 else "01"
    mo = MONTHS.get(mo[:3], mo)  # convert "Oct" -> "10"
    if not mo.isdigit():
        mo = "01"
    if not da.isdigit():
        da = "01"
    return f"{y}-{int(mo):02d}-{int(da):02d}"


# ---------------------------------------------------------------------------
# Verified grey literature (news, WHO DON, guidance, press releases, 1 preprint)
# URLs, titles and dates verified via web search / page fetch, Aug-Sep 2026.
# ---------------------------------------------------------------------------
NEWS = [
    dict(title="Ebola disease caused by Bundibugyo virus – Democratic Republic of the Congo",
         summary="As of 26 August 2026 the outbreak reached 5,794 confirmed cases and 2,786 deaths across 60 health zones in six provinces. Vaccination using the Ervebo (rVSV-ZEBOV) vaccine began on 27 August for healthcare workers, though its effectiveness against Bundibugyo virus is unproven, while the PARTNERS clinical trial is enrolling patients to test treatments.",
         url="https://www.who.int/emergencies/disease-outbreak-news/item/2026-DON616",
         source="WHO Disease Outbreak News", source_type="outbreak_report",
         published_date="2026-08-28"),
    dict(title="WHO and Africa CDC welcome the allocation of Ebola vaccines to the Democratic Republic of the Congo",
         summary="WHO and Africa CDC welcomed the allocation of 70,000 doses of the Ervebo vaccine to the DRC; 20,000 doses are earmarked for a phase 3 clinical trial to determine whether Ervebo offers cross-protection against the Bundibugyo strain driving the outbreak.",
         url="https://www.who.int/news/item/20-08-2026-who-and-africa-cdc-welcome-the-allocation-of-ebola-vaccines-to-the-democratic-republic-of-the-congo",
         source="WHO", source_type="news", published_date="2026-08-20"),
    dict(title="WHO delivers Ebola vaccine to DR Congo to see if it can protect against Bundibugyo strain",
         summary="The WHO allocated 70,000 doses of Ervebo to the DRC, although the vaccine targets Ebola Zaire, not the Bundibugyo strain causing the current crisis. Twenty thousand doses will be used in a phase 3 trial to test cross-protection; WHO notes early laboratory and animal data suggest it may provide some protection.",
         url="https://www.cidrap.umn.edu/ebola/who-delivers-ebola-vaccine-dr-congo-see-if-it-can-protect-against-bundibugyo-strain",
         source="CIDRAP", source_type="news", published_date="2026-08-20"),
    dict(title="Talks on launch of clinical trial of Ebola vaccine in DRC advance, WHO says",
         summary="WHO says discussions have advanced on launching a clinical trial of the Ervebo Ebola vaccine in the Democratic Republic of the Congo to evaluate protection during the Bundibugyo virus outbreak.",
         url="https://www.statnews.com/2026/08/12/ebola-who-drc-ebola-vaccine-trial/",
         source="STAT", source_type="news", published_date="2026-08-12"),
    dict(title="DR Congo to receive 70,000 doses of Ervebo vaccine as Ebola infections surge",
         summary="The Democratic Republic of the Congo is to receive 70,000 doses of the Ervebo Ebola vaccine as Bundibugyo-virus infections surge, even though the vaccine was developed against the Zaire species.",
         url="https://www.aljazeera.com/news/2026/8/20/dr-congo-to-receive-70000-doses-of-ervebo-vaccine-as-ebola-infections-surge",
         source="Al Jazeera", source_type="news", published_date="2026-08-20"),
    dict(title="Congo begins Ebola vaccinations against world's fastest-growing outbreak",
         summary="The DRC began administering the Ervebo Ebola vaccine to health workers and contacts as it confronts the world's fastest-growing outbreak, caused by the Bundibugyo virus.",
         url="https://www.euronews.com/health/2026/08/28/congo-begins-ebola-vaccinations-against-worlds-fastest-growing-outbreak",
         source="Euronews", source_type="news", published_date="2026-08-28"),
    dict(title="Health Canada authorizes mRNA vaccine trial for Ebola virus causing huge outbreak in Congo",
         summary="Health Canada authorized Moderna to proceed with a Phase 1 clinical trial of an mRNA vaccine candidate against Bundibugyo virus. Canada is the second country after the UK to approve such a trial; the Public Health Agency of Canada's National Microbiology Laboratory in Winnipeg supports orthoebolavirus research.",
         url="https://www.cbc.ca/news/health/ebola-vaccine-trial-health-canada-moderna-9.7295616",
         source="CBC News", source_type="news", published_date="2026-08-04"),
    dict(title="Health Canada authorizes vaccine clinical trial for Ebola disease caused by the Bundibugyo virus",
         summary="Health Canada authorized Moderna to begin a Phase 1 clinical trial (authorized 30 July 2026) of its candidate mRNA vaccine for Ebola disease caused by the Bundibugyo virus. The Public Health Agency of Canada continues to support orthoebolavirus research through its National Microbiology Laboratory in Winnipeg and maintains an mRNA manufacturing collaboration with Moderna in Canada.",
         url="https://www.canada.ca/en/health-canada/news/2026/08/health-canada-authorizes-vaccine-clinical-trial-for-ebola-disease-caused-by-the-bundibugyo-virus.html",
         source="Government of Canada", source_type="guideline", published_date="2026-08-04"),
    dict(title="New Ebola vaccine trial launches as outbreak spreads in DR Congo",
         summary="A new Ebola vaccine trial launches as the Bundibugyo-virus outbreak spreads in the DRC, with WHO and partners deploying Ervebo and evaluating cross-protection.",
         url="https://news.un.org/en/story/2026/08/1168072",
         source="UN News", source_type="news", published_date="2026-08-21"),
    dict(title="Ebola vaccine enters Phase 3 trial. But will it work on a new target?",
         summary="The licensed Ervebo Ebola vaccine enters a Phase 3 trial in the DRC to test whether the Zaire-targeted vaccine can protect against the Bundibugyo species driving the 2026 outbreak.",
         url="https://cen.acs.org/pharmaceuticals/vaccines/ebola-vaccine-trial-drc/104/web/2026/08",
         source="Chemical & Engineering News", source_type="news", published_date="2026-08-26"),
    dict(title="Moderna Announces Initiation of Phase 1 Clinical Trial of mRNA-1469, Moderna's Investigational Vaccine Against Bundibugyo Ebolavirus",
         summary="Moderna announced the initiation of a Phase 1 clinical trial of mRNA-1469, its investigational mRNA vaccine against Bundibugyo ebolavirus, in response to the ongoing outbreak in the DRC.",
         url="https://finance.yahoo.com/healthcare/articles/moderna-announces-initiation-phase-1-150000501.html",
         source="Moderna (press release)", source_type="press_release", published_date="2026-08-04"),
    dict(title="Regeneron's Ebola Antibody Recommended by WHO for Investigational Use in Response to Current Bundibugyo Ebolavirus Outbreak",
         summary="Regeneron announced that WHO recommended its Ebola monoclonal antibody therapy Inmazeb (atoltivimab, maftivimab and odesivimab-ebgn) for investigational use in response to the current Bundibugyo ebolavirus outbreak.",
         url="https://investor.regeneron.com/news-releases/news-release-details/regenerons-ebola-antibody-recommended-world-health-organization",
         source="Regeneron (press release)", source_type="press_release", published_date="2026-05-28"),
    dict(title="Canada and the development of a vaccine for Bundibugyo virus",
         summary="MSF Canada describes Canada's longstanding role in Ebola vaccine science — including the rVSV-ZEBOV vaccine originally developed at the National Microbiology Laboratory in Winnipeg — and current efforts toward a Bundibugyo virus vaccine.",
         url="https://www.doctorswithoutborders.ca/canada-and-the-development-of-a-vaccine-for-bundibugyo-virus/",
         source="MSF Canada", source_type="news", published_date="2026-08-15"),
    dict(title="Congo to receive 70,000 doses of Ervebo Ebola vaccine, which has been effective in past outbreaks",
         summary="The DRC is to receive 70,000 doses of Merck's Ervebo Ebola vaccine, effective in past Zaire-species outbreaks, as it battles a Bundibugyo-virus epidemic.",
         url="https://www.inquirer.com/news/nation-world/congo-ebola-vaccines-ervebo-20260820.html",
         source="The Philadelphia Inquirer", source_type="news", published_date="2026-08-20"),
    dict(title="New studies to test whether existing Ebola vaccines can generate immune responses to Bundibugyo ebolavirus",
         summary="CEPI announced new studies to test whether licensed Ebola vaccines (including Ervebo and Ad26.ZEBOV/MVA-BN-Filo) can generate cross-reactive immune responses against Bundibugyo ebolavirus, drawing on laboratory and animal data.",
         url="https://cepi.net/new-studies-test-whether-existing-ebola-vaccines-can-generate-immune-responses-bundibugyo",
         source="CEPI", source_type="press_release", published_date="2026-06-05"),
    dict(title="Cross-protection against Bundibugyo by Ebola and Sudan vaccines",
         summary="Preprint reporting that vaccination with licensed Ebola (Zaire) and Sudan vaccines confers partial cross-protection against lethal Bundibugyo virus challenge in animal models, supporting emergency cross-species use.",
         url="https://www.biorxiv.org/content/10.64898/2026.06.10.731377v1",
         source="bioRxiv", source_type="preprint", published_date="2026-06-10",
         journal="bioRxiv (preprint)"),
    dict(title="rVSV-EBOV vaccination protects ferrets from lethal Bundibugyo virus disease",
         summary="An uncontrolled, rapidly growing outbreak of Bundibugyo virus (BDBV) is gripping the Democratic Republic of the Congo. There is no BDBV-specific vaccine, but emerging evidence suggests the Ebola virus-specific vaccine rVSV-EBOV (ERVEBO) may offer cross-protection. Evaluated in the uniformly lethal ferret model, all vaccinated animals survived BDBV challenge with minimal clinical signs, attributed to a moderate but protective humoral response — evidence supporting cross-protective efficacy of rVSV-EBOV and a potential role in mitigating the ongoing outbreak.",
         url="https://www.biorxiv.org/content/10.64898/2026.08.24.746878v1",
         doi="10.64898/2026.08.24.746878",
         source="bioRxiv", source_type="preprint", published_date="2026-08-26",
         journal="bioRxiv (preprint)",
         authors="Wight J, Liu G, Chan M, Medina SJ, Lu D, Cao W, Krosta SJ, Tierney K, Azaransky K, Banadyga L",
         affiliations="Special Pathogens Program, National Microbiology Laboratory, Public Health Agency of Canada, Winnipeg, Manitoba, Canada; Department of Medical Microbiology and Infectious Diseases, University of Manitoba, Winnipeg, Manitoba, Canada"),
    dict(title="WHO emergency guidance on the use of licensed Ebola vaccine during Bundibugyo virus disease outbreaks",
         summary="WHO interim guidance (31 August 2026), updating the 28 May 2026 guidance following SAGE review on 19 August 2026, on the off-label use of the licensed Ebola vaccine Ervebo (rVSV-EBOV-GP) during Bundibugyo virus disease (BDBV) outbreaks. Ervebo is licensed and WHO-prequalified against Zaire ebolavirus; its efficacy against the antigenically distinct BDBV is unknown. Animal challenge data (non-human primates and ferrets) and human immunogenicity data suggest possible but unquantified cross-protection against BDBV-related mortality, with little or no protection against viraemia and clinical disease. The guidance weighs benefit–risk of off-label use and supports an urgent ring-vaccination RCT of Ervebo and BDBV-specific candidates in the DRC.",
         url="https://doi.org/10.2471/B09884",
         doi="10.2471/B09884",
         source="WHO IRIS", source_type="guideline", published_date="2026-08-31",
         journal="World Health Organization",
         affiliations="World Health Organization; Strategic Advisory Group of Experts on Immunization (SAGE)"),
    dict(title="Third meeting of the WHO Technical Advisory Group on candidate vaccine prioritization (TAG-CVP) for Bundibugyo virus disease outbreak response",
         summary="WHO TAG-CVP meeting report (31 July 2026). Reviewing cross-protection evidence from animal challenge studies (ferret and non-human primate) and clinical immunogenicity data, the group recommended that Ervebo (rVSV-ZEBOV) be prioritized for inclusion in a Phase 3 ring-vaccination trial in the ongoing Bundibugyo outbreak — noting it could enter Phase 3 without an initial Phase 2 — while agreeing that a BDBV-specific vaccine remains the preferred option once one is ready. The pivotal ferret challenge study was funded by the Public Health Agency of Canada.",
         url="https://doi.org/10.2471/B09865",
         doi="10.2471/B09865",
         source="WHO IRIS", source_type="guideline", published_date="2026-07-31",
         journal="World Health Organization",
         affiliations="World Health Organization; Public Health Agency of Canada; University of Manitoba, Canada"),
]

# ---------------------------------------------------------------------------
# ClinicalTrials.gov records (from ClinicalTrials.gov API v2 search)
# ---------------------------------------------------------------------------
def T(nct, title, summary, date, status, phase, sponsor, intr, countries=""):
    return dict(
        title=title, summary=summary,
        url=f"https://clinicaltrials.gov/study/{nct}",
        source="ClinicalTrials.gov", source_type="clinical_trial",
        published_date=date, journal="", authors=sponsor,
        affiliations=f"{sponsor} | {countries}", intervention_raw=intr,
        extra=dict(nct_id=nct, status=status, phase=phase, sponsor=sponsor,
                   countries=[c for c in countries.split(",") if c]),
    )


TRIALS = [
    T("NCT07737717", "Phase 1 study of mRNA-1469 vaccine to prevent Ebola-Bundibugyo virus disease in healthy adults",
      "A Phase 1, observer-blind, placebo-controlled, dose-escalation study of Moderna's mRNA-1469 vaccine to prevent Ebola-Bundibugyo virus disease in healthy adults 18–65.",
      "2026-07-31", "RECRUITING", ["PHASE1"], "ModernaTX, Inc.", "mRNA-1469 vaccine placebo", "United States"),
    T("NCT06126822", "Ervebo and Zabdeno booster vaccines against Ebola virus in DRC (mix-and-match RCT)",
      "A Phase 3 randomized controlled trial evaluating Ervebo and Zabdeno booster vaccination in people previously vaccinated with the Zabdeno/Mvabea or Ervebo schedules in the DRC.",
      "2025-02-25", "RECRUITING", ["PHASE3"], "Institute of Tropical Medicine, Belgium", "Ervebo booster Zabdeno booster vaccine", "Congo"),
    T("NCT05909358", "Safety and immunogenicity of Sudan ebolavirus vaccines in Uganda",
      "A Phase 1/2 randomized placebo-controlled trial of Sudan ebolavirus vaccine candidates (cAd3, ChAdOx1, rVSV-SUDV) in Uganda.",
      "2024-01-15", "RECRUITING", ["PHASE1", "PHASE2"], "Makerere University", "cAd3 ChAdOx1 rVSV-SUDV vaccine", "Uganda"),
    T("NCT04822376", "Monoclonal antibody and vaccine post-exposure prophylaxis in high-risk Ebola contacts",
      "A Phase 2 pilot evaluating a post-exposure prophylaxis strategy combining the monoclonal antibody ansuvimab with the Ervebo vaccine in high-risk contacts of Ebola virus disease.",
      "2021-10-17", "COMPLETED", ["PHASE2"], "ANRS, Emerging Infectious Diseases", "ansuvimab monoclonal antibody Ervebo vaccine", "Guinea"),
    T("NCT05202288", "Immunogenicity of Ervebo vaccine administered with Inmazeb in healthy adults",
      "A Phase 2 trial assessing immunogenicity, safety and tolerability of the Ervebo vaccine administered together with the Inmazeb monoclonal antibody cocktail in healthy adults.",
      "2027-01-01", "NOT_YET_RECRUITING", ["PHASE2"], "ANRS, Emerging Infectious Diseases", "Ervebo vaccine Inmazeb monoclonal antibody", "France"),
    T("NCT03161366", "Safety and effectiveness of rVSVΔG-ZEBOV-GP (open-label)",
      "An open-label, single-arm Phase 3 study providing additional safety and effectiveness information on the rVSVΔG-ZEBOV-GP (Ervebo) vaccine, conducted during ring vaccination.",
      "2018-05-28", "COMPLETED", ["PHASE3"], "Epicentre", "rVSVΔG-ZEBOV-GP vaccine", "Congo,Guinea"),
    T("NCT02363322", "PREVAIL II: investigational therapeutics including ZMapp for Ebola infection",
      "A multicenter randomized study (PREVAIL II) of investigational therapeutics — the ZMapp monoclonal antibody cocktail plus standard of care — in patients with Ebola virus infection.",
      "2015-03-13", "COMPLETED", ["PHASE1", "PHASE2"], "National Institute of Allergy and Infectious Diseases (NIAID)", "ZMapp monoclonal antibody", "United States,Liberia,Guinea"),
    T("NCT03031912", "rVSVΔG-ZEBOV-GP (V920) Ebola vaccine in HIV-infected adults and adolescents",
      "A Phase 2 randomized, double-blind, placebo-controlled study of the V920 (rVSVΔG-ZEBOV-GP) Ebola vaccine in HIV-infected adults and adolescents, run by the Canadian Immunization Research Network.",
      "2017-08-01", "COMPLETED", ["PHASE2"], "Canadian Immunization Research Network", "V920 rVSVΔG-ZEBOV-GP vaccine", "Canada"),
    T("NCT02374385", "BPSC-1001 (VSVΔG-ZEBOV) Ebola vaccine dose-ranging study",
      "A Phase 1 randomized, double-blind, placebo-controlled dose-ranging study of the BPSC-1001 (VSVΔG-ZEBOV) Ebola vaccine candidate in healthy adults, led from Dalhousie University in Canada.",
      "2014-11-01", "COMPLETED", ["PHASE1"], "Dalhousie University", "BPSC-1001 VSVΔG-ZEBOV vaccine", "Canada"),
    T("NCT02788227", "PREPARE: rVSVΔG-ZEBOV-GP for pre-exposure prophylaxis in at-risk workers",
      "A multicenter Phase 2 study (PREPARE) of the rVSVΔG-ZEBOV-GP (V920) vaccine for pre-exposure prophylaxis in individuals at potential occupational risk of Ebola exposure.",
      "2016-10-14", "COMPLETED", ["PHASE2"], "National Institutes of Health Clinical Center", "rVSVΔG-ZEBOV-GP vaccine", "United States"),
    T("NCT03478891", "VRC 608: safety and pharmacokinetics of monoclonal antibody MAb114",
      "A Phase 1, open-label, dose-escalation study of the human monoclonal antibody MAb114 (VRC-EBOMAB092-00-AB) administered intravenously to healthy adults.",
      "2018-05-16", "COMPLETED", ["PHASE1"], "National Institute of Allergy and Infectious Diseases (NIAID)", "MAb114 monoclonal antibody", "United States"),
    T("NCT04717830", "Humanized monoclonal antibody (Gamezumab) for emergency prevention of Ebola",
      "An open study of the safety and pharmacokinetics of Gamezumab, a humanized monoclonal antibody drug for emergency prevention of Ebola virus disease.",
      "2021-02-15", "COMPLETED", ["PHASE1"], "Gamaleya Research Institute", "Gamezumab monoclonal antibody", "Russia"),
    T("NCT02509494", "Ad26.ZEBOV and MVA-BN-Filo prophylactic Ebola vaccine (Phase 3)",
      "A staged Phase 3 study, including a double-blind controlled stage, evaluating the two-dose Ad26.ZEBOV and MVA-BN-Filo prophylactic Ebola vaccine regimen.",
      "2015-09-30", "COMPLETED", ["PHASE3"], "Janssen Vaccines & Prevention B.V.", "Ad26.ZEBOV MVA-BN-Filo vaccine", "United States"),
    T("NCT04556526", "Ad26.ZEBOV / MVA-BN-Filo Ebola vaccine regimen in healthy pregnant women",
      "A Phase 3 open-label randomized trial of the two-dose Ad26.ZEBOV followed by MVA-BN-Filo Ebola vaccine regimen in healthy pregnant women.",
      "2020-10-05", "COMPLETED", ["PHASE3"], "Janssen Vaccines & Prevention B.V.", "Ad26.ZEBOV MVA-BN-Filo vaccine", "Congo,Rwanda"),
    T("NCT05301504", "Bivalent ChAdOx1 vaccine against Zaire and Sudan Ebola species",
      "A Phase 1 study to determine safety and immunogenicity of a bivalent ChAdOx1-vectored vaccine (ChAdOx1 biEBOV) against Zaire and Sudan Ebola virus species in healthy adults.",
      "2022-03-30", "COMPLETED", ["PHASE1"], "University of Oxford", "ChAdOx1 biEBOV vaccine", "Tanzania"),
    T("NCT04723602", "cAd3-EBO-S and cAd3-Marburg filovirus vaccines (Phase 1)",
      "A Phase 1b trial evaluating safety, tolerability and immune responses of two monovalent chimpanzee-adenovirus-vectored filovirus vaccines (cAd3-EBO-S and cAd3-Marburg) in healthy adults.",
      "2021-01-06", "COMPLETED", ["PHASE1"], "Albert B. Sabin Vaccine Institute", "cAd3-EBO-S cAd3-Marburg vaccine", "United States"),
    T("NCT05724472", "rVSVΔG-SEBOV-GP Sudan ebolavirus vaccine (Phase 1)",
      "A Phase 1, single-blind, placebo-controlled dose-escalation trial of the rVSVΔG-SEBOV-GP Sudan ebolavirus vaccine at three dose levels in healthy adults.",
      "2023-06-19", "COMPLETED", ["PHASE1"], "International AIDS Vaccine Initiative", "rVSVΔG-SEBOV-GP vaccine", "United States,Kenya"),
    T("NCT02533791", "Recombinant adenovirus vector Ebola vaccine (Ad5-EBOV) booster (Phase 1)",
      "A Phase 1 study of a booster dose of the recombinant adenovirus type-5 vectored Ebola vaccine (Ad5-EBOV) in healthy adults after primary immunization.",
      "2015-07-01", "COMPLETED", ["PHASE1"], "Jiangsu Province CDC", "Ad5-EBOV vaccine", "China"),
]


def load_literature():
    items = json.loads(LIT_FILE.read_text(encoding="utf-8"))
    for it in items:
        it["published_date"] = norm_date(it.get("published_date", ""))
        it.setdefault("extra", {})
    return items


def main():
    raw = load_literature() + NEWS + TRIALS
    today = dt.date.today().isoformat()

    kept = {}
    dropped_animal = dropped_off = 0
    for rec in raw:
        rec.setdefault("doi", "")
        rec.setdefault("journal", "")
        rec.setdefault("authors", "")
        rec.setdefault("affiliations", "")
        rec.setdefault("extra", {})
        classify(rec)
        if not is_relevant(rec):
            dropped_off += 1
            continue
        if not passes_inclusion(rec):
            dropped_animal += 1
            continue
        rec["id"] = sources.stable_id(record_key(rec))
        # Seed initialization: treat an item's publication date as when it was
        # "first seen" so the New/unreviewed badge reflects genuine recency on
        # day one. The live pipeline stamps first_seen = discovery date onward.
        pd = rec.get("published_date", "")
        rec["first_seen"] = pd if (pd and pd <= today) else today
        rec["reviewed"] = False
        kept[rec["id"]] = rec

    records = [finalize(r) for r in kept.values()]
    records.sort(key=lambda r: (r.get("published_date") or "", r.get("first_seen") or ""),
                 reverse=True)

    run_by_channel = {c: 0 for c in CHANNELS}
    for r in records:
        run_by_channel[channel_of(r)] = run_by_channel.get(channel_of(r), 0) + 1

    payload = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "record_count": len(records),
        "new_last_run": len(records),
        "counts": _counts(records),
        "source_status": {"seed": len(records)},
        "coverage": {
            "channels": CHANNELS,
            "run_counts": run_by_channel,
            "fetcher_errors": [],
        },
        "records": records,
    }
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Seed written: {len(records)} records "
          f"(dropped {dropped_animal} animal-therapeutic, {dropped_off} off-topic)")
    print("By type:", payload["counts"]["by_type"])
    print("By intervention:", payload["counts"]["by_intervention"])
    print("By species:", payload["counts"]["by_species"])
    print("Bundibugyo:", payload["counts"]["bundibugyo"], "| Canadian:", payload["counts"]["canadian"])


if __name__ == "__main__":
    main()
