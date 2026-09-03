"""
discovery_pipeline.py

Phase 4 of the MedSense pipeline: turns de-identified text into a set of
coherent topics with sentiment and supporting evidence attached.

Reads ONLY from data/processed/deidentified.csv (Phase 2's output).

THREE KEY DECISIONS, AND WHY (see Phase4_Research_Notes.md for full detail):

1. EMBEDDINGS: sentence-transformers ('all-MiniLM-L6-v2'), not TF-IDF.
   Tested TF-IDF + SVD first (fully offline-testable) - it found one
   genuinely coherent small cluster (generic-vs-brand-name complaints)
   but dumped 67% of reviews into unclustered noise and lumped much of
   the rest into one vague catch-all. TF-IDF only sees word overlap, not
   meaning - two reviews saying the same thing in different words look
   unrelated to it. Semantic embeddings solve exactly this, which is why
   they're worth the extra dependency for short consumer text like this.

2. CLUSTERING: HDBSCAN, not k-means - run on UMAP-reduced embeddings.
   The project spec explicitly warns that "not every algorithm handles
   outliers gracefully" - k-means forces every single review into some
   cluster, including ones that don't really belong anywhere, which
   would silently corrupt topic coherence. HDBSCAN is density-based: it
   finds naturally dense regions and explicitly labels sparse/atypical
   reviews as noise (-1) instead of forcing them into a topic. It also
   doesn't require guessing the number of topics upfront, which fits an
   exploratory discovery task.
   IMPORTANT: raw sentence embeddings are high-dimensional (384-d),
   where distance metrics become unreliable (curse of dimensionality) -
   measured directly: HDBSCAN on raw embeddings produced only 2 topics
   with 93%+ noise. Adding a UMAP dimensionality-reduction step first
   (standard practice in topic-modeling pipelines like BERTopic) fixed
   this - see reduce_dimensions() and Phase4_Research_Notes.md.

3. SENTIMENT: patient-given rating (Satisfaction/Effectiveness) as the
   PRIMARY signal, not a generic text sentiment model, when the dataset's
   config provides a rating column. This was investigated, not assumed:
   VADER (a standard general-purpose sentiment tool) was tested against
   this dataset's real Satisfaction ratings and only reached a 0.373
   correlation. Digging into the mismatches showed a structural cause,
   not a vocabulary quirk: reviews often narrate a before/after arc
   ("I had daily asthma attacks... now I don't" - negative words
   describing the PROBLEM, positive words for the OUTCOME) and list side
   effects (negative words) inside otherwise very positive reviews.
   Patching a sentiment lexicon with a handful of domain phrases (e.g.
   "slept through the night") did not move the correlation at all,
   because those specific phrases are too rare (~0.2% of reviews) to
   matter in aggregate - the problem is structural, not lexical.
   Since patients already told us how they felt via a rating, use that
   directly. VADER text sentiment is kept as a FALLBACK for datasets
   that don't have a rating column, so the pipeline still works on a
   different dataset shape.

Usage:
    python src/discovery_pipeline.py
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.preprocessing import normalize

from config_loader import load_config


def compute_embeddings(texts: list[str], cache_path: Path | None = None, force_recompute: bool = False):
    """
    Generates semantic embeddings using sentence-transformers.

    Caches the result to cache_path (a .npy file) so re-running the
    pipeline with different clustering parameters (min_cluster_size)
    doesn't require re-embedding from scratch - embedding a quarter
    million reviews can take ~2 hours, while re-clustering the cached
    embeddings takes minutes.

    NOTE: this downloads a ~90MB pretrained model from Hugging Face the
    first time it runs, so it needs an internet connection. If this
    fails with a connection error, check your network - some restricted
    environments (corporate proxies, sandboxed dev containers) block
    huggingface.co.
    """
    if cache_path and cache_path.exists() and not force_recompute:
        print(f"Loading cached embeddings from {cache_path} (use --force_recompute to regenerate) ...")
        return np.load(cache_path)

    from sentence_transformers import SentenceTransformer

    print("Loading sentence-transformer model (all-MiniLM-L6-v2) ...")
    model = SentenceTransformer("all-MiniLM-L6-v2")
    print(f"Embedding {len(texts):,} reviews (this may take a few minutes) ...")
    embeddings = model.encode(texts, show_progress_bar=True, batch_size=64)

    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        np.save(cache_path, embeddings)
        print(f"Cached embeddings to {cache_path} for faster re-runs.")

    return embeddings


def reduce_dimensions(embeddings, n_components: int = 10):
    """
    Reduces embedding dimensionality with UMAP before clustering.

    WHY THIS STEP EXISTS: sentence-transformer embeddings are
    high-dimensional (384 for all-MiniLM-L6-v2). Distance metrics
    (euclidean/cosine) become unreliable in that many dimensions - the
    "curse of dimensionality" - which starves HDBSCAN of the density
    signal it needs. This was measured directly, not assumed: running
    HDBSCAN straight on the raw embeddings produced only 2 topics with
    93%+ of reviews marked as noise. Adding this UMAP reduction step
    (the same approach used in established topic-modeling pipelines
    like BERTopic) dropped noise to ~31% and raised topic count to 70
    on an identical test sample - see Phase4_Research_Notes.md.
    """
    import umap

    reducer = umap.UMAP(n_components=n_components, metric="cosine", random_state=1,
                         n_neighbors=15, min_dist=0.0)
    return reducer.fit_transform(embeddings)


def cluster_embeddings(embeddings, min_cluster_size: int = 25, min_samples: int = 5):
    """
    HDBSCAN clustering, run on a UMAP-reduced version of the embeddings.
    See reduce_dimensions() and Phase4_Research_Notes.md for why the
    UMAP step is necessary. See module docstring for why HDBSCAN over
    k-means.
    """
    import hdbscan

    normalized = normalize(embeddings)
    reduced = reduce_dimensions(normalized)
    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=min_cluster_size,
        min_samples=min_samples,
        metric="euclidean",
    )
    labels = clusterer.fit_predict(reduced)
    return labels


def compute_sentiment(df: pd.DataFrame, rating_col: str | None, text_col: str) -> pd.Series:
    """
    Primary: patient-given rating, rescaled to -1..+1, when a rating
    column is configured. Falls back to VADER text sentiment when there
    is no rating column (keeps the pipeline usable on a dataset that
    doesn't have one) - see module docstring for why this ordering,
    based on measured investigation rather than assumption.
    """
    if rating_col and rating_col in df.columns:
        print(f"Using patient rating column '{rating_col}' as the primary sentiment signal.")
        min_r, max_r = df[rating_col].min(), df[rating_col].max()
        # rescale to -1..+1
        return 2 * (df[rating_col] - min_r) / (max_r - min_r) - 1
    else:
        print("No rating column configured - falling back to VADER text sentiment.")
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
        analyzer = SentimentIntensityAnalyzer()
        return df[text_col].astype(str).apply(lambda t: analyzer.polarity_scores(t)["compound"])


def flag_spam_reviews(texts: pd.Series) -> pd.Series:
    """
    Flags reviews that look like promotional spam rather than genuine
    patient feedback - e.g. reviews advertising a WhatsApp/Telegram
    contact, delivery/discount offers, or listing multiple controlled
    substances like a price catalog. Found during Phase 4 QA: several
    real clusters (n=25-60 each) turned out to be spam, not patient
    sentiment, and would have corrupted any insight built from them.

    This is a conservative heuristic, not a perfect classifier - it's
    meant to catch obvious cases, not every possible spam variant.
    """
    pattern = (
        r"\bwhatsapp\b|\btelegram\b|\bdiscount\b|\bdelivery\b.{0,20}\bdays?\b"
        r"|\[PHONE_REDACTED\].{0,50}\[NAME_REDACTED\]|\[NAME_REDACTED\].{0,50}\[PHONE_REDACTED\]"
    )
    return texts.str.contains(pattern, regex=True, na=False, case=False)


def flag_small_topics(labels, min_topic_size: int = 30) -> dict[int, bool]:
    """
    Mirrors Phase 2's small-cell logic, but at the topic level instead
    of the condition level. A narrowly-defined topic with very few
    reviews can be just as identifying as a rare condition, even if the
    condition itself isn't rare - e.g. a specific side-effect topic with
    only 25 reviews. Topics below this threshold should not be surfaced
    as a standalone insight in Phase 5 without the same excerpting care
    as Phase 2's quasi-identification flag.
    """
    counts = pd.Series(labels).value_counts()
    return {cid: (counts.get(cid, 0) < min_topic_size) for cid in set(labels) if cid != -1}


def top_terms_per_cluster(texts: list[str], labels, top_n: int = 8) -> dict[int, list[str]]:
    """
    Cheap, interpretable summary of what each cluster is "about": the
    TF-IDF terms most distinctive to that cluster vs. the rest of the
    corpus. This is just for human-readable labeling of clusters - the
    clustering itself is based on the semantic embeddings above, not this.
    """
    from sklearn.feature_extraction.text import TfidfVectorizer

    vectorizer = TfidfVectorizer(max_features=3000, stop_words="english", min_df=3)
    tfidf = vectorizer.fit_transform(texts)
    terms = np.array(vectorizer.get_feature_names_out())

    result = {}
    for cid in sorted(set(labels)):
        if cid == -1:
            continue
        mask = labels == cid
        cluster_mean = np.asarray(tfidf[mask].mean(axis=0)).flatten()
        top_idx = cluster_mean.argsort()[::-1][:top_n]
        result[cid] = terms[top_idx].tolist()
    return result


def run(config_path: str, sample_size: int | None, min_cluster_size: int, force_recompute: bool):
    config = load_config(config_path)
    cols = config["columns"]
    text_col = cols["text"]
    rating_col = cols.get("rating")
    category_col = cols.get("category")

    processed_path = Path(config["processed_path"])
    df = pd.read_csv(processed_path)
    print(f"Loaded {len(df):,} de-identified reviews.")

    if sample_size and sample_size < len(df):
        df = df.sample(sample_size, random_state=1).reset_index(drop=True)
        print(f"Sampled down to {len(df):,} rows for this run (use --sample_size to change).")

    # --- Spam filtering (found during Phase 4 QA) ---------------------------
    print("Checking for promotional spam disguised as reviews ...")
    is_spam = flag_spam_reviews(df[text_col].astype(str))
    n_spam = int(is_spam.sum())
    if n_spam:
        print(f"  Removing {n_spam:,} rows that look like spam/promotional content, not genuine reviews.")
        df = df[~is_spam].reset_index(drop=True)

    texts = df[text_col].astype(str).tolist()

    cache_path = Path("data/processed/embeddings_cache.npy") if not sample_size else None
    embeddings = compute_embeddings(texts, cache_path=cache_path, force_recompute=force_recompute)
    labels = cluster_embeddings(embeddings, min_cluster_size=min_cluster_size)
    df["topic_id"] = labels

    n_topics = len(set(labels)) - (1 if -1 in labels else 0)
    n_noise = int((labels == -1).sum())
    print(f"\nFound {n_topics} topics. {n_noise:,} reviews ({n_noise/len(df)*100:.1f}%) did not fit any topic (noise).")

    # --- Topic-level small-cell flag (mirrors Phase 2's condition-level one) -
    small_topic_flags = flag_small_topics(labels)
    df["is_small_topic"] = df["topic_id"].map(lambda t: small_topic_flags.get(t, False))

    df["sentiment"] = compute_sentiment(df, rating_col, text_col)

    terms = top_terms_per_cluster(texts, labels)

    print("\n=== Topic summary ===")
    summary_rows = []
    for cid in sorted(set(labels)):
        if cid == -1:
            continue
        mask = df["topic_id"] == cid
        subset = df[mask]
        avg_sentiment = subset["sentiment"].mean()
        top_condition = subset[category_col].mode().iloc[0] if category_col in df.columns and len(subset) else "n/a"
        is_small = small_topic_flags.get(cid, False)
        flag_str = " [SMALL - excerpt only, do not surface as standalone insight]" if is_small else ""
        print(f"Topic {cid} (n={mask.sum()}): terms={terms.get(cid, [])[:6]} "
              f"avg_sentiment={avg_sentiment:+.2f} top_condition={top_condition}{flag_str}")
        summary_rows.append({
            "topic_id": int(cid),
            "n_reviews": int(mask.sum()),
            "top_terms": terms.get(cid, []),
            "avg_sentiment": float(avg_sentiment),
            "top_condition": top_condition,
            "is_small_topic": bool(is_small),
        })

    out_path = Path("data/processed/topics.csv")
    df.to_csv(out_path, index=False)
    print(f"\nSaved per-review topic assignments and sentiment to {out_path}")

    summary_path = Path("data/processed/topic_summary.json")
    with open(summary_path, "w") as f:
        json.dump(summary_rows, f, indent=2)
    print(f"Saved topic summary to {summary_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Phase 4: embeddings, clustering, sentiment.")
    parser.add_argument("--config", default="config/dataset_config.yaml")
    parser.add_argument("--sample_size", type=int, default=None,
                         help="Optional: run on a random sample instead of the full dataset (useful for a first test run).")
    parser.add_argument("--min_cluster_size", type=int, default=25,
                         help="HDBSCAN min_cluster_size - smaller finds more, smaller topics; larger finds fewer, broader ones.")
    parser.add_argument("--force_recompute", action="store_true",
                         help="Recompute embeddings even if a cached version exists (e.g. after data changes).")
    args = parser.parse_args()
    run(args.config, args.sample_size, args.min_cluster_size, args.force_recompute)