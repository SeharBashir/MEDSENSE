# Phase 2 — Step-by-Step in VS Code

This assumes you're on a normal laptop (Mac/Windows/Linux) with VS Code and Python 3.10+ already installed. Follow in order.

---

## Step 1 — Get the project folder onto your machine

1. Download the `medsense` folder I've prepared (it's attached below this message) and unzip it somewhere easy to find, e.g. your Desktop.
2. Open **VS Code**.
3. Go to **File → Open Folder...** and select the `medsense` folder.
4. You should now see this in the Explorer panel on the left:
   ```
   medsense/
     config/
       dataset_config.yaml
     data/
       raw/
       processed/
     src/
       config_loader.py
       deidentify.py
     requirements.txt
   ```

## Step 2 — Put your dataset in the right place

1. In the VS Code Explorer, right-click the `data/raw` folder → **Reveal in Finder/Explorer**.
2. Copy your `webmd.csv` file into that `data/raw` folder.
3. Back in VS Code, confirm you now see `data/raw/webmd.csv` in the file tree.

## Step 3 — Open the integrated terminal

1. Go to **Terminal → New Terminal** (or press `` Ctrl+` `` / `` Cmd+` ``).
2. This opens a terminal already pointed at your `medsense` folder. Confirm with:
   ```bash
   pwd
   ```
   It should print a path ending in `medsense`.

## Step 4 — Create a virtual environment

Do this so the packages you install don't clash with anything else on your machine.

**Mac/Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

**Windows (PowerShell):**
```powershell
python -m venv venv
venv\Scripts\Activate.ps1
```

After running this, your terminal prompt should now start with `(venv)`. If it doesn't, stop and re-run the activate command — don't continue until you see `(venv)`.

## Step 5 — Install dependencies

```bash
pip install -r requirements.txt
```

This installs `pandas`, `pyyaml`, `spacy`, and `tqdm`. Wait for it to finish (30 seconds to a couple minutes depending on your connection).

## Step 6 — Download the spaCy language model

This is a separate download from the `pip install` above — spaCy needs an actual language model to detect names.

```bash
python -m spacy download en_core_web_sm
```

You should see `Download and installation successful` at the end.

## Step 7 — Open and skim the config file

1. In VS Code's Explorer, click `config/dataset_config.yaml` to open it.
2. Confirm the column names match your CSV exactly (open `data/raw/webmd.csv` briefly too, or check the header row). For the WebMD dataset, these are already set correctly:
   - `text: "Reviews"`
   - `category: "Condition"`
   - `rating: "Satisfaction"`
   - `date: "Date"`
   - `age: "Age"`
   - `sex: "Sex"`
3. Note the privacy settings at the bottom:
   - `min_cell_count: 5` — subgroups with fewer than 5 reviews get flagged as too small to surface later.
   - `quasi_id_rare_category_threshold: 10` — a condition with fewer than 10 reviews, combined with age + sex both present, gets flagged as a quasi-identification risk.
   - These are reasonable starting values. You should be ready to explain *why* 5 and 10 in your writeup — e.g., "small enough to catch genuinely rare conditions, large enough that a handful of reviews can't be traced back to one plausible person."

You don't need to edit this file for the WebMD dataset — it's already configured. You'd only touch it if you later pointed the pipeline at a different dataset.

## Step 8 — Open the pipeline script (just to see what it does)

1. Click `src/deidentify.py` in the Explorer to open it and skim the comments at the top — they explain what each of the three privacy steps does.
2. No edits needed here either. This is just so you understand what you're about to run.

## Step 9 — Run the de-identification pipeline

Back in the terminal (still inside `medsense`, with `(venv)` showing):

```bash
python src/deidentify.py
```

**What you'll see, in order:**
- Row count loaded
- How many blank/too-short reviews were dropped
- A regex PII pass (fast)
- The spaCy model loading
- A progress bar for the NER name-scrubbing pass — **this is the slow part**. On the full ~362K row WebMD file, expect roughly 30–35 minutes based on the speed I tested at. Let it run; don't close the terminal.
- Small-cell flagging counts
- Quasi-identification flagging counts
- A final line confirming the output was saved to `data/processed/deidentified.csv`

## Step 10 — Check the output

1. In the Explorer, open `data/processed/deidentified.csv` (VS Code will preview it as raw text — for a nicer view, use an extension like "Edit csv" or "Rainbow CSV," or just open it in Excel/Numbers).
2. Confirm you see three new columns at the end: `category_count`, `is_small_cell`, `is_quasi_identifying`.
3. Search the file (Ctrl+F / Cmd+F in VS Code) for `REDACTED` to see a few examples of scrubbed text.

## Step 11 — Spot-check the results (important, don't skip)

Open a new terminal tab (or reuse the same one) and run a couple of quick checks so you have real numbers for your writeup, not just "it ran":

```bash
python3 -c "
import pandas as pd
df = pd.read_csv('data/processed/deidentified.csv')
print('Total rows:', len(df))
print('Rows with a redaction:', df['Reviews'].str.contains('REDACTED', na=False).sum())
print('Rows flagged small-cell:', df['is_small_cell'].sum())
print('Rows flagged quasi-identifying:', df['is_quasi_identifying'].sum())
"
```

Also manually read 5–10 of the redacted rows (search `REDACTED` in the CSV) and check: did it catch real names? Did it over-redact anything harmless (like a drug name)? Write down 1–2 examples of each for your check-in — this is exactly the kind of "decision you made that you'd like a second opinion on" your lead asked for.

## Step 12 — Deactivate the environment when done (optional, end of session)

```bash
deactivate
```

Next time you come back to work on this, you only need to run `source venv/bin/activate` (Mac/Linux) or `venv\Scripts\Activate.ps1` (Windows) again — no need to reinstall anything.

---

## What's next after this

Every later phase (exploration, embeddings, clustering) should read from `data/processed/deidentified.csv` — never from `data/raw/webmd.csv` again. That's the whole point of doing this first.
