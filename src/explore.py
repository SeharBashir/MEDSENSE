"""
explore.py

Phase 3 of the MedSense pipeline: exploration before building.

Reads ONLY from data/processed/deidentified.csv (never the raw file) and
produces a plain-text/console summary of:
  1. Domain vocabulary - most frequent meaningful words
  2. Domain-specific language patterns a generic sentiment model would
     miss: dosage mentions, discontinuation, comparison-to-another-drug,
     timing-of-onset language
  3. Sub-population breakdown by condition, with satisfaction differences
  4. Review volume over time
  5. Concrete example reviews for each pattern found, to ground the
     numbers in real evidence

This is exploration, not a pipeline step - it's meant to be read and
reasoned about, and to inform decisions in Phase 4 (embeddings/
clustering) and Phase 5 (insight selection), not to be run as part of
the production pipeline.

Usage:
    python src/explore.py
"""

import re
from collections import Counter

import pandas as pd

from config_loader import load_config

STOPWORDS = set("""a about above after again against all am an and any are aren't as at be because been before
being below between both but by can't cannot could couldn't did didn't do does doesn't doing don't down during
each few for from further had hadn't has hasn't have haven't having he he'd he'll he's her here here's hers
herself him himself his how how's i i'd i'll i'm i've if in into is isn't it it's its itself let's me more most
mustn't my myself no nor not of off on once only or other ought our ours ourselves out over own same shan't she
she'd she'll she's should shouldn't so some such than that that's the their theirs them themselves then there
there's these they they'd they'll they're they've this those through to too under until up very was wasn't we
we'd we'll we're we've were weren't what what's when when's where where's which while who who's whom why why's
with won't would wouldn't you you'd you'll you're you've your yours yourself yourselves im ive dont didnt""".split())

WORD_RE = re.compile(r"[a-z']+")

DOMAIN_PATTERNS = {
    "dosage mentions (mg/dose)": r"\bmg\b|\bdose\b|\bdosage\b",
    "discontinuation language": r"\bstopp?ed\b|\bquit\b|\bweaned?\b|\bdiscontinu|\bcame off\b|\bgot off\b",
    "comparison to another drug/treatment": r"\bcompared? to\b|\bswitched? (?:from|to)\b|\binstead of\b|\bversus\b",
    "side-effect timing (first days/weeks)": r"\bfirst (?:few )?(?:day|days|week|weeks)\b",
    "positive-but-clinical phrasing (sleep)": r"\bslept? through\b|\bfinally sleep|\bsleeping (?:through|better)\b",
    "tolerance/adjustment language": r"\bbody (?:got )?used to\b|\badjust(?:ed|ing)? to\b|\btolerance\b",
}


def top_vocabulary(reviews: pd.Series, n: int = 40, sample_size: int = 50000) -> list[tuple[str, int]]:
    counter = Counter()
    sample = reviews.sample(min(sample_size, len(reviews)), random_state=1)
    for text in sample:
        for word in WORD_RE.findall(str(text).lower()):
            if word not in STOPWORDS and len(word) > 2:
                counter[word] += 1
    return counter.most_common(n)


def domain_pattern_prevalence(reviews: pd.Series) -> dict[str, tuple[int, float]]:
    n = len(reviews)
    results = {}
    for label, pattern in DOMAIN_PATTERNS.items():
        count = reviews.str.contains(pattern, regex=True, na=False, case=False).sum()
        results[label] = (count, count / n * 100)
    return results


def example_for_pattern(reviews: pd.Series, pattern: str, n: int = 2) -> list[str]:
    matches = reviews[reviews.str.contains(pattern, regex=True, na=False, case=False)]
    return matches.head(n).tolist()


def run(config_path: str = "config/dataset_config.yaml"):
    config = load_config(config_path)
    cols = config["columns"]
    text_col = cols["text"]
    category_col = cols["category"]
    rating_col = cols["rating"]
    date_col = cols.get("date")

    df = pd.read_csv(config["processed_path"])
    reviews = df[text_col].astype(str)
    print(f"Loaded {len(df):,} de-identified reviews from {config['processed_path']}\n")

    print("=" * 70)
    print("1. TOP DOMAIN VOCABULARY (excluding common English stopwords)")
    print("=" * 70)
    for word, count in top_vocabulary(reviews):
        print(f"  {word:20s} {count:>6,}")

    print()
    print("=" * 70)
    print("2. DOMAIN-SPECIFIC LANGUAGE PATTERNS")
    print("   (things a generic sentiment score would likely miss)")
    print("=" * 70)
    prevalence = domain_pattern_prevalence(reviews)
    for label, (count, pct) in prevalence.items():
        print(f"  {label:45s} {count:>7,} reviews ({pct:.1f}%)")

    print()
    print("=" * 70)
    print("3. SUB-POPULATIONS BY CONDITION")
    print("=" * 70)
    top_conditions = df[category_col].value_counts().head(10)
    for cond, count in top_conditions.items():
        subset = df[df[category_col] == cond]
        avg_rating = subset[rating_col].mean()
        print(f"  {cond:45s} n={count:>6,}  avg {rating_col}={avg_rating:.2f}")

    if date_col and date_col in df.columns:
        print()
        print("=" * 70)
        print("4. REVIEW VOLUME OVER TIME")
        print("=" * 70)
        dates = pd.to_datetime(df[date_col], errors="coerce")
        by_year = dates.dt.year.value_counts().sort_index()
        for year, count in by_year.items():
            print(f"  {int(year)}: {count:>6,}")

    print()
    print("=" * 70)
    print("5. EXAMPLE REVIEWS PER PATTERN (for manual reading)")
    print("=" * 70)
    for label, pattern in DOMAIN_PATTERNS.items():
        print(f"\n--- {label} ---")
        for ex in example_for_pattern(reviews, pattern, n=2):
            print(f"  - {ex[:200]}")


if __name__ == "__main__":
    run()
