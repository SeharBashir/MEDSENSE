"""
deidentify.py

Phase 2 of the MedSense pipeline: privacy protection.

This is meant to run FIRST, before any embedding/clustering/exploration
touches the raw text. It does three things, matching the project spec:

1. DIRECT IDENTIFIERS
   Scrubs names, emails, phone numbers, and URLs out of the free-text
   review column using a combination of regex (fast, catches structured
   PII like emails/phones) and spaCy NER (catches names, which regex
   can't reliably find).

2. SMALL-CELL EXPOSURE
   Counts how many reviews exist per subgroup (here: per Condition).
   Any subgroup with fewer than `min_cell_count` reviews is flagged as
   `is_small_cell = True`. Later phases must NOT surface a subgroup-level
   stat/insight for any row where this is True.

3. QUASI-IDENTIFICATION THROUGH COMBINATION
   Flags individual rows where a rare condition is combined with a
   specific age bracket + sex - the kind of record that could identify
   someone through combination even with no name attached. Rows flagged
   `is_quasi_identifying = True` must be excerpted (not shown in full)
   if ever used as supporting evidence for an insight.

Output: a new CSV (data/processed/deidentified.csv) that every later
pipeline phase reads from. Nothing downstream should ever read the raw
CSV directly.

Usage:
    python src/deidentify.py
    python src/deidentify.py --config config/dataset_config.yaml
"""

import argparse
import difflib
import re
import sys
from pathlib import Path

import pandas as pd
import spacy
from tqdm import tqdm

from config_loader import load_config

