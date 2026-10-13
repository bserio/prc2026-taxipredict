# Repository — ordering, checks, and the single-file decision

Execution document for the team. Nothing here requires reopening a model: the three files are
already produced, frozen, and checked. Official deadline: **2026‑10‑14 12:00 CET (10:00 Z)**.

## What the rules require (verified on 2026‑10‑10 on the official pages)

| item | rule |
| --- | --- |
| metric | RMSE over the template rows; **the ranking keeps the team's best submission** |
| actual scope | "The applied ranking will use RMSE for submitted predictions for the movements in **January and July 2026**" — the template covers four months, the score grades two |
| upload | MinIO client only (never the web interface); `<team>_v<N>.parquet`, then a single `<team>_final.parquet` |
| quota | 5 submissions/day, 1 GB maximum per bucket |
| fairness | submissions are monitored against any attempt to "learn from or exploit the ranking" |

Our committed stance (D‑009, D‑036): a **single reading** of the reference file, whose local RMSE is
known in advance, to calibrate the local→ranking factor. No recipe iteration driven by the
displayed scores.

## Step 0 — prepare the names (5 minutes)

The team name is the only missing element. Once known:

```bash
cd prc2026-v1
EQUIPE=<nom-exact-de-l-equipe>          # identique au compte rendu aux organisateurs
cp submission/ATTENTE-nom-equipe_reference-proxy_v1.parquet  submission/${EQUIPE}_v1.parquet
cp submission/ATTENTE-nom-equipe_causal_v1.parquet           submission/${EQUIPE}_prediction_v2.parquet
cp submission/ATTENTE-nom-equipe_reconstitution_v1.parquet   submission/${EQUIPE}_reconstitution_v3.parquet

.venv/bin/python -m src.validate_submission --file submission/${EQUIPE}_v1.parquet
.venv/bin/python -m src.validate_submission --file submission/${EQUIPE}_prediction_v2.parquet
.venv/bin/python -m src.validate_submission --file submission/${EQUIPE}_reconstitution_v3.parquet
shasum -a 256 submission/${EQUIPE}_*.parquet      # a consigner dans DECISIONS.md
```

Each file must validate **without error or warning**: 670 790 rows, template identifiers and order,
conforming types, finite values. The three expected files, with their full fingerprint:

| source file | track | local RMSE Jan.+Jul. | destination after renaming | SHA‑256 |
| --- | --- | ---: | --- | --- |
| `submission/ATTENTE-nom-equipe_reference-proxy_v1.parquet` | training-free reference | 643,6 s | `${EQUIPE}_v1.parquet` | `d0ab0cb87d0fea373b90ff3227c685e8bd0b7aeb8a3919fcd8c06a0dc04cda3e` |
| `submission/ATTENTE-nom-equipe_causal_v1.parquet` | causal prediction | 603,5 s | `${EQUIPE}_prediction_v2.parquet` | `dd0050319e63c00677a4ee05b772fbcee8bde8c862443fe2c8c4ddfeb5eaf3af` |
| `submission/ATTENTE-nom-equipe_reconstitution_v1.parquet` | reconstruction | 519,9 s | `${EQUIPE}_reconstitution_v3.parquet` | `66223d9b23c005f4cd2fd9c1f7769100baa6684186ba39e8be4ca418425f8870` |

Renaming does not change the bytes: the fingerprints must be found identical under the new names.
The three files are **regenerable** — `src.predict` commands (the `hybrid`, `causal`,
`residual` tracks) in README §9; reverified on 2026‑10‑10, all three fingerprints were recovered to
the byte after regeneration. If a fingerprint differs, do not upload: the recipe or the inputs have changed.

## Step 1 — measurement upload: the reference file first

```bash
# alias MinIO : cles generees depuis le compte OpenSky (instructions officielles, section « Using MinIO client »)
mc alias set prc2026 https://<endpoint-minio> <CLE> <SECRET>
mc cp submission/${EQUIPE}_v1.parquet  prc2026/<bucket-equipe>/${EQUIPE}_v1.parquet
```

**What we expect** (D‑036): since the ranking grades only January + July, the useful local
comparison is **643,6 s** (not the 591,7 s of the four months). After applying the factor measured on
the true arrival labels (×1,045 to ×1,067), the expected order of magnitude is **≈ 672 – 687 s**.

- If the official score falls within this range: the local→ranking factor is confirmed, we move to
  step 2 without further measurement.
- If it clearly falls outside it: that is information about the **departure population** that the
  arrivals could not provide. We record the discrepancy in `DECISIONS.md`, recompute the two other
  expected files with the measured factor — and we stop there: no new submission to refine.

## Step 2 — choosing the single `<team>_final.parquet` file

The ranking keeps the best submission, but you want only one final file. The choice is made from
the table below, corrected by the factor (measured in D‑036, possibly confirmed by step 1):

| file | local Jan.+Jul. | expected in ranking | nature of the measurement |
| --- | ---: | ---: | --- |
| reference (proxy + bias) | 643,6 | ≈ 672 – 687 s | transparent, training-free |
| prediction (causal) | 603,5 | ≈ 631 – 644 s | reads no information later than the pushback |
| reconstruction (proxy + correction) | **519,9** | **≈ 543 – 555 s** | reads the takeoff time present in the inputs |

The three figures are RMSE **over January + July**, the ranking's population and rows. The
reconstruction's gap over the prediction (−13,9 %) holds for each of the four months and on the internal
holdout (−18,2 %), so it does not depend on a lucky month; however it relies on information that we
ourselves qualify as later than departure (`FEATURE_ADMISSIBILITY.md`, D‑004). The rules set
no instant and forbid no column — but the absence of a prohibition is not permission, and the
decision is yours. Two sentences ready to quote in the response, depending on the choice:

- *reconstruction chosen*: "The rules set no prediction instant; our solution uses the actually
  realized times provided with the inputs, and we separately document a purely predictive variant (603,5 s over January+July) so that the reader can judge the gap."
- *prediction chosen*: "We deliberately excluded any information later than the pushback; the
  variant that reads the takeoff time actually provided in the inputs would reach ≈ 543 – 555 s, which we document without uploading it."

```bash
cp submission/${EQUIPE}_<choix>.parquet  submission/${EQUIPE}_final.parquet
.venv/bin/python -m src.validate_submission --file submission/${EQUIPE}_final.parquet
mc cp submission/${EQUIPE}_final.parquet prc2026/<bucket-equipe>/${EQUIPE}_final.parquet
```

## Step 3 — record-keeping (mandatory for eligibility)

1. In `DECISIONS.md`, add the upload decision: chosen file, official score recorded at step 1,
   SHA‑256 fingerprint of the final file, date and time.
2. Recall the two eligibility obligations not yet met: **public code under GPLv3** on GitHub
   (a fork of the challenge account — the local repository has **no commit** yet, to be created before publication) and a consistent
   **team name** everywhere (`RULES.md`, Eligibility section).
3. Keep the `reports/` logs and this folder: reproducibility is part of the prize.

## What NOT to do

- Iterating variants based on the displayed scores: this is exactly the practice targeted by the official warning,
  and our tuning is finished anyway: thirty‑two experiments recorded in
  `experiments/REGISTRY.md`, no variant adopted outside the two frozen tracks.
- Uploading a partially filled file "just to see": the ranking script rejects any
  missing or extra row, and it would consume a slot.
- Using the ranking scores as an input feature for a model or a feature-selection choice.
