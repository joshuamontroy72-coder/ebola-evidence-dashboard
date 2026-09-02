#!/usr/bin/env python3
"""
Lightweight tests for classification & the inclusion rule.
Run:  python pipeline/test_classify.py
No external dependencies; safe to run in CI.
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from classify import classify, passes_inclusion, is_relevant

CASES = []
def case(desc, rec, expect_intervention=None, expect_species=None,
         expect_included=None, expect_relevant=None,
         expect_bdbv=None, expect_canada=None):
    CASES.append((desc, rec, dict(intervention=expect_intervention, species=expect_species,
                                  included=expect_included, relevant=expect_relevant,
                                  bdbv=expect_bdbv, canada=expect_canada)))

# 1. Animal vaccine study -> kept
case("animal vaccine (ferret)",
     dict(title="rVSV-ZEBOV vaccine protects ferrets against Bundibugyo virus challenge",
          summary="Ferrets immunized with the Ebola vaccine survived lethal challenge.",
          source_type="journal_article"),
     expect_species="animal", expect_included=True, expect_bdbv=True)

# 2. Animal therapeutic (mAb) study -> DROPPED by inclusion rule
case("animal monoclonal (should drop)",
     dict(title="A monoclonal antibody protects macaques from Ebola virus",
          summary="Nonhuman primates treated with the monoclonal antibody survived.",
          source_type="journal_article"),
     expect_species="animal", expect_included=False)

# 3. Human clinical trial of a vaccine -> kept
case("human vaccine trial",
     dict(title="Phase 1 trial of an Ebola vaccine in healthy adults",
          summary="Healthy adult participants received the vaccine; immunogenicity assessed.",
          source_type="clinical_trial"),
     expect_species="human", expect_included=True)

# 4. Human therapeutic (mAb) -> kept
case("human monoclonal",
     dict(title="Inmazeb treatment for Ebola virus disease in patients",
          summary="Patients treated with the Inmazeb monoclonal antibody cocktail.",
          source_type="journal_article"),
     expect_species="human", expect_included=True)

# 5. Off-topic (no ebola) -> not relevant
case("off-topic monkeypox",
     dict(title="A monkeypox virus vaccine confers protection",
          summary="Mice vaccinated against monkeypox.", source_type="journal_article"),
     expect_relevant=False)

# 6. Canadian detection via affiliation
case("canadian via affiliation",
     dict(title="Immunogenicity of an Ebola vaccine",
          summary="Vaccine study.", source_type="journal_article",
          affiliations="National Microbiology Laboratory, Winnipeg, Manitoba, Canada"),
     expect_canada=True)

# 7. News about vaccine -> relevant + human-ish
case("news vaccine",
     dict(title="DR Congo begins Ebola vaccination with Ervebo",
          summary="Ervebo vaccine rollout begins.", source_type="news"),
     expect_relevant=True)


def main():
    failures = 0
    for desc, rec, exp in CASES:
        classify(rec)
        inc = passes_inclusion(rec)
        rel = is_relevant(rec)
        checks = []
        if exp["intervention"] is not None:
            checks.append(("intervention", exp["intervention"] in rec["intervention"]))
        if exp["species"] is not None:
            checks.append(("species", rec["species"] == exp["species"]))
        if exp["included"] is not None:
            checks.append(("included", inc == exp["included"]))
        if exp["relevant"] is not None:
            checks.append(("relevant", rel == exp["relevant"]))
        if exp["bdbv"] is not None:
            checks.append(("bundibugyo", rec["bundibugyo"] == exp["bdbv"]))
        if exp["canada"] is not None:
            checks.append(("canadian", rec["canadian"] == exp["canada"]))
        bad = [name for name, ok in checks if not ok]
        status = "ok " if not bad else "FAIL"
        if bad:
            failures += 1
            print(f"[{status}] {desc}  -> failed: {bad}  (species={rec['species']}, "
                  f"intervention={rec['intervention']}, included={inc}, relevant={rel})")
        else:
            print(f"[{status}] {desc}")
    print(f"\n{len(CASES)-failures}/{len(CASES)} passed")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
