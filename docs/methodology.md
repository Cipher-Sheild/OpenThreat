# NLP methodology

The implemented pipeline combines learned representations and deterministic rules. SecureBERT-based token classification extracts seven entity types; a marked subject/object pair classifier predicts seven relation labels, including NONE and OTHER. Identifier patterns, reference aliases, type constraints and trigger rules supplement predictions. Trained inference is enabled through `NER_MODEL` and `RE_MODEL`.

Preprocessing preserves sentence evidence, negation and offsets. Training converts labels into BIO tags, maps relationship predicates, creates negative pair examples and forms bounded sequences. General stemming and stop-word removal are not runtime stages.

BGE base English v1.5 produces normalized 768-dimensional vectors. Chunks contribute length-weighted document embeddings. Behavior mapping compares explicit technique matches and semantic anchors. Date expressions and event cues yield temporal assertions with partial dates when appropriate; a missing date is not invented.

The deterministic fact policy uses confidence, entity identity, predicate, polarity and publication chronology to label factual change. Similar wording alone is insufficient for an UPDATED or CONFLICTING claim. A model score is not a verified probability of truth.

The taxonomy includes THREAT_ACTOR, MALWARE, TOOL, VULNERABILITY, TECHNIQUE, ORGANIZATION and OBSERVABLE. Stored relation types include USES, DEPLOYS, EXPLOITS, TARGETS and ATTRIBUTED_TO. Indicator ownership requires a supported relationship; appearing in the same report does not automatically establish ownership.
