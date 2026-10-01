# Evaluation notes

The app defaults to a 72-example original synthetic corpus. Its held-out file has 24 separately authored, labelled intent messages, six out-of-domain messages and three mixed-intent messages. No evaluation text is read during fitting. Thresholds are fixed demo policy, not production-calibrated probabilities.

Default results: 24/24 top-intent matches; macro F1 1.000; 15/24 clear suggestions (62.5% coverage), all 15 correct; nine labelled messages held. All six out-of-domain and three mixed-intent examples were held. This small authored result is useful for regression checks and does not estimate real-shop performance.

The opt-in Bitext experiment downloaded publisher revision `430d1a8`. After bounded selection, canonical deduplication and near-duplicate grouping, 237 public examples supplemented the original 72 training examples. The separate evaluation had 63 public messages plus the original 24 labelled messages. Original out-of-domain and mixed checks remained separate.

The supplemental model matched 83/87 labelled intents (95.4%), macro F1 0.939. It suggested 74/87 (85.1% coverage); those 74 happened to be correct. Six out-of-domain prompts were held, but only two of three mixed requests were held. More data increased coverage and introduced a missed mixed-intent review gate on this tiny check set. This is why accuracy, coverage and abstention must be reported together.

The importer excludes the source's general `complaint` intent because mapping all complaints to product faults would invent a label. Product examples therefore remain original-only. Both corpora are synthetic. Character n-gram groups remove some close phrasings, not all shared templates or semantic leakage. These results establish neither calibrated confidence nor safe unattended routing.

Row-level public text and modified datasets stay in ignored `instance/bitext/`; committed public evidence is aggregate-only. Dataset attribution and licensing are separate from the repository's MIT license. Future evaluation should use consented representative requests, multilingual and typo cases, unseen policies, and human-reviewed uncertain examples, with a frozen holdout and an independent calibration split.
