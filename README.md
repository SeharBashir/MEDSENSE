# MedSense — Patient Feedback Intelligence Platform

Turns unstructured patient drug reviews into decision-useful insights: de-identification, topic discovery, sentiment, and a dashboard.

## Status
- **Phase 1 — Dataset sourcing:** Complete. Using the WebMD Drug Reviews Dataset (~362K patient reviews).
- **Phase 2 — Privacy protection:** Complete. De-identification pipeline (direct identifiers, small-cell suppression, quasi-identification flagging) runs as the first step of the pipeline.
- **Phase 3 — Exploration:** In progress.
- **Phase 4 — Discovery pipeline (embeddings/clustering/sentiment):** Not started.
- **Phase 5 — Insight selection:** Not started.
- **Phase 6 — API, dashboard, deployment:** Not started.

## Project structure
```
medsense/
  config/dataset_config.yaml   # column mapping + privacy thresholds - dataset-agnostic config layer
  src/
    config_loader.py           # loads the config so column names are never hardcoded
    deidentify.py               # Phase 2: de-identification pipeline
    evaluate_redaction.py       # QA tool: builds a manual-review sample to check redaction accuracy
  data/
    raw/                        # NOT committed - place your source CSV here
    processed/                  # NOT committed - pipeline output goes here
```

## Setup
```bash
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

## Usage
1. Place your dataset CSV in `data/raw/` and update `config/dataset_config.yaml` to map its columns.
2. Run the de-identification step:
   ```bash
   python src/deidentify.py
   ```
3. (Optional) QA the redaction quality:
   ```bash
   python src/evaluate_redaction.py --sample_size 150
   ```
   Then manually fill in the `false_negative_found` / `false_positive_found` / `notes` columns in the generated `data/processed/redaction_review_sample.csv`.

## Privacy approach
See `config/dataset_config.yaml` for the exact thresholds used:
- `min_cell_count`: minimum reviews per condition before a subgroup stat can be surfaced.
- `quasi_id_rare_category_threshold`: flags rows combining a rare condition with age+sex present, for excerpt-only use as evidence.

Data is never committed to this repo — raw and processed patient data stay local only (see `.gitignore`).
