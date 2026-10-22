# OpenThreat NLP — NLP & Intelligence Engine (NLP service sections, DRAFT)

> **Draft for NLP service to rewrite in their own words.** Facts, numbers, tables and figures are final
> once generated from the evaluation outputs; the wording is not. Figures are in
> `services/nlp/evaluation/results/` and the Colab results folder.

## 1. Role of the NLP engine

The NLP engine turns an unstructured threat report into structured, traceable intelligence and
decides whether each extracted fact is new. It is a separate FastAPI service (`services/nlp`) that
talks to the platform only through a versioned JSON contract (`docs/contracts/`, v1.1). Every fact
it returns carries its evidence sentence, character offsets (and page number for PDFs) and a
confidence score.

Pipeline: preprocessing → named entity recognition (NER) → entity canonicalisation → relation
extraction (RE) → behaviour mapping to MITRE ATT&CK → temporal extraction → document embedding.
Novelty is a separate step (`/classify_novelty`): the platform retrieves candidate facts from
PostgreSQL/Qdrant and the engine applies the labelling policy to them.

## 2. Data

**NER: CyberNER.** The harmonised CyberNER corpus combines four public CTI NER datasets (CyNER,
DNRTI, APTNER, Attacker) under one STIX-2.1 label set. We map its 21 STIX labels onto our 7 types
(Threat-Actor, Intrusion-Set, Campaign → THREAT_ACTOR; Malware → MALWARE; Tool, Software → TOOL;
Vulnerability; Attack-Pattern → TECHNIQUE; Identity → ORGANIZATION; Indicator, File, Domain-Name,
IPv4-Addr, URL, Email-Addr → OBSERVABLE). Location, Infrastructure, Course-of-Action and similar
labels are outside the v1 taxonomy and treated as O. Split: 80/10/10 per source dataset with a
fixed seed (42), so every source appears in train, dev and test. Long "sentences" (tables, lists)
are cut into 100-word windows without splitting an entity. Size: {{NER_DATA}}.

**RE: AZERG.** Public CTI relation datasets are scarce (flagged in Phase 0). AZERG (QCRI,
Apache-2.0) annotates 141 reports with STIX entities and relationships and is distributed as
instruction/answer pairs. We convert its "relationship label" items into classification examples
and its "not related" answers into negative examples, and map STIX relations to ours (uses → USES;
drops, downloads, delivers → DEPLOYS; exploits → EXPLOITS; targets, compromises → TARGETS;
attributed-to, authored-by → ATTRIBUTED_TO; everything else → OTHER). The two entities are marked
in the passage with [E1]…[/E1] (subject) and [E2]…[/E2] (object). Label counts: {{RE_DATA}}.
DEPLOYS has no dedicated public annotation; it comes from the mapped "drops/downloads/delivers" labels.

**ATT&CK mapping: TRAM and CTI-HAL.** MITRE CTID's TRAM data (5,089 sentences, 50 techniques,
Apache-2.0) provides labelled example sentences. 30 TRAM documents are held out for testing
(document-level split, so no sentence of a test report is used as an anchor). CTI-HAL (974
annotated passages from 81 real reports, 175 techniques) is used as an out-of-domain test set.

**Novelty benchmark.** No public dataset exists for fact-level novelty, so we built one: 142
(older sentence, newer sentence) pairs, each labelled under the agreed policy, covering 12
categories (same names, aliases, paraphrases, typos, new subject, new object, look-alike names,
attribution updates, "no longer", attribution conflicts, denials, hedged statements). Several
categories are deliberately hard for our system. **[TODO before submission: both members check
every label in `evaluation/data/novelty_benchmark_review.csv`, then replace this note with
"Labels were reviewed independently by both members."]**

## 3. Methods

**Preprocessing.** The analysed text is never rewritten, so IOCs (CVE IDs, IPs, hashes, defanged
domains such as `evil[.]com`) are preserved and all offsets point into the original text.
Sentence splitting handles abbreviations ("e.g.", "U.S.") and does not split inside IOCs.

**NER (hybrid).** A RoBERTa-based model pre-trained on cybersecurity text (SecureBERT) is
fine-tuned for token classification (BIO, 15 labels; 4 epochs, learning rate 3e-5, batch 16,
warm-up 10%, seed 42, best epoch chosen on dev micro-F1). In deployment, its predictions are
combined with high-precision rules: regular expressions for IOCs always win on overlap, and
curated name lists from MITRE ATT&CK (176 groups, 825 malware/tools with aliases) map mentions to
canonical names (e.g. "Fancy Bear" → APT28). A light coreference rule links "the group" to the
last named actor.

**Relation extraction (hybrid).** A SecureBERT sequence classifier over marked entity pairs
(7 classes, class-weighted cross-entropy to counter imbalance, 4 epochs, learning rate 2e-5). In
deployment every plausible pair in a sentence (type-compatible, ≤160 characters apart) is
classified in both directions. Type constraints (e.g. EXPLOITS needs a VULNERABILITY object) filter
the output, and facts also found by the trigger-based rules get a higher confidence. A negation
detector marks facts such as "no longer uses" or "is not attributed to".

**Behaviours → ATT&CK.** Explicit technique IDs and exact technique names are mapped directly.
Other behaviour sentences are embedded with {{EMBEDDING_MODEL}} and compared with two kinds of
anchors: the official technique descriptions and labelled TRAM example sentences. The technique
with the most similar anchor is returned if the similarity clears a threshold calibrated on
held-out data.

**Temporal extraction.** Absolute dates (ISO, "15 March 2024", "March 2024", "Q3 2023", years)
and relative dates resolved against the publication date ("last month", "three months ago") are
linked to the nearest suitable entity and typed by the closest cue word: FIRST_SEEN, DISCLOSED,
PATCHED, ACTIVE, RETIRED, otherwise OBSERVED.

**Entity resolution.** Cascade from cheap and reliable to expensive: exact normalised name →
stored alias → ATT&CK alias knowledge → string similarity (never across different numbers, so
APT28 ≠ APT29 and CVE-…-1 ≠ CVE-…-2) → embedding similarity, always filtered by entity type.

**Novelty classification.** Rules applied after resolution: NEW (nothing on record, or another
object for a multi-valued relation), KNOWN (same subject, relation and object), UPDATED (the new
fact supersedes the old one: a newer or explicitly revised attribution, or "no longer uses"; the
old fact becomes HISTORICAL), CONFLICTING (contradiction without clear supersession; both stay
ACTIVE and are flagged), UNCERTAIN (fact confidence < 0.5 or entity match < 0.9). Similarity alone
never decides novelty.

## 4. Results

### 4.1 NER (CyberNER test set, entity-level exact match)

{{NER_TABLE}}

Fine-tuned model per source dataset:

{{NER_PER_SOURCE}}

Figures: `confusion_ner_rules.png`, `confusion_ner.png` (model), `confusion_ner_hybrid.png`.

*Reading the table.* Fine-tuning raises micro-F1 from 0.37 (rules) to 0.67, mostly through recall
(0.26 → 0.68): the rules are precise but only know names on their lists. The hybrid scores below the
model alone *on this benchmark* (0.62) because rule spans win overlaps and follow ATT&CK naming and
span boundaries rather than CyberNER's annotation conventions (e.g. TECHNIQUE: rules tag exact
technique names, CyberNER annotates descriptive phrases). This is a deliberate trade-off: the
service needs exact IOCs and canonical names, which novelty detection depends on (§4.5: hybrid
0.908 vs rules 0.852 accuracy). Note: model-only scores come from the training run (100-word
windows, 5,219 gold entities); rules and hybrid from the service on whole sentences (5,233).

### 4.2 Relation extraction (AZERG test set)

{{RE_TABLE}}

Figure: `confusion_re.png`.

*Reading the table.* The three well-represented relations reach F1 0.67–0.89 and the model
separates related from unrelated pairs well (NONE F1 0.88). DEPLOYS (34 training examples) and
EXPLOITS (2) are too rare in AZERG to learn, which drags macro-F1 down to 0.49; in deployment these
two relations come from the trigger-based rules. A first training run without negative examples
(`experiments/re_SecureBERT_v1_no_negatives.json`) could not say "no relation" at all; generating
negatives from AZERG's entity lists fixed this.

### 4.3 ATT&CK mapping

{{ATTACK_TABLE}}

Recommended operating point: {{ATTACK_THRESHOLD}}. Figure: `attack_threshold_curve.png`.
The service uses this threshold (`ATTACK_MIN_SIMILARITY=0.64`).

*Reading the table.* Labelled example sentences matter far more than official descriptions
(TRAM top-1 0.22 → 0.72). On CTI-HAL, whose 175 techniques are mostly not among TRAM's 50, top-1
drops to 0.32 (0.61 top-3 at parent-technique level): the method transfers to unseen reports but is
limited by which techniques have labelled examples.

### 4.4 Temporal extraction

{{TEMPORAL}}

### 4.5 Novelty classification — main result (hybrid pipeline)

{{NOVELTY_HYBRID}}

{{KNOWNNEW_HYBRID}}

Baselines compare the two sentences directly (keyword Jaccard, fuzzy string ratio, embedding
cosine) and output KNOWN above a threshold, else NEW. Thresholds were tuned on the benchmark itself,
which favours the baselines. Figure: `hybrid/confusion_novelty.png`.

*Reading the table.* The full pipeline reaches 0.908 accuracy and macro-F1 0.818, against 0.394 /
0.196 for the best baseline. Baselines can only output KNOWN or NEW, so the fairer comparison is the
KNOWN/NEW subset, where the pipeline still leads by about 29 points. CONFLICTING (F1 1.00), UPDATED
(0.96) and NEW (0.96) are handled well; UNCERTAIN is the weak class (F1 0.29) because hedged
statements are extracted as facts (see §5).

Same benchmark with the rule-based extractors (Phase 2):

{{NOVELTY_RULES}}

### 4.6 Ablation study (hybrid pipeline, one component removed at a time)

{{ABLATION_HYBRID}}

Every component contributes. Temporal reasoning matters most (−0.27 macro-F1): without
publication dates and "no longer" cues, updates cannot be told apart from conflicts. Relation
semantics (−0.20) separate single-valued attributions from multi-valued facts, negation (−0.14)
detects denials, and entity resolution (−0.07) merges aliases; its drop is smaller because
canonical names are already applied at extraction time.

Rule-based variant:

{{ABLATION_RULES}}

### 4.7 Error analysis (hybrid pipeline, per category)

{{PERCAT_HYBRID}}

Individual errors: `hybrid/novelty_errors.json`.

## 5. Limitations

- **Hedged language.** Statements such as "possibly associated with" or "it is unclear whether"
  are extracted as facts; the system has no hedge/speculation detector, so these become NEW or
  KNOWN instead of UNCERTAIN.
- **Benchmark size and construction.** The novelty benchmark (142 pairs) was written by the
  project team, with labels that follow our own policy; it shows relative behaviour of components
  and baselines but is not an independent benchmark. The temporal set (30 sentences) is a sanity check.
- **Label mapping.** CyberNER and AZERG labels were mapped onto our 7/5-type taxonomy;
  annotation conventions differ between sources (e.g. what counts as a TOOL), which caps
  exact-match scores, especially for the rule-based baseline.
- **DEPLOYS** has no native annotations; it is learnt from mapped STIX labels.
- **Single-valued relations** are limited to ATTRIBUTED_TO in v1; temporal ranges ("between April
  and December 2022", "second half of 2023") are only partly handled.
- **Alias coverage** depends on ATT&CK and a hand-made list; vendor names not in them (e.g.
  TA542 vs Mummy Spider) are not resolved.
- **Compute.** Training on a single free Colab T4; no hyper-parameter search was run.

## 6. Reproducibility

Every training run writes a log (dataset SHA-256, base model, hyper-parameters, seed, metrics,
library versions) to `experiments/`. Splits are deterministic (seed 42; `split_ner.json`,
`tram_split.json`). Models: `NER_MODEL` / `RE_MODEL` on Hugging Face. All evaluations re-run with
one command (`evaluation/run_all.py`).
