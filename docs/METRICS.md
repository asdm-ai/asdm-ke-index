# Reference lines: definitions and raw numbers

English | [简体中文](METRICS_zh-cn.md)

This page documents the reference lines published on the [README](../README.md), and only those. Baseline 2026-11-26, run #36 (`45829165719`).

## Overview

| Reference line | Definition | Direction | Systems (N) | P25 | P50 | P75 | P90 | Mean |
|---|---|---|---|---|---|---|---|---|
| Circular dependency density | Share of all packages that sit in a dependency cycle (two or more packages that can reach each other) | Lower is better | 33 | 0.0909 | 0.2126 | 0.4223 | 0.5031 | 0.2459 |
| Package dependency density | Dependency edges between packages divided by the number of packages | Range | 33 | 2.3617 | 4.6343 | 7.6102 | 9.1023 | 5.0892 |
| Giant-class share | Share of all classes with more than 500 lines | Lower is better | 33 | 0.0062 | 0.0253 | 0.0356 | 0.0821 | 0.0356 |
| Cyclomatic complexity (P90) | The cyclomatic complexity that 90% of methods stay within (90th percentile over methods that carry a complexity value) | Lower is better | 33 | 2 | 3 | 3 | 4 | 2.7576 |
| Test-method share | Test methods as a share of all methods | Higher is better | 33 | 0.0043 | 0.0397 | 0.1672 | 0.3014 | 0.1089 |
| Giant-method share | Share of methods with more than 80 lines, among methods with a recorded line count | Lower is better | 33 | 0.0014 | 0.003 | 0.0073 | 0.0148 | 0.0051 |

## How each line is computed

### Circular dependency density (`B1.backend`)

- **Definition.** Share of all packages that sit in a dependency cycle (two or more packages that can reach each other).
- **Computation.** Tarjan strongly connected components over the repository's package dependency graph. Numerator: packages in components of two or more. Denominator: all packages.
- **Direction.** Lower is better. Systems with a value: 33; without: 8.
- **Cross-check.** None yet: the line is computed in one pass from the package dependency list.

### Package dependency density (`B2`)

- **Definition.** Dependency edges between packages divided by the number of packages.
- **Computation.** Numerator: `dependsOn` edges between packages of the repository. Denominator: number of packages.
- **Direction.** Range. Systems with a value: 33; without: 8.
- **Cross-check.** None yet: the line is computed in one pass from the package dependency list.

### Giant-class share (`B3`)

- **Definition.** Share of all classes with more than 500 lines.
- **Computation.** Numerator: classes with `lineCount > 500`. Denominator: all classes.
- **Direction.** Lower is better. Systems with a value: 33; without: 8.
- **Cross-check.** One of the two counts behind the line was compared, per repository, with a separate filtered count from the server: 33 of 33 match.

### Cyclomatic complexity (P90) (`C2`)

- **Definition.** The cyclomatic complexity that 90% of methods stay within (90th percentile over methods that carry a complexity value).
- **Computation.** Nearest-rank 90th percentile of per-method cyclomatic complexity. Denominator: methods with a complexity value.
- **Direction.** Lower is better. Systems with a value: 33; without: 8.
- **Cross-check.** One of the two counts behind the line was compared, per repository, with a separate filtered count from the server: 33 of 33 match.

### Test-method share (`C3`)

- **Definition.** Test methods as a share of all methods.
- **Computation.** Numerator: methods flagged as tests. Denominator: all methods.
- **Direction.** Higher is better. Systems with a value: 33; without: 8.
- **Cross-check.** One of the two counts behind the line was compared, per repository, with a separate filtered count from the server: 33 of 33 match.

### Giant-method share (`C4`)

- **Definition.** Share of methods with more than 80 lines, among methods with a recorded line count.
- **Computation.** Numerator: methods with `lineCount > 80`. Denominator: methods with a recorded line count (zero or missing line counts are excluded).
- **Direction.** Lower is better. Systems with a value: 33; without: 8.
- **Cross-check.** One of the two counts behind the line was compared, per repository, with a separate filtered count from the server: 33 of 33 match.

## Rules

- **Publishing.** A reference line is published when at least 30 systems carry a value.
- **Percentiles.** Nearest-rank, computed over the systems that carry a value for the line.
- **Scope.** All lines are computed over the whole corpus; per-type reference lines come once a type reaches the threshold.
- **Source.** `census/summary.json` in this repository; per-repository values in `reports/`. [Baseline scan run](https://github.com/asdm-ai/asdm-ke-index/actions/runs/45829165719).
