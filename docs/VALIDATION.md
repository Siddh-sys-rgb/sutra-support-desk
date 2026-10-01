# Local validation

Validated on 1 October 2026 with Python 3.12.14 on macOS. The offline suite passes **77 tests** with **99% statement coverage** across `triage/`. Dependency consistency and JavaScript syntax checks pass. The separate original/public model evaluations and their limitations are in [EVALUATION.md](EVALUATION.md).

## Running-browser checks

The actual Flask server was exercised through the in-app browser:

- Created Ananya Shah's fictional delayed-parcel ticket and inspected its learned delivery suggestion and related conversation.
- Confirmed routing, assigned Kavya Joshi, started work, then resolved the ticket. The original prediction remained visible and accepted changes appeared in its history.
- Inspected the ambiguous bottle/refund example and its human-review gate, class scores and text features.
- Verified the inbox counts reflected accepted changes and displayed both resolved and pending-review cases.
- Opened all three portfolio apps in one browser. Their distinct session cookies allowed mutations in every app and a subsequent Sutra save without a CSRF conflict.
- Inspected the 1280-pixel desktop inbox and the 390-pixel mobile inbox/review. Document width matched viewport width; there was no horizontal page overflow. Queue navigation intentionally scrolls inside its own row.
- Final desktop browser console contained no warning or error entries.

The screenshots are original JPEG captures of the running app, with fictional data: `overview.jpg`, `ticket-review.jpg` and `mobile.jpg`. Counts and timestamps reflect that local demo session; they need not match a fresh database exactly.

Browser inspection is separate from the API/model/concurrency tests. It is not an exhaustive browser automation suite or a production accuracy/security assessment. Prepared remote CI has not run, and no GitHub account or remote operation was used.
