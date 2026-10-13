# Official rules — PRC Data Challenge 2026 (final)

Pages consulted on 2026‑10‑09, **re‑read on 2026‑10‑10** (the re‑reading changed our understanding of
the ranking scope — see below), official pages:

| source | content retained |
| --- | --- |
| `https://prc-data-challenge-2026.netlify.app/index.html` | objective, scope, calendar |
| `https://prc-data-challenge-2026.netlify.app/ranking.html` | metric, template, submission, limits |
| `https://prc-data-challenge-2026.netlify.app/eligibility.html` (via `docs/01_eligibility.md`) | prize eligibility |
| `https://ansperformance.eu/study/data-challenge/dc2026/data.html` | data, columns, files |

## Target and population

> « The submitting dataset is the template to be filled with the predicted taxi‑out times,
> i.e. `TAXITIME_SEC_mvt` = `MVT_TIME_UTC_mvt` - `BLOCK_TIME_UTC_mvt` (for the departure). »
> — Data page, *The Submitting Dataset* section

- Target: `TAXITIME_SEC_mvt` of **departures** (`PHASE_mvt = "DEP"`); the template contains only
  departures (verified: 670,790 rows = exactly the departures of `final_ranking.parquet`).
- 10 airports: EDDF, EDDM, EGLL, EHAM, LEBL, LEMD, LFPG, LIRF, LTFM, LSZH.
- Military, head-of-State and sensitive movements are removed; no synthetic data.

## Actual scope of the ranking (clarification obtained in the 2026‑10‑10 re‑reading)

> « The applied ranking will use Root Mean Square Error (RMSE) for submitted predictions for the
> movements in **January and July 2026**. » — home page, *Ranking* section

- The **template** to fill covers the four months (`final_submitting.parquet`, 670,790 departures:
  January, February, June, July 2026) and the ranking script rejects any missing or extra row: so we do
  fill all four months.
- But the **ranking** is computed over **January + July 2026**. Our methodological decisions must
  therefore be judged primarily on those two months; the four months remain our stability control.
- The evaluation files ship, in addition to the departures to predict, **arrivals with their actual
  taxi time**: `ranking.parquet` (January + July 2026, 8 airports from the previous phase) and
  `final_ranking.parquet` (the four months, on our ten airports, **670,407 labelled arrivals**).
  This is 2026 ground truth provided by the organiser: we use it as **observable context**
  (traffic actually landed before the anchor) and as a **drift control**, never as a tuned target,
  since our scored population is that of departures.

## Metric and ranking

> « Teams will be ranked based on the best Root Mean Square Error (RMSE) achieved across
> their submissions. » — Ranking page

- RMSE over the template rows; any missing or extra row, or any unmatched `MVT_ID_mvt`, makes the
  ranking script fail.
- The unweighted mean of the monthly RMSEs is **not** the overall RMSE: our headline metric is
  therefore the RMSE computed over all evaluated rows.

## Submission

- Ranking: « Teams will be ranked based on the **best** Root Mean Square Error (RMSE) achieved
  across their submissions. » — a team's best submission counts; the others do not penalise it.
- Running name: `<team-name>_v<incremental integer>.parquet`; single final file: `<team-name>_final.parquet`.
- 5 submissions/day, 1 GB maximum per bucket; submission via the MinIO client (never via the web).
- Official warning: submissions are monitored for any attempt to "learn from or exploit the ranking
  process", which is considered unfair.
  → no exploratory submission to extract information about the hidden targets.
- **Line we set for ourselves**: depositing the *reference* file first (proxy + bias, no learning, known
  local RMSE in advance) is a single, justified measurement — it calibrates the local→ranking transfer
  factor, and no recipe is tuned with that figure. Iterating variants based on the displayed scores, on
  the other hand, would be exactly the practice the warning targets: we will not do it. All model choices
  remain made on local data (D‑009, D‑030).

## Calendar

- Competition from 1 September to **14 October 2026, 12:00 CET (10:00 Z)**, deadline extended.
- Internal goal: recipe frozen at least 24 h before the deadline.

## Prize eligibility

1. No non-open external data; any additional data under an open licence and documented.
2. Public code on GitHub under **GNU GPLv3** (forked by the challenge account).
3. Sufficient documentation to reproduce the results.
4. Original solution: reusing an existing implementation requires the authors' consent **and**
   significant modifications to the algorithm or model.

## What the rules do not say (and must not be invented)

- **No prediction instant is specified**: no text requires predicting before pushback, before take‑off,
  or at any other moment.
- **No list of forbidden variables**: the rules describe the columns, they declare no column unusable.
- Methodological consequence (prompt §6): the absence of a prohibition **does not prove** admissibility.
  The two tracks of the project are therefore explicitly labelled *prediction* or *reconstruction* in
  `FEATURE_ADMISSIBILITY.md`, and the submission decision is traced in `DECISIONS.md`.