# --------------------------------------------------------------------------
# Regex patterns for structured direct identifiers.
# These run before NER because they're cheap and reliable for
# well-formed patterns that NER often misses (e.g. emails, phone numbers).
# --------------------------------------------------------------------------
# Allows optional whitespace around the @ sign (e.g. "name @ yahoo.com") -
# a gap found during manual QA where a real email with a space before the
# @ was missed by the strict no-space version of this pattern.
EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+\s*@\s*[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
# Matches US-style phone numbers (with or without separators/parens) AND
# international numbers written as +<country code><digits> with no
# separators, e.g. "+2348064460510" - a gap found during manual QA
# (evaluate_redaction.py) where a Nigerian-format number was initially missed.
PHONE_RE = re.compile(
    r"(\+?1[-.\s]?)?\(?\b[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}\b"
    r"|\+[0-9]{7,15}\b"
)
URL_RE = re.compile(r"https?://\S+|www\.\S+")


def scrub_structured_pii(text: str) -> str:
    """Regex pass: emails, phone numbers, URLs."""
    text = EMAIL_RE.sub("[EMAIL_REDACTED]", text)
    text = PHONE_RE.sub("[PHONE_REDACTED]", text)
    text = URL_RE.sub("[URL_REDACTED]", text)
    return text


def dedupe_scraping_duplicates(df: pd.DataFrame, text_col: str, drug_id_col: str | None) -> pd.DataFrame:
    """
    Collapses scraping-duplicate rows: the same patient review scraped once
    per drug-formulation-label sub-page (e.g. "lisinopril" and "lisinopril
    solution" are the same DrugId, same review, just a different label).

    Investigated during Phase 1 feedback: of all duplicate-text groups in
    the raw WebMD data, 99.4% share the same DrugId and differ only in the
    formulation-label string in the Drug column. Only 0.6% are genuinely
    different drugs sharing duplicate text (a couple of which were
    spam-like reviews advertising an outside service).

    Deduping on (DrugId, review text) - rather than review text alone -
    collapses the formulation-scraping duplicates while leaving genuine
    same-text-different-drug rows alone. This must run BEFORE small-cell
    and quasi-identification counting, since those counts would otherwise
    over-count how many distinct people are behind a given condition.

    If the dataset has no drug_id column configured, falls back to
    deduping on review text alone and prints a warning, since the
    pipeline needs to stay usable on datasets without that field.
    """
    before = len(df)
    if drug_id_col and drug_id_col in df.columns:
        df = df.drop_duplicates(subset=[drug_id_col, text_col], keep="first")
    else:
        print("  WARNING: no drug_id column configured - deduping on review text alone. "
              "This may under-dedupe (miss formulation-label scraping duplicates) or "
              "over-dedupe (collapse different patients' near-identical short reviews). "
              "Configure 'drug_id' in dataset_config.yaml if this dataset has one.")
        df = df.drop_duplicates(subset=[text_col], keep="first")
    removed = before - len(df)
    print(f"  Removed {removed:,} scraping-duplicate rows ({removed/before*100:.1f}% of rows entering this step). "
          f"{len(df):,} rows remain.")
    return df


def build_known_drug_terms(df: pd.DataFrame, drug_col: str | None) -> set[str]:
    """
    Builds a lowercase set of drug-name tokens from the dataset's own
    drug column. Used to stop NER from mistaking a drug name for a
    person's name (e.g. "Zoloft", "Coumadin").

    We add both the full drug name and its individual words, since
    NER sometimes only tags one word of a multi-word drug name.
    """
    known = set()
    if not drug_col or drug_col not in df.columns:
        return known
    for name in df[drug_col].dropna().astype(str).unique():
        name_lower = name.lower().strip()
        known.add(name_lower)
        for token in re.findall(r"[a-z]+", name_lower):
            if len(token) > 2:  # skip tiny tokens like "mg", "hr"
                known.add(token)
    return known


# Common medical eponyms/condition terms that don't reliably appear as
# exact substrings of the dataset's own Condition column, but that NER
# regularly mistakes for a person's name (eponyms ARE literally named
# after people). Added after Phase 2 QA + lead feedback found these
# being swept up as false-positive redactions - a real cost, since these
# are exactly the clinically meaningful terms topic modeling will need
# in Phase 4. This is a curated, documented starting list, not a claim
# of exhaustive medical-ontology coverage.
KNOWN_MEDICAL_EPONYMS_AND_TERMS = {
    "sjogren", "sjogren's", "sjogrens",
    "meniere", "meniere's", "menieres",
    "stevens-johnson", "stevens",
    "asperger", "asperger's", "aspergers",
    "parkinson", "parkinson's", "parkinsons",
    "alzheimer", "alzheimer's", "alzheimers",
    "crohn", "crohn's", "crohns",
    "graves",
    "raynaud", "raynaud's", "raynauds",
    "tourette", "tourette's", "tourettes",
    "addison", "addison's", "addisons",
    "cushing", "cushing's", "cushings",
    "hashimoto", "hashimoto's", "hashimotos",
    "sciatica",
    "degenerative", "disc",
    "interstitial", "cystitis",
    "lupus",
    "bipolar",
    "fibromyalgia",
}


def build_known_clinical_terms(df: pd.DataFrame, category_col: str | None) -> set[str]:
    """
    Builds a lowercase set of clinical/condition terms from the dataset's
    own Condition column (same approach as build_known_drug_terms),
    combined with the small curated eponym list above for terms that
    don't reliably appear in the Condition column as written.
    """
    known = set(KNOWN_MEDICAL_EPONYMS_AND_TERMS)
    if not category_col or category_col not in df.columns:
        return known
    for name in df[category_col].dropna().astype(str).unique():
        name_lower = name.lower().strip()
        known.add(name_lower)
        for token in re.findall(r"[a-z]+", name_lower):
            if len(token) > 3:  # skip tiny/common tokens
                known.add(token)
    return known


def build_word_casing_stats(texts: list[str]) -> dict[str, float]:
    """
    Scans the corpus once to compute, for each lowercase word, what
    fraction of its occurrences are capitalized (Title-case or ALLCAPS
    first letter) vs. lowercase.

    Real personal names are almost always capitalized consistently
    wherever they appear. Ordinary English words that spaCy's NER
    sometimes mistakes for names when they land at the start of a
    sentence ("Began", "Felt", "God", "Took") overwhelmingly appear in
    lowercase elsewhere in the same corpus, since most of their
    occurrences aren't at a sentence boundary.

    Returns: {lowercase_word: capitalized_fraction} for words that
    appear at least MIN_OCCURRENCES times, so the signal is reliable.
    This works on ANY dataset's own text - no external word list or
    model needed, keeping the pipeline dataset-agnostic.
    """
    MIN_OCCURRENCES = 5
    word_re = re.compile(r"[A-Za-z']+")
    total_counts: dict[str, int] = {}
    cap_counts: dict[str, int] = {}

    for text in texts:
        for word in word_re.findall(str(text)):
            lower = word.lower()
            total_counts[lower] = total_counts.get(lower, 0) + 1
            if word[0].isupper():
                cap_counts[lower] = cap_counts.get(lower, 0) + 1

    casing_stats = {}
    for word, total in total_counts.items():
        if total >= MIN_OCCURRENCES:
            casing_stats[word] = cap_counts.get(word, 0) / total
    return casing_stats


def is_likely_common_word(word: str, casing_stats: dict[str, float], threshold: float = 0.5) -> bool:
    """
    A word is treated as "probably not a name" if it appears capitalized
    less than `threshold` of the time elsewhere in the corpus - i.e. it's
    normally a lowercase word (a verb, common noun, etc.) that only
    happened to be capitalized here because it started a sentence.
    """
    lower = word.lower()
    if lower not in casing_stats:
        return False  # not enough data - don't guess, fall through to other checks
    return casing_stats[lower] < threshold


def fuzzy_matches_known_term(word: str, known_terms: set[str], cutoff: float = 0.82) -> bool:
    """
    Catches misspelled drug/condition names that don't exact-match the
    known-term list (e.g. "Zomigvtab" vs "Zomig", "Bacrtim" vs "Bactrim",
    "Clonazapam" vs "Clonazepam") using simple string similarity.
    Only checks words of reasonable length to avoid noisy short-word
    matches, and only against a sample of known terms for speed.
    """
    word_lower = word.lower()
    if len(word_lower) < 5:
        return False
    close = difflib.get_close_matches(word_lower, known_terms, n=1, cutoff=cutoff)
    return len(close) > 0


COMMON_ABBREVIATIONS_AND_RELATIONS = {
    "dr", "mr", "mrs", "ms", "dr.", "mom", "dad", "mother", "father",
    "gyno", "obgyn", "gp", "er", "icu", "hs", "prn", "bid", "tid", "qid",
    "mg", "ml", "mcg", "kg", "lb", "hr", "hrs", "yr", "yrs",
}

# Common pharmaceutical company names that show up in patient reviews
# (complaints about cost, shortages, formulation changes) but aren't
# drug or condition names, so the known_terms lists above don't catch
# them. Not exhaustive - the major manufacturers most likely to be
# named by a patient, added after QA found "Pfizer" and
# "GlaxoSmithKline" being redacted as if they were people's names.
COMMON_PHARMA_COMPANIES = {
    "pfizer", "glaxosmithkline", "gsk", "merck", "novartis", "astrazeneca",
    "sanofi", "bayer", "abbvie", "amgen", "gilead", "teva", "mylan",
    "actavis", "cipla", "sandoz", "purdue", "roche", "lilly", "biogen",
    "regeneron", "moderna", "johnson",
}


def scrub_names_with_ner(texts: list[str], nlp, known_terms: set[str], casing_stats: dict[str, float]) -> list[str]:
    """
    spaCy NER pass: catches PERSON entities regex can't find.
    Runs as a batch via nlp.pipe for speed on large datasets.

    Before redacting a PERSON entity, we run four checks - if ANY of
    them suggests it's not really a person's name, we skip redacting:

    1. Exact match against known_terms (built from the dataset's own
       Drug/Condition columns + curated eponym list) - catches drug
       names, condition names, and medical eponyms.
    2. Fuzzy match against known_terms - catches misspelled drug/
       condition names that don't exact-match (e.g. "Bacrtim").
    3. Casing-frequency check against the corpus itself - catches
       ordinary words ("Began", "Felt", "God") that only look like
       names because they landed at the start of a sentence.
    4. A small curated list of common abbreviations/relations ("Dr",
       "Mom", "Mg") that spaCy's small model regularly mistags.
    """
    redacted = []
    for doc in tqdm(nlp.pipe(texts, batch_size=200), total=len(texts), desc="NER scrubbing"):
        new_text = doc.text
        # Replace longest spans first so offsets don't shift under us
        person_spans = sorted(
            (ent for ent in doc.ents if ent.label_ == "PERSON"),
            key=lambda e: e.start_char,
            reverse=True,
        )
        for ent in person_spans:
            ent_lower = ent.text.lower().strip()
            ent_words = re.findall(r"[a-z']+", ent_lower)

            if ent_lower in known_terms or any(w in known_terms for w in ent_words):
                continue  # exact match: drug/condition/eponym
            if any(fuzzy_matches_known_term(w, known_terms) for w in ent_words):
                continue  # fuzzy match: likely a misspelled drug/condition name
            if any(w in COMMON_ABBREVIATIONS_AND_RELATIONS for w in ent_words):
                continue  # common abbreviation/relation term, not a name
            if any(w in COMMON_PHARMA_COMPANIES for w in ent_words):
                continue  # pharma company name, not a person
            if len(ent_words) == 1 and is_likely_common_word(ent_words[0], casing_stats):
                continue  # normally a lowercase word elsewhere in this corpus

            new_text = new_text[: ent.start_char] + "[NAME_REDACTED]" + new_text[ent.end_char :]
        redacted.append(new_text)
    return redacted


def flag_small_cells(df: pd.DataFrame, category_col: str, min_count: int) -> pd.DataFrame:
    """
    Adds:
      - category_count: how many rows share this row's category value
      - is_small_cell: True if that count is below the configured threshold
    """
    counts = df[category_col].value_counts()
    df["category_count"] = df[category_col].map(counts)
    df["is_small_cell"] = df["category_count"] < min_count
    return df


def flag_quasi_identifiers(
    df: pd.DataFrame,
    category_col: str,
    age_col: str | None,
    sex_col: str | None,
    rare_category_threshold: int,
) -> pd.DataFrame:
    """
    Flags a row as quasi-identifying if it combines:
      - a rare category (below rare_category_threshold occurrences), AND
      - a non-blank age value, AND
      - a non-blank sex value

    This mirrors the "rare condition + specific age + specific location"
    example in the spec - here we don't have a location field, so age + sex
    stand in as the demographic combination that narrows down who a review
    could belong to.
    """
    is_rare_category = df["category_count"] < rare_category_threshold

    has_age = pd.Series(False, index=df.index)
    has_sex = pd.Series(False, index=df.index)

    if age_col and age_col in df.columns:
        has_age = df[age_col].astype(str).str.strip() != ""
    if sex_col and sex_col in df.columns:
        has_sex = df[sex_col].astype(str).str.strip() != ""

    df["is_quasi_identifying"] = is_rare_category & has_age & has_sex
    return df


def run(config_path: str):
    config = load_config(config_path)
    cols = config["columns"]
    privacy = config["privacy"]

    text_col = cols["text"]
    category_col = cols["category"]
    age_col = cols.get("age")
    sex_col = cols.get("sex")

    raw_path = Path(config["raw_path"])
    processed_path = Path(config["processed_path"])
    processed_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Loading raw data from {raw_path} ...")
    df = pd.read_csv(raw_path)
    print(f"Loaded {len(df):,} rows.")

    # Keep a stable reference back to the original raw file's row position.
    # Without this, once we filter rows and save/reload as CSV, row numbers
    # shift and there's no reliable way to compare a processed row back to
    # its original raw text (needed for the redaction QA script).
    df["original_row_id"] = df.index

    # --- Step 0: drop rows with unusable review text -----------------------
    df[text_col] = df[text_col].astype(str)
    before = len(df)
    df = df[df[text_col].str.strip().str.len() >= config["min_review_length"]]
    print(f"Dropped {before - len(df):,} rows with blank/too-short review text. "
          f"{len(df):,} rows remain.")

    # --- Step 0b: dedupe scraping-duplicate rows ----------------------------
    # Must run before small-cell / quasi-id counting (Step 2/3 below), or
    # those counts over-count how many distinct reviews back a condition.
    # Also speeds up the NER pass below, since it now runs on fewer rows.
    print("Removing scraping-duplicate rows (same review, same drug, different formulation label) ...")
    drug_id_col = cols.get("drug_id")
    df = dedupe_scraping_duplicates(df, text_col, drug_id_col)

    # --- Step 1: direct identifiers -----------------------------------------
    print("Scrubbing structured PII (emails, phones, URLs) ...")
    df[text_col] = df[text_col].apply(scrub_structured_pii)

    print("Loading spaCy NER model ...")
    nlp = spacy.load("en_core_web_sm", disable=["parser", "lemmatizer"])

    drug_col = cols.get("drug")
    known_drug_terms = build_known_drug_terms(df, drug_col)
    print(f"Built known-drug-term list from '{drug_col}' column: "
          f"{len(known_drug_terms):,} terms (used to avoid over-redacting drug names as people's names).")

    known_clinical_terms = build_known_clinical_terms(df, category_col)
    print(f"Built known-clinical-term list from '{category_col}' column + curated eponym list: "
          f"{len(known_clinical_terms):,} terms (used to avoid over-redacting condition names/eponyms as people's names).")

    known_terms = known_drug_terms | known_clinical_terms

    print("Building word-casing frequency stats from the corpus (for the common-word check) ...")
    casing_stats = build_word_casing_stats(df[text_col].tolist())
    print(f"  Computed casing stats for {len(casing_stats):,} distinct words.")

    print("Scrubbing names via NER (this can take a while on large datasets) ...")
    df[text_col] = scrub_names_with_ner(df[text_col].tolist(), nlp, known_terms, casing_stats)

    # --- Step 1b: dedupe again, post-redaction ------------------------------
    # A small number of rows (spam/templated reviews) differ in the RAW text
    # only by a URL, phone number, or name - e.g. two "buy Cialis here <link>"
    # spam posts with different tracking links. The pre-redaction dedup pass
    # above correctly treats those as different text, but once the varying
    # part is redacted to the same placeholder tag, they become identical.
    # Catching this here prevents these from inflating category_count /
    # small-cell counts as if they were distinct reviews.
    print("Re-checking for duplicates that only became identical after redaction ...")
    df = dedupe_scraping_duplicates(df, text_col, drug_id_col)

    # --- Step 2: small-cell exposure -----------------------------------------
    print(f"Flagging small cells (threshold = {privacy['min_cell_count']} reviews per category) ...")
    df = flag_small_cells(df, category_col, privacy["min_cell_count"])
    print(f"  {df['is_small_cell'].sum():,} rows fall in a small-cell category "
          f"({df.loc[df['is_small_cell'], category_col].nunique():,} distinct categories affected).")

    # --- Step 3: quasi-identification through combination --------------------
    print("Flagging quasi-identifying rows (rare category + age + sex) ...")
    df = flag_quasi_identifiers(
        df,
        category_col,
        age_col,
        sex_col,
        privacy["quasi_id_rare_category_threshold"],
    )
    print(f"  {df['is_quasi_identifying'].sum():,} rows flagged as quasi-identifying "
          "- these must be excerpted, not shown in full, if used as evidence.")

    # --- Save -------------------------------------------------------------
    df.to_csv(processed_path, index=False)
    print(f"\nSaved de-identified dataset to {processed_path} ({len(df):,} rows).")
    print("Every later pipeline phase should read from this file, not the raw CSV.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Phase 2: de-identify patient feedback data.")
    parser.add_argument(
        "--config",
        default="config/dataset_config.yaml",
        help="Path to the dataset config YAML file.",
    )
    args = parser.parse_args()
    run(args.config)
