# Phase 4 — Research Notes: Embeddings, Clustering, Sentiment

## 1. Embeddings: sentence-transformers, not TF-IDF

**Tested first (fully offline, no external download needed):** TF-IDF + SVD dimensionality reduction, clustered with HDBSCAN on a 2,000-review sample from a single condition (Depression).

**Result:** found one genuinely coherent small cluster (12 reviews, all specifically about generic-vs-brand-name drug switching complaints) but classified 66.8% of reviews as noise, and lumped much of the rest into one large, vague catch-all cluster.

**Why this happens:** TF-IDF only measures word overlap. Two reviews saying the same thing in different words ("I stopped taking it" vs. "I discontinued the medication") look unrelated to it. That's a fundamental ceiling, not a tuning problem.

**Decision:** use `sentence-transformers` (`all-MiniLM-L6-v2`) to generate semantic embeddings instead — these capture meaning, not just word overlap, which is exactly what short, paraphrase-heavy consumer review text needs.

**Caveat:** this model downloads from Hugging Face on first run (~90MB). This needs to be verified on a machine with normal internet access — some restricted/sandboxed environments block huggingface.co.

## 2. Clustering: HDBSCAN, not k-means

The project spec explicitly flags that "not every algorithm handles outliers gracefully." k-means forces every review into some cluster, including ones that don't really belong anywhere — this would silently corrupt topic coherence by diluting real topics with unrelated reviews.

HDBSCAN is density-based: it finds naturally dense regions of similar reviews and explicitly labels sparse/atypical ones as noise (`-1`) rather than forcing them somewhere. It also doesn't require guessing the number of topics upfront, which fits a discovery task where the topics aren't known in advance.

Confirmed via testing: even with TF-IDF's weaker signal, HDBSCAN correctly separated a real, specific topic (generic-vs-brand complaints) rather than blending it into a generic bucket.

## 3. Sentiment: patient rating first, text sentiment as fallback

**Investigated, not assumed**, per the spec's explicit instruction.

**Step 1 — tested VADER** (a standard general-purpose sentiment tool) against domain phrases identified in Phase 3:
- "I finally slept through the night" → scored 0.00 (neutral) — should be strongly positive in this domain.
- "The pain is completely gone, I feel like a new person" → scored -0.20 (negative) — should be strongly positive.

**Step 2 — measured real correlation** between VADER sentiment and the dataset's actual `Satisfaction` ratings (patients' own stated satisfaction) on a 5,000-review sample: **0.373** — weak-to-moderate, leaving a lot of signal on the table.

**Step 3 — tried fixing it** by augmenting VADER's lexicon with the specific domain phrases found in Phase 3 ("slept through the night," "pain gone," etc.). Result: **no measurable improvement** (0.373 → 0.373), because these specific phrases are too rare (~0.2% of reviews) to move an aggregate correlation number.

**Step 4 — diagnosed the real cause** by finding the biggest mismatches directly:
- 414 reviews rated 5/5 satisfaction but scored strongly negative by VADER — pattern: patients describe how bad their *pre-treatment* symptoms were ("daily asthma attacks," "Triglycerides over 1000") before explaining the drug fixed it. VADER reads the negative words describing the problem, not the positive outcome.
- 209 reviews rated 1/5 but scored strongly positive by VADER — pattern: side effects listed in words that sound positive out of context ("LOTS OF ENERGY, INSOMNIA").

**Conclusion:** the mismatch is structural (before/after narrative arcs, side-effects listed inside positive reviews), not a vocabulary gap a phrase list can patch.

**Decision:** since patients already told us how they felt via a real numeric rating, use that (`Satisfaction`, rescaled to -1..+1) as the primary sentiment signal whenever the dataset's config provides a rating column. VADER text sentiment is kept only as a fallback for a different dataset that lacks a rating field, so the pipeline still produces something reasonable — keeping it dataset-agnostic per the project's ground rules.
