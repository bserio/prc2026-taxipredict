# Arbor contracts for this session (actual state, verified by calls)

## State and identifiers

- `run_name`: `prc2026-v1`. A `tree_view` call confirmed the existence of the tree (root `ROOT`,
  one node). The recorded metadata are the **measured** values, not estimates:
  `baseline_score = 640,8` (overall average on dev), `trunk_score = 557,1` (causal track),
  `metric_direction = minimize`, `eval_timeout = 1800 s`.
- Tree at the time of writing:

| node | hypothesis | dev score | status |
| --- | --- | ---: | --- |
| 1 | LightGBM causal track | 557,1 | adopted (trunk) |
| 1.1 | exclude targets > 7200 s | 570,1 | rejected (D‑011) |
| 2 | analytical reconstruction + clipping | 566,6 | replaced |
| 2.1 | proxy as a variable in LightGBM | **490,8** | best measured |

- Each node's `code_ref` points to the actual configuration file and JSON report, so every
  score shown in the tree is verifiable under `reports/`.

## Arbor ↔ this repository mapping

| Arbor notion | equivalent here |
| --- | --- |
| B_dev | the four held-out months (Jan, Feb, Jun, Jul 2025) concatenated |
| B_test | **internal holdout Nov + Dec 2025**, deliberately never opened |
| trunk | `configs/tabular_causal.toml` (`causal-r2`) |
| experiment | a `run-id` with its `reports/<id>.json`, its models and its config |
| experiment worktree | not used: each recipe is isolated by `--run-id`, artifacts are separated, the official data is read-only |

## Why no Arbor merge has been performed yet (important)

`git_merge_branch` refuses a merge **without a B_test score** and requires an improvement on that
score. Yet the protocol (D‑005) forbids opening the holdout before the recipe freeze, on pain of
rendering it unusable as an uncontaminated estimate. The accepted consequence:

- interim decisions are made **solely** on B_dev and traced in `DECISIONS.md`;
- the Arbor merge (or its git-branch equivalent) will only take place after the freeze, with a
  single opening of the holdout to produce the B_test score;
- no circumvention of the guard (for example by calling the holdout "dev") will be attempted:
  this guard is precisely what protects the validity of the final estimate.

## What remains to be verified on the Arbor side

- `metric_direction = minimize` was accepted by `tree_set_meta`, but the behavior of medals and
  trunk comparisons has not yet been observed with an RMSE: to be confirmed at the first official
  score submission.
- The recorded evaluation commands use a `{node_id}` template; actual command generation by the
  tool has not yet been exercised in this session.

## What Arbor does not decide here

The choice between the causal track and the reconstruction track (D‑004) is a question of
eligibility, not of score: the tree may rank 490,8 < 557,1, but that is no authorization to
submit. This decision remains written in `DECISIONS.md` and is submitted to the project lead.
