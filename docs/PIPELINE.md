# How the data is produced

English | [简体中文](PIPELINE_zh-cn.md)

How the 41 systems behind the [reference lines](../README.md) are scanned, measured and checked. Current baseline: run #36 (`45829165719'), 2026-11-26T13:26:27Z to 2026-11-26T18:13:24Z UTC (4h 46m 57s).

## Directory layout

| Path | Content |
|---|---|
| `repos.yaml` | Scan list (owner / repo / branch / skip / notes; the first character of `notes` is the tier letter) |
| `.github/workflows/scan.yml` | Batch scan workflow (matrix, one repo at a time, `max-parallel: 1`) |
| `scripts/install-cli.sh` | Downloads the KE CLI (manifest latest + sha256 check + version assertion, currently `0.3.10`) |
| `scripts/preflight-skip.sh` | Zero-drift short circuit (skips the whole repo when the remote HEAD and the report freshness both match) |
| `scripts/scan-one.sh` | Single-repo scan: clone, then `ke import start` (default `--defer-projection`) |
| `scripts/repo-scale.py` | Repository scale collection (file count / lines, by language), run right after the clone |
| `scripts/compute-metrics.py` | Per-repository metrics to `reports/{owner}/{repo}.json` (numerators, denominators, provenance) |
| `scripts/graph-metrics.py` | Graph-form recomputation of the chain metrics and the dual-path equivalence check (`--compare`, exit 2 on MISMATCH) |
| `scripts/pipeline-status.sh` | Writes the four step conclusions to `pipeline-status/{owner}/{repo}.json` |
| `scripts/census.py` | Aggregated percentiles, per-repository pipeline validation, matrix reconciliation and scale distribution to `census/summary.json` |
| `scripts/render-docs.py` | Renders `README.md` and `docs/` from the artifacts; refuses to write unless every system passed |
| `scripts/validate-docs.py` | Checks the rendered pages against the artifacts (numbers, links, structure, prohibited content) |
| `scripts/push-with-retry.sh` | Bot commit/push retry (rebase only on non-FF, backoff on transient 5xx) |
| `scripts/scale-backfill.py`, `.github/workflows/scale-backfill.yml` | Backfills scale for legacy reports at the pinned commit (idempotent, manual dispatch) |
| `reports/{owner}/{repo}.json` | Per-repository report |
| `pipeline-status/{owner}/{repo}.json` | Per-repository pipeline conclusion |
| `census/summary.json` | Aggregate output: sample list, per-metric percentiles, validation, cohorts, scale distribution |

## Scan pipeline

One job per repo. The chain runs serially inside the job and any failing step fails that repo's job (`fail-fast: false` + `max-parallel: 1`: one repo's failure neither cancels the others nor blocks the trailing census).

```
preflight (zero-drift short circuit)
  1. scan         clone, then import --defer-projection (MySQL only)
  2. projection   ke project <snapshotId> (Neo4j projection)
  3. metrics      compute-metrics.py (direct MySQL queries)
  4. consistency   graph-metrics.py --compare (chain metrics only: graph-form recomputation + dual-path equivalence)
  5. annotate     pipeline-status written + report committed
census           aggregates the artifacts, rolls up every repo's step conclusions, reconciles with the scan matrix
```

- **Triggers**: a push touching `repos.yaml`, a manual dispatch from the Actions tab (optional `scan_force`), or the monthly schedule `0 2 1 * *`. A run-level `concurrency` group keeps the three trigger surfaces mutually exclusive.
- **Default-track dedup**: when both the repo HEAD and the CLI version are unchanged, preflight skips the whole job.
- **Concurrency guard**: `max-parallel: 1` keeps repos serial, so projection has an exclusive window.
- **Documentation**: after the census is committed, `render-docs.py` rebuilds `README.md` and `docs/`, `validate-docs.py` checks them and both are committed. Nothing is written unless every system passed the pipeline.

## What is checked, and what is not

- **Pipeline steps.** All four steps completed for 41 of 41 repositories; failed: 0.
- **Chain metrics.** The consistency step (step 4) covers the chain metrics only. It is not evidence for the reference lines published on the README; their cross-checks are listed in [docs/METRICS.md](METRICS.md).
- **File counts.** The scale collector's file count matches the server's `Repository.fileCount` for 41 of 41 repositories (mismatch 0, unknown 0).
- **Reconciliation.** The `objectCount` on the last line of each scan step matches the platform's snapshot list, and snapshotId / objectCount / sourceHead agree across the report and pipeline-status of each repo.

## Census gating

| Item | Value |
|---|---|
| Samples included | **41** |
| Publish threshold (statistical sufficiency) | total N ≥ 30 gives status `published` |
| Privacy guard (k-anonymity) | slices with N < 5 get no percentiles |
| validation | 41/41 four steps ok; consistency pass 41 / mismatch 0; reconciled with the scan matrix, missing 0 |

> The threshold applies to the total sample. Which individual lines are published on the README is decided by the per-line rule in [docs/METRICS.md](METRICS.md), which this documentation enforces at generation time.

## Reproducing

```bash
# 1. Install the KE CLI (manifest latest + sha256 check + version assertion)
KE_API_KEY=<member key> bash scripts/install-cli.sh /tmp/ke-cli

# 2. Scan one repo (clone --depth 1, then ke import start)
OWNER=macrozheng REPO=mall CLI_DIR=/tmp/ke-cli \
KE_API_KEY=<member key> KE_SERVER_URL=https://console.kengine.ai \
bash scripts/scan-one.sh
# The last line is the import summary JSON (ok / status / snapshotId / objectCount); exit 1 on failure
```
- Reconciliation: the `objectCount` on the last line of the Action step must match the platform's snapshot list; snapshotId / objectCount / sourceHead must agree across the repo report and pipeline-status.

### Rescan track (metric corrections after an analyzer upgrade)

When the repo HEAD is unchanged, `ke import start` hits the already-complete snapshot and is **dedup skipped**: the right behaviour for monthly rescans, but it swallows the metric corrections an analyzer upgrade brings. Rescans after an analyzer upgrade must therefore use the force track (tick `scan_force` when dispatching from the Actions tab, or set `SCAN_FORCE=true` locally):

```bash
SCAN_FORCE=true OWNER=dromara REPO=RuoYi-Vue-Plus CLI_DIR=/tmp/ke-cli \
KE_API_KEY=<member key> KE_SERVER_URL=https://console.kengine.ai \
bash scripts/scan-one.sh
```
- Telling them apart: the force track's summary has `status == "completed"` (rebuilt); the default track with the same HEAD has `"skipped"` (values unchanged).
- Boundary: the force rescan commit is the natural boundary between the old and new metric definitions (traceable in git history).

[Baseline scan run](https://github.com/asdm-ai/asdm-ke-index/actions/runs/45829165719)
