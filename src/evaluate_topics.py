"""
evaluate_topics.py

Phase 4 QA: answers two questions raised in lead review of the discovery
pipeline, with real measurements instead of spot-checking.

1. COHERENCE: with 904 topics, eyeballing a handful isn't a real check.
   This computes an objective coherence score for EVERY topic - mean
   pairwise cosine similarity between the embeddings of reviews in that
   topic, compared against a random-pair baseline from the whole corpus.
   A topic that's genuinely coherent should score well above the random
   baseline; one that doesn't is worth a second look. This is also
   paired with a stratified random sample (not cherry-picked) across
   small/medium/large topics for manual reading - same QA pattern as
   evaluate_redaction.py in Phase 2.

2. SENTIMENT VALIDITY: the discovery pipeline uses the patient's overall
   Satisfaction rating as topic-level sentiment. That's the right choice
   for topics about the drug's core effect, but it's a mismatch for
   "aspect" topics - insurance/cost complaints, packaging, pharmacy
   switching - where someone can be very satisfied with the drug's
   effect (high Satisfaction) while the specific thing clustered here is
   a complaint about something else entirely. This computes a SEPARATE
   text-based sentiment (VADER) per topic and flags any topic where it
   diverges substantially from the rating-based sentiment already in
   topics.csv - that divergence is exactly the signal that a topic's
   "sentiment" number may not mean what it looks like it means.

Reads from data/processed/topics.csv and data/processed/embeddings_cache.npy
(both produced by discovery_pipeline.py) - does not touch raw/de-identified
text directly beyond what's already in topics.csv.

Usage:
    python src/evaluate_topics.py
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics.pairwise import cosine_similarity
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from config_loader import load_config


def compute_topic_coherence(embeddings: np.ndarray, labels: np.ndarray, n_baseline_pairs: int = 5000) -> dict:
    """
    For each topic, computes mean pairwise cosine similarity between the
    embeddings of reviews assigned to it. Also computes a random-pair
    baseline from the whole corpus (ignoring topic assignment) so the
    per-topic scores have something meaningful to compare against - a
    topic scoring similar to random pairs is not meaningfully coherent,
    whatever it looks like on a quick read.
    """
    rng = np.random.default_rng(1)
    n = len(embeddings)
    idx_a = rng.integers(0, n, n_baseline_pairs)
    idx_b = rng.integers(0, n, n_baseline_pairs)
    baseline_sims = np.array([
        cosine_similarity(embeddings[[a]], embeddings[[b]])[0, 0]
        for a, b in zip(idx_a, idx_b)
    ])
    baseline_mean = float(baseline_sims.mean())

    coherence = {}
    for cid in sorted(set(labels)):
        if cid == -1:
            continue
        mask = labels == cid
        topic_embeddings = embeddings[mask]
        if len(topic_embeddings) < 2:
            continue
        sims = cosine_similarity(topic_embeddings)
        # exclude diagonal (self-similarity = 1.0) from the mean
        n_topic = len(topic_embeddings)
        mean_sim = (sims.sum() - n_topic) / (n_topic * (n_topic - 1))
        coherence[int(cid)] = float(mean_sim)

    return {"baseline_random_pair_similarity": baseline_mean, "topic_coherence": coherence}


def compute_topic_text_sentiment(df: pd.DataFrame, text_col: str) -> pd.Series:
    """Per-review VADER text sentiment, independent of the patient rating."""
    analyzer = SentimentIntensityAnalyzer()
    return df[text_col].astype(str).apply(lambda t: analyzer.polarity_scores(t)["compound"])


def build_stratified_sample(df: pd.DataFrame, n_per_bucket: int = 8, seed: int = 1) -> pd.DataFrame:
    """
    Random (not cherry-picked) sample of topics across size buckets, so
    small, medium, and large topics all get manually checked, not just
    the large ones that are easiest to skim.
    """
    sizes = df.groupby("topic_id").size()
    sizes = sizes[sizes.index != -1]
    q1, q2 = sizes.quantile([0.33, 0.66])
    buckets = {
        "small": sizes[sizes <= q1].index,
        "medium": sizes[(sizes > q1) & (sizes <= q2)].index,
        "large": sizes[sizes > q2].index,
    }

    rows = []
    rng = np.random.default_rng(seed)
    for bucket_name, topic_ids in buckets.items():
        chosen = rng.choice(topic_ids, size=min(n_per_bucket, len(topic_ids)), replace=False)
        for tid in chosen:
            examples = df[df["topic_id"] == tid]["Reviews"].astype(str).head(3).tolist()
            rows.append({
                "topic_id": int(tid),
                "size_bucket": bucket_name,
                "n_reviews": int(sizes[tid]),
                "example_reviews": examples,
                "coherent_judgement": "",  # reviewer fills in: yes/no/unsure
                "notes": "",
            })
    return pd.DataFrame(rows)


def run(config_path: str, sentiment_divergence_threshold: float):
    config = load_config(config_path)
    cols = config["columns"]
    text_col = cols["text"]

    topics_path = Path("data/processed/topics.csv")
    embeddings_path = Path("data/processed/embeddings_cache.npy")

    print(f"Loading {topics_path} ...")
    df = pd.read_csv(topics_path)
    print(f"Loading cached embeddings from {embeddings_path} ...")
    embeddings = np.load(embeddings_path)

    if len(df) != len(embeddings):
        raise ValueError(
            f"Row count mismatch: topics.csv has {len(df)} rows but embeddings_cache.npy "
            f"has {len(embeddings)}. These must come from the same run - re-run "
            f"discovery_pipeline.py without --sample_size to regenerate both together."
        )

    labels = df["topic_id"].to_numpy()

    # --- 1. Coherence, computed for every topic, not a handful --------------
    print("Computing per-topic coherence (mean pairwise cosine similarity) ...")
    coherence_result = compute_topic_coherence(embeddings, labels)
    baseline = coherence_result["baseline_random_pair_similarity"]
    topic_coherence = coherence_result["topic_coherence"]

    coherence_df = pd.DataFrame([
        {"topic_id": tid, "coherence": score, "above_random_baseline": score > baseline}
        for tid, score in topic_coherence.items()
    ]).sort_values("coherence")

    n_below_baseline = (~coherence_df["above_random_baseline"]).sum()
    print(f"  Random-pair baseline similarity: {baseline:.3f}")
    print(f"  Topics scoring AT OR BELOW the random baseline: {n_below_baseline} / {len(coherence_df)}")
    print(f"  Mean topic coherence: {coherence_df['coherence'].mean():.3f}")
    print(f"  Weakest 5 topics (lowest coherence):")
    print(coherence_df.head(5).to_string(index=False))

    coherence_df.to_csv("data/processed/topic_coherence.csv", index=False)

    # --- 2. Sentiment validity: rating-based vs text-based, flag divergence -
    print("\nComputing text-based sentiment (VADER) per topic, comparing to rating-based sentiment ...")
    df["text_sentiment"] = compute_topic_text_sentiment(df, text_col)

    topic_sentiment = df.groupby("topic_id").agg(
        rating_sentiment=("sentiment", "mean"),
        text_sentiment=("text_sentiment", "mean"),
        n_reviews=("sentiment", "size"),
    ).reset_index()
    topic_sentiment = topic_sentiment[topic_sentiment["topic_id"] != -1]
    topic_sentiment["divergence"] = (topic_sentiment["rating_sentiment"] - topic_sentiment["text_sentiment"]).abs()
    topic_sentiment["flagged_divergent"] = topic_sentiment["divergence"] > sentiment_divergence_threshold

    n_flagged = topic_sentiment["flagged_divergent"].sum()
    print(f"  Topics where rating-sentiment and text-sentiment diverge by more than "
          f"{sentiment_divergence_threshold}: {n_flagged} / {len(topic_sentiment)}")
    print(f"  These are topics where 'this topic's sentiment' is ambiguous - the patient's overall\n"
          f"  rating and what the review text actually says about THIS topic don't agree.")

    if n_flagged:
        print("\n  Most divergent topics:")
        print(topic_sentiment.sort_values("divergence", ascending=False).head(10).to_string(index=False))

    topic_sentiment.to_csv("data/processed/topic_sentiment_validity.csv", index=False)

    # --- 3. Stratified manual-review sample (not cherry-picked) -------------
    print("\nBuilding a stratified random sample of topics for manual coherence review ...")
    sample_df = build_stratified_sample(df)
    sample_path = Path("data/processed/topic_manual_review_sample.csv")
    sample_df.to_csv(sample_path, index=False)
    print(f"  Saved {len(sample_df)} topics (small/medium/large, randomly chosen) to {sample_path}")
    print(f"  Open this file and fill in 'coherent_judgement' (yes/no/unsure) for each.")

    print("\nDone. Files written:")
    print("  data/processed/topic_coherence.csv           - objective coherence score for EVERY topic")
    print("  data/processed/topic_sentiment_validity.csv   - rating vs text sentiment per topic, divergence flagged")
    print("  data/processed/topic_manual_review_sample.csv - stratified random sample for manual read-through")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Phase 4 QA: topic coherence and sentiment validity.")
    parser.add_argument("--config", default="config/dataset_config.yaml")
    parser.add_argument("--sentiment_divergence_threshold", type=float, default=0.35,
                         help="Flag a topic if |rating_sentiment - text_sentiment| exceeds this.")
    args = parser.parse_args()
    run(args.config, args.sentiment_divergence_threshold)
