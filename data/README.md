# Original fictional dataset

`training.json` contains 72 original English ticket examples (12 per intent), written for this demo and licensed with the repository under MIT. `evaluation.json` contains 24 different intent examples, six out-of-domain prompts and three deliberately mixed-intent prompts. The evaluation file is never loaded by the classifier. `scripts/create_original_data.py` reproduces both files.

These are hand-authored synthetic examples, not customer records or a representative benchmark. English phrasing, six fixed intents, and short shop-support requests are assumptions. Indian names appear in the separate fictional demo tickets. Gujarati, Hindi, spelling errors, complex conversations, emerging intents and production performance have not been established.

No Bitext corpus, third-party customer data or pretrained language-model weights are included. Expanding this dataset should use lawful, consented or appropriately licensed examples, preserve a separate held-out set, and review licensing before redistribution.
