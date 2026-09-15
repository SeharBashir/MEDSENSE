# Phase 5 — Final Insights

Seven insights, each backed by verified evidence from `insights_verified.json` (real counts, real sentiment, privacy-checked example quotes — no small-cell or quasi-identifying rows used as quotes). All seven passed the Phase 2/Phase 4 privacy checks.

---

## 1. Statin-class drugs: the complaint is muscle pain, not efficacy

**Insight:** Reviews of statin-class cholesterol medications (Lipitor, Crestor, simvastatin, Zocor — 1,780 reviews, avg sentiment -0.49) are strongly negative specifically around muscle and bone pain, not cholesterol-lowering failure, and this holds consistently across every major brand in the class — suggesting a class-wide tolerability/monitoring gap rather than a single-drug issue.

**Evidence:** n=1,780 across Lipitor (359), Crestor (327), simvastatin (241), Zocor (226), Livalo (63); concentrated in High Cholesterol (869) and combined cholesterol/triglyceride conditions (287).
> *"I experience[d] SEVERE muscle and bone pain. It was so severe that I had multiple scans of my bones for breakage... 100x's worse than childbirth."*

**Actionable:** Muscle-pain risk communication and monitoring protocols may be under-emphasized relative to efficacy messaging, across the drug class as a whole, not one brand.

---

## 2. ADHD medication feedback is substantially caregiver-reported, not self-reported

**Insight:** 2,011 reviews under ADHD (Vyvanse, Concerta, Focalin, Intuniv) are dominated by caregiver language ("my son," "her personality") describing school behavior and family relationships rather than first-person patient experience — meaning "patient satisfaction" for this condition is substantially proxy-reported by parents and should not be interpreted or dashboarded the same way as self-reported conditions.

**Evidence:** n=2,011, avg sentiment -0.22; top drugs Vyvanse (329), Concerta (172), Focalin XR (125), Intuniv (125).
> *"My son was taking concerta 36mg... After 3 weeks, his hair started falling out in 2 spots and he started hallucinating and crying about it... We had to put him back on meds after being off for 2 weeks."*

**Actionable:** Flag ADHD topic data as caregiver-reported in the dashboard; treat differently from conditions where the patient is self-describing their own experience.

---

## 3. Cost/insurance complaints are hidden by the aggregate sentiment metric

**Insight:** 562 reviews explicitly about cost/insurance show a near-neutral aggregate sentiment (-0.11) despite containing sharp, specific complaints — because "Satisfaction" measures drug efficacy, not affordability. A patient who loves the drug but is furious about price averages out to neutral, masking a real access signal.

**Evidence:** n=562, avg sentiment -0.11, spread across many unrelated drugs (Plavix, Cymbalta, Provigil, Lyrica) — confirming this is a cross-cutting cost theme, not a single-product issue.
> *"This drug has helped me immensely. However, the cost has increased by more than 500%!!! ...Cannot something be done to reduce the cost of this effective medication?"*

**Actionable:** Track cost/access complaints as a separate metric from efficacy sentiment — this is a methodology finding about the pipeline itself, not just a drug-specific one, and should inform how Phase 6's dashboard presents "sentiment" for any cost-adjacent topic.

---

## 4. Osteoporosis bisphosphonates: severe bone pain from bone-strengthening drugs

**Insight:** 360 reviews of osteoporosis bisphosphonates (Boniva, Fosamax, Actonel) show strongly negative sentiment (-0.66) centered on severe, unexpected bone/joint pain — an ironic class-wide effect given these drugs exist to strengthen bone.

**Evidence:** n=360, avg sentiment -0.66; 66% under "Decreased Bone Mass Following Menopause"; consistent across Boniva (118), Fosamax (100), Actonel (61).
> *"Last July, I began experiencing excruciating pain in my back, hips, knees... I was told to stop this med. It has been 6 months since my last pill and I still hurt."*

**Actionable:** Worth flagging to a clinical-affairs team as a class-wide (not single-brand) tolerability pattern warranting monitoring guidance.

---

## 5. Depression medications: sexual side effects as a distinct, separable complaint

**Insight:** 420 reviews under Depression medications (Lexapro, Zoloft, Celexa, Effexor XR) show a complaint cluster specifically about sexual side effects, distinct from complaints about mood-related efficacy — patients report the drug working for mood while citing sexual dysfunction as the reason for dissatisfaction.

**Evidence:** n=420, avg sentiment -0.18; top drugs Lexapro (32), Zoloft (30), citalopram (27), Celexa (27).
> *"Kills sexual functioning... Doctors don't inform you of the possible consequences and the FDA has underestimated the sexual dysfunction effects."*

**Actionable:** The explicit mention of patients researching this independently (referencing PSSD, "look it up online") suggests an informed-consent/counseling gap worth addressing proactively rather than reactively.

---

## 6. Sleep medications: hallucinations are a distinct, more serious symptom than grogginess

**Insight:** Within the much larger volume of general sleep-medication feedback (thousands of reviews about effectiveness/grogginess), a distinct 127-review cluster specifically describes hallucinations and confusion — a categorically different and more serious symptom, currently buried within broader "sleep aid" feedback.

**Evidence:** n=127, avg sentiment -0.74 (the most negative of all seven insights); spans Ambien, Seroquel, and others — not a single-drug artifact.
> *"I was seeing things melt down my wall and seeing people in my room. My husband literally had to lay on top of me and hold me to get me to sleep."*

**Actionable:** Worth surfacing as its own safety-relevant category rather than folding into generic "drowsiness" side-effect reporting.

---

## 7. Serious adverse-event narrative cluster — route to clinical review, do not display as a standard topic

**Insight:** A 112-review cluster (avg sentiment -0.88, the most negative in the dataset) contains explicit language describing death, hospitalization, and organ failure attributed to medication, spanning several unrelated drugs (amiodarone, oxycodone, Seroquel) rather than one product.

**Evidence:** n=112, avg sentiment -0.88; no single drug accounts for more than 6 reviews, confirming this is a cross-drug pattern of severe-outcome language, not one product's signal.

**Handling:** This is presented in aggregate only — count and sentiment — with **no verbatim quotes**, given the severity and personal nature of the content (deaths of family members). This should be routed to your team's clinical/pharmacovigilance review process for a judgment call on whether and how it belongs in a patient-facing dashboard, rather than displayed as a standard topic card.

---

## Not pursued

- **ACE-inhibitor cough** (lisinopril and related, 900+ reviews): strong, well-supported pattern, but fails the non-obvious bar — persistent dry cough from ACE-inhibitors is textbook clinical knowledge, not a new finding.
- **Birth control → hair loss**: topics looked promising (~773 reviews) but the `Condition` label didn't match the apparent content, and this was never run through the privacy-verification script. Left out rather than surfaced unverified.

---

## Privacy compliance summary

All seven insights: privacy check passed (no small topics used standalone, all example quotes drawn only from rows that are not `is_small_cell` or `is_quasi_identifying`). Small-cell and quasi-identifying counts per insight are logged in `insights_verified.json` for audit.
