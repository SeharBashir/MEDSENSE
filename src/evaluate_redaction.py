"""
evaluate_redaction.py

Builds a manual-review sample to sanity-check the de-identification step
in deidentify.py, instead of just eyeballing a handful of rows.

It samples rows from BOTH the raw and processed files (matched by row
position), and puts original text next to redacted text so a human can
go through and mark:
  - false_negative: a real identifier that was MISSED (dangerous - the
    kind of mistake that matters most for patient privacy)
  - false_positive: something redacted that shouldn't have been (like
    a drug name mistaken for a person's name)

Sampling strategy:
  - Half the sample is drawn from rows that DID get a redaction
    (to check those redactions were correct - false positive check)
  - Half the sample is drawn from rows that did NOT get a redaction
    (to check nothing real was missed - false negative check)
This is deliberately not a pure random sample, because a pure random
sample would be mostly-unredacted rows (since only ~10% of rows had
any redaction) and wouldn't give you much to check on the false-positive
side.

Usage:
    python src/evaluate_redaction.py --sample_size 150
"""

import argparse
from pathlib import Path

import pandas as pd

from config_loader import load_config


def run(config_path: str, sample_size: int, seed: int):
    config = load_config(config_path)
    cols = config["columns"]
    text_col = cols["text"]

    raw_path = Path(config["raw_path"])
    processed_path = Path(config["processed_path"])

    print(f"Loading raw data from {raw_path} ...")
    raw = pd.read_csv(raw_path)
    raw["original_row_id"] = raw.index
    print(f"Loading processed (de-identified) data from {processed_path} ...")
    processed = pd.read_csv(processed_path)

    if "original_row_id" not in processed.columns:
        raise ValueError(
            "processed file has no 'original_row_id' column - re-run "
            "deidentify.py with the latest version of the script first."
        )

    # Match rows back to their original raw text using the stable
    # original_row_id column (NOT the dataframe index, which gets reset
    # every time a CSV is saved/reloaded and would otherwise silently
    # pair up the wrong rows).
    raw_text_by_id = raw.set_index("original_row_id")[text_col]

    processed = processed.copy()
    processed["had_redaction"] = processed[text_col].astype(str).str.contains(
        "REDACTED", na=False
    )

    redacted_rows = processed[processed["had_redaction"]]
    clean_rows = processed[~processed["had_redaction"]]

    half = sample_size // 2
    sample_redacted = redacted_rows.sample(
        min(half, len(redacted_rows)), random_state=seed
    )
    sample_clean = clean_rows.sample(
        min(sample_size - len(sample_redacted), len(clean_rows)), random_state=seed
    )

    sample = pd.concat([sample_redacted, sample_clean]).sample(
        frac=1, random_state=seed
    )  # shuffle so redacted/clean rows aren't grouped together

    original_text = raw_text_by_id.loc[sample["original_row_id"]]

    review_df = pd.DataFrame(
        {
            "original_row_id": sample["original_row_id"].values,
            "had_redaction": sample["had_redaction"].values,
            "original_text": original_text.values,
            "redacted_text": sample[text_col].values,
            # reviewer fills these in by hand:
            "false_negative_found": "",   # yes/no - did a real identifier get missed?
            "false_positive_found": "",   # yes/no - was something wrongly redacted?
            "notes": "",
        }
    )

    out_path = Path("data/processed/redaction_review_sample.csv")
    review_df.to_csv(out_path, index=False)
    print(f"\nSaved {len(review_df)} rows to review at {out_path}")
    print(f"  - {sample['had_redaction'].sum()} rows had a redaction (check for false positives)")
    print(f"  - {(~sample['had_redaction']).sum()} rows had no redaction (check for false negatives)")
    print("\nOpen this file (Excel, or VS Code's CSV viewer) and fill in the last three columns by hand.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build a manual review sample for de-identification QA.")
    parser.add_argument("--config", default="config/dataset_config.yaml")
    parser.add_argument("--sample_size", type=int, default=150)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    run(args.config, args.sample_size, args.seed)
