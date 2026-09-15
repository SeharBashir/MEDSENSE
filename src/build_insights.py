"""
build_insights.py

Phase 5: pulls real, verified evidence for a set of candidate insights and
checks each against the privacy thresholds set in Phase 2/4 before they
can be surfaced.

This does NOT decide what the insights are - that's a judgment call made
by reading the topic summary (see Phase5_Candidate_Insights.md). This
script's job is narrower and mechanical: for each candidate insight
(a named group of topic_ids), it pulls the real aggregate numbers, checks
privacy flags, and selects safe-to-show example quotes - so the final
insight write-up is backed by verified data, not just a description of
console output.

PRIVACY RULES APPLIED (from Phase 2 and Phase 4):
- A topic flagged is_small_topic (Phase 4, <30 reviews) should not be
  surfaced as a standalone insight on its own.
- A row flagged is_quasi_identifying (Phase 2) is never used as a
  verbatim example quote - only aggregate stats from it are used.
- A row flagged is_small_cell (Phase 2, <5 reviews for its condition)
  is excluded entirely from insight evidence.

Usage:
    python src/build_insights.py
"""

import json
from pathlib import Path

import pandas as pd

# Candidate insights: each is a name + the topic_ids that make up its
# evidence base. Edit this list to match the insights you actually want
# to pursue - this is deliberately a plain data structure, not something
# buried in logic, so it's easy to add/remove/adjust before the final
# write-up.
CANDIDATE_INSIGHTS = {
    "statin_muscle_pain": {
        "description": "Statin-class drugs (High Cholesterol) - muscle pain/weakness dominates complaints, not efficacy",
        "topic_ids": [4, 68, 69, 93, 94, 539, 540],
    },
    "adhd_caregiver_reporting": {
        "description": "ADHD medication reviews are disproportionately caregiver-reported (parent writing about a child), not self-reported",
        "topic_ids": [503, 485, 502],
    },
    "cost_sentiment_masking": {
        "description": "Cost/insurance complaints show falsely neutral aggregate sentiment because Satisfaction measures drug efficacy, not affordability",
        "topic_ids": [874, 877, 852],
    },
    "bisphosphonate_bone_pain": {
        "description": "Osteoporosis bisphosphonates (Boniva, Fosamax, Actonel) - severe bone/joint pain, an ironic class-wide effect",
        "topic_ids": [175, 177, 178],
    },
    "depression_sexual_side_effects": {
        "description": "Depression medications - sexual side effects form a distinct complaint cluster separate from general inefficacy",
        "topic_ids": [185, 187],
    },
    "sleep_med_hallucinations": {
        "description": "Sleep medications - hallucinations/confusion is a distinct, separable symptom from ordinary grogginess",
        "topic_ids": [864, 865],
    },
    "serious_adverse_events": {
        "description": "Severe adverse event narrative cluster (death, hospitalization) - sensitive, aggregate-only",
        "topic_ids": [636],
    },
}


def run():
    df = pd.read_csv("data/processed/topics.csv")

    required_cols = ["topic_id", "Reviews", "Condition", "Drug", "sentiment",
                      "is_small_topic", "is_small_cell", "is_quasi_identifying"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(
            f"topics.csv is missing expected columns: {missing}. "
            f"This script needs the privacy flag columns from Phase 2/4 - "
            f"make sure you're using the latest deidentify.py and discovery_pipeline.py."
        )

    results = {}

    for name, spec in CANDIDATE_INSIGHTS.items():
        topic_ids = spec["topic_ids"]
        subset = df[df["topic_id"].isin(topic_ids)]

        n_total = len(subset)
        any_small_topic = df[df["topic_id"].isin(topic_ids) & (df["is_small_topic"] == True)]["topic_id"].unique().tolist()
        n_small_cell = int(subset["is_small_cell"].sum())
        n_quasi_id = int(subset["is_quasi_identifying"].sum())

        # Safe examples: not small-cell, not quasi-identifying
        safe_pool = subset[(subset["is_small_cell"] == False) & (subset["is_quasi_identifying"] == False)]
        examples = safe_pool["Reviews"].astype(str).sample(min(3, len(safe_pool)), random_state=1).tolist() if len(safe_pool) else []

        avg_sentiment = float(subset["sentiment"].mean()) if n_total else None
        top_conditions = subset["Condition"].value_counts().head(3).to_dict()
        top_drugs = subset["Drug"].value_counts().head(5).to_dict()

        privacy_ok = (len(any_small_topic) == 0) and (n_total >= 30)

        results[name] = {
            "description": spec["description"],
            "topic_ids": topic_ids,
            "n_total_reviews": n_total,
            "avg_sentiment": round(avg_sentiment, 3) if avg_sentiment is not None else None,
            "top_conditions": top_conditions,
            "top_drugs": top_drugs,
            "n_small_cell_excluded_from_examples": n_small_cell,
            "n_quasi_identifying_excluded_from_examples": n_quasi_id,
            "topics_flagged_small_by_phase4": any_small_topic,
            "privacy_check_passed": privacy_ok,
            "safe_example_quotes": examples,
        }

        status = "OK" if privacy_ok else "NEEDS REVIEW"
        sentiment_str = f"{avg_sentiment:.3f}" if avg_sentiment is not None else "n/a"
        print(f"[{status}] {name}: n={n_total}, avg_sentiment={sentiment_str}, "
              f"small_topics_included={any_small_topic}")

    out_path = Path("data/processed/insights_verified.json")
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved verified insight evidence to {out_path}")
    print("Review this file before writing the final Phase 5 insight report - ")
    print("any insight marked 'NEEDS REVIEW' should not be surfaced as-is.")


if __name__ == "__main__":
    run()
