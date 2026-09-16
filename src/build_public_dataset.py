"""
build_public_dataset.py

Phase 6 prep: builds a compact, privacy-safe JSON file for the API to
serve. This is deliberately NOT the full topics.csv (248K+ rows of real
patient text) - that should never be shipped to a public-facing API or
frontend. Instead, this bundles:

  1. A summary of every topic (id, size, top terms, sentiment, condition)
     - no raw review text.
  2. Up to 3 example quotes PER TOPIC, pulled only from rows that are
     NOT flagged is_small_cell or is_quasi_identifying (same privacy
     rule enforced in build_insights.py for Phase 5) - EXCEPT topics in
     SENSITIVE_TOPIC_IDS below, which get zero quotes, full stop.
  3. The curated Phase 5 insights (from insights_verified.json), already
     privacy-checked.

Keeps the API's data contract dataset-agnostic per the project's ground
rules: the fields here (topic_id, n_reviews, top_terms, sentiment,
condition, example_quotes) don't assume anything WebMD-specific, so a
different dataset run through the same pipeline would produce a
same-shaped public_data.json.

SENSITIVE-CONTENT RULE: is_small_cell/is_quasi_identifying catch
cell-size and combination risk, not "this content is sensitive
regardless of size." Topic 636 (severe adverse events - deaths,
hospitalizations) has 112 reviews, well above any small-cell threshold,
so it would sail through that filter and produce real verbatim quotes
about patient deaths on a topic drill-down page. This is the same class
of miss caught in build_insights.py - fixed the same way here: any
topic_id in SENSITIVE_TOPIC_IDS gets its quote sampling skipped
entirely, independent of what the cell-size/quasi-id flags say. Keep
this in sync with SENSITIVE_INSIGHTS in build_insights.py.

Usage:
    python src/build_public_dataset.py
"""

import json
from pathlib import Path

import pandas as pd

# Topic IDs whose content is sensitive regardless of cell size - quote
# sampling is skipped entirely for these. Currently just topic 636 (the
# serious_adverse_events insight's underlying topic - see
# build_insights.py's SENSITIVE_INSIGHTS for the insight-level version
# of this same rule). Add a topic_id here any time a topic's content
# involves death, serious harm, or similarly sensitive personal
# narrative - this is a human judgment call, not something inferred
# automatically from the data.
SENSITIVE_TOPIC_IDS = {636}


def run():
    df = pd.read_csv("data/processed/topics.csv")

    required = ["topic_id", "Reviews", "Condition", "sentiment",
                "is_small_topic", "is_small_cell", "is_quasi_identifying"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"topics.csv missing columns: {missing}")

    topic_summary_path = Path("data/processed/topic_summary.json")
    with open(topic_summary_path) as f:
        topic_summary = json.load(f)

    public_topics = []
    for t in topic_summary:
        tid = t["topic_id"]
        subset = df[df["topic_id"] == tid]

        if tid in SENSITIVE_TOPIC_IDS:
            # Skipped entirely, not filtered - see SENSITIVE_TOPIC_IDS above.
            examples = []
        else:
            safe_pool = subset[(subset["is_small_cell"] == False) & (subset["is_quasi_identifying"] == False)]
            examples = safe_pool["Reviews"].astype(str).sample(
                min(3, len(safe_pool)), random_state=1
            ).tolist() if len(safe_pool) else []

        public_topics.append({
            "topic_id": tid,
            "n_reviews": t["n_reviews"],
            "top_terms": t["top_terms"],
            "avg_sentiment": t["avg_sentiment"],
            "top_condition": t["top_condition"],
            "is_small_topic": t.get("is_small_topic", False),
            "is_sensitive_no_quotes": tid in SENSITIVE_TOPIC_IDS,
            "example_quotes": examples,
        })

    insights_path = Path("data/processed/insights_verified.json")
    insights = {}
    if insights_path.exists():
        with open(insights_path) as f:
            raw_insights = json.load(f)
        # strip anything not meant for public display - keep description,
        # aggregate numbers, and already-vetted safe quotes only
        for name, ins in raw_insights.items():
            insights[name] = {
                "name": name,
                "description": ins["description"],
                "n_total_reviews": ins["n_total_reviews"],
                "avg_sentiment": ins["avg_sentiment"],
                "top_conditions": ins["top_conditions"],
                "top_drugs": ins["top_drugs"],
                "example_quotes": ins["safe_example_quotes"],
                "privacy_check_passed": ins["privacy_check_passed"],
            }
    else:
        print("WARNING: insights_verified.json not found - public_data.json will have no insights section.")

    public_data = {
        "topics": public_topics,
        "insights": insights,
        "meta": {
            "n_topics": len(public_topics),
            "n_insights": len(insights),
        },
    }

    out_path = Path("data/processed/public_data.json")
    with open(out_path, "w") as f:
        json.dump(public_data, f, indent=2)

    print(f"Saved {out_path}")
    print(f"  {len(public_topics)} topics, {len(insights)} insights")
    print(f"  This file (not the raw dataset) is what the API serves.")


if __name__ == "__main__":
    run()
