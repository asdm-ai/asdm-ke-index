# asdm-ke-index

English | [简体中文](README_zh-cn.md)

Open-source benchmark corpus for KE Index — the scan list, scan pipeline, metric reports and census aggregates.

> This repository is maintained automatically by the AOS / KE batch scan pipeline (GitHub Actions).  
> Data sink: [kengine.ai](https://kengine.ai). Metric definitions: AOS Index Metrics Schema (16 cards — A chain / B structure / C code / D stack).

## Current status (baseline of 2026-11-26)

| Item | Value |
|---|---|
| List / reports / pipeline-status | **41 / 41 / 41** |
| Pipeline (scan → projection → metrics → consistency) | all four steps ok for 41/41; consistency 41 pass / 0 mismatch; 41 / 41 repos pass overall |
| Analyzer version | KE CLI `0.3.10` (homogeneous across 41 repos — values comparable) |
| Data volume | 1,171,119 objects / 8,348,519 links |
| Repository scale (files / lines) | collected for 41/41 repos; file count matches the server `Repository.fileCount` for **41 / 41**; Java lines P50 85,434 / P90 1,086,948 — see [Repository scale](#repository-scale-files--lines) |
| Census | `samples=41`, `status=published`, `schemaVersion=draft-v1` |
| Metrics with N ≥ 30 | **6 / 16** (see [Metric status](#metric-status-all-16-cards-as-listed)) |

Full baseline rebuilt by run #36 (`45829165719`): a complete rescan of all 41 repositories from empty storage (every repo re-cloned at its upstream HEAD; preflight skipped none), triggered by a manual dispatch after a full data wipe. Zero failures, zero zombie snapshots.

Run window: 2026-11-26T13:26:27Z → 2026-11-26T18:13:24Z UTC (4h 46m 57s); repos failing the pipeline: 0.

## Directory layout

| Path | Content |
|---|---|
| `repos.yaml` | Scan list (owner / repo / branch / skip / notes — the first character of `notes` is the tier marker) |
| `.github/workflows/scan.yml` | Batch scan workflow (matrix, one repo at a time, `max-parallel: 1`) |
| `scripts/install-cli.sh` | Downloads the KE CLI (manifest latest + sha256 check + version assertion, currently anchored to `0.3.10`) |
| `scripts/preflight-skip.sh` | Zero-drift short circuit (skips the whole repo when the remote HEAD and the report freshness both match) |
| `scripts/scan-one.sh` | Single-repo scan: clone → `ke import start` (default `--defer-projection`) |
| `scripts/repo-scale.py` | Repository scale collection (file count / lines, by language) — called right after the clone, before the import |
| `scripts/compute-metrics.py` | Per-repo metrics → `reports/{owner}/{repo}.json` (numerators, denominators, provenance) |
| `scripts/graph-metrics.py` | Graph-form recomputation of A1/C1 + dual-path equivalence check (`--compare`, exit 2 on MISMATCH) |
| `scripts/framework-policy.json` | Target version ranges for D1 |
| `scripts/pipeline-status.sh` | Writes the four step conclusions to `pipeline-status/{owner}/{repo}.json` |
| `scripts/census.py` | Aggregated percentiles + validation roll-up + matrix reconciliation + scale distribution → `census/summary.json` |
| `scripts/push-with-retry.sh` | Bot commit/push retry (classified by rejection reason: rebase only on non-FF, backoff on transient 5xx) |
| `scripts/scale-backfill.py`, `.github/workflows/scale-backfill.yml` | Backfills scale for legacy reports at the pinned commit (idempotent, manual dispatch) |
| `reports/{owner}/{repo}.json` | Per-repo metric report |
| `pipeline-status/{owner}/{repo}.json` | Per-repo pipeline conclusion (deterministic artifact) |
| `census/summary.json` | Aggregate output (sample list + per-metric percentiles + validation + D2 cohort + scale distribution) |

## Scan pipeline

One job per repo; the full chain runs serially inside the job and any failing step fails that repo's job (`fail-fast: false` + `max-parallel: 1` — one repo's failure neither cancels the others nor blocks the trailing census):

```
preflight (zero-drift short circuit)
  → ① scan         clone → import --defer-projection (MySQL only)
  → ② projection   ke project <snapshotId> (Neo4j projection)
  → ③ metrics      compute-metrics.py (direct MySQL queries)
  → ④ consistency  graph-metrics.py --compare (graph-form recomputation + dual-path equivalence)
  → ⑤ annotate     pipeline-status written + report committed
census (aggregate the successful artifacts + roll up every repo's step conclusions + reconcile with the scan matrix — a missing repo fails it)
```

- **Triggers**: a push touching `repos.yaml` / manual dispatch from the Actions tab (optional `scan_force`) / monthly schedule `0 2 1 * *` (first run 2026-12-01). A run-level `concurrency` group keeps the three trigger surfaces mutually exclusive.
- **Default-track dedup**: when both the repo HEAD and the CLI version are unchanged, preflight skips the whole job.
- **Concurrency guard**: `max-parallel: 1` — repos are scanned one at a time, so projection has an exclusive window.

## Reproducing

```bash
# 1. Install the KE CLI (manifest latest + sha256 check + version assertion)
KE_API_KEY=<member key> bash scripts/install-cli.sh /tmp/ke-cli

# 2. Scan one repo (clone --depth 1 → ke import start, three-segment upload)
OWNER=macrozheng REPO=mall CLI_DIR=/tmp/ke-cli \
KE_API_KEY=<member key> KE_SERVER_URL=https://console.kengine.ai \
bash scripts/scan-one.sh
# The last line is the import summary JSON (ok / status / snapshotId / objectCount) — exit 1 on failure
```

- Reconciliation: the `objectCount` on the last line of the Action step must match the platform's snapshot list; snapshotId / objectCount / sourceHead must agree across the repo report and pipeline-status.

### Rescan track (metric corrections after an analyzer upgrade)

When the repo HEAD is unchanged, `ke import start` hits the already-complete snapshot and is **dedup skipped** (silently skipped — the correct dedup for monthly rescans, but it swallows the metric corrections an analyzer upgrade brings). Rescans after an analyzer upgrade must therefore use the force track (tick `scan_force` when dispatching from the Actions tab, or set `SCAN_FORCE=true` locally):

```bash
SCAN_FORCE=true OWNER=dromara REPO=RuoYi-Vue-Plus CLI_DIR=/tmp/ke-cli \
KE_API_KEY=<member key> KE_SERVER_URL=https://console.kengine.ai \
bash scripts/scan-one.sh
```

- Telling them apart: the force track's summary has `status == "completed"` (rebuilt); the default track with the same HEAD has `"skipped"` (values unchanged)
- Boundary: the force rescan commit is the natural boundary between the old and new metric definitions (traceable in git history)

## Repository index (41 repos)

### Tiers

| Tier | Count | Shape |
|---|---|---|
| A · Admin / business systems | 18 | Java scaffolds and business systems (MyBatis / MyBatis-Plus / JPA mixes — RuoYi family, Jeecg, yudao, pig and more, plus e-commerce / office / tooling systems) |
| B · Large repositories | 8 | Very large multi-module repositories (mostly Gradle — Apache middleware + cornerstone repos of the Spring ecosystem) |
| C · JPA data-access layer | 8 | JPA shape (contrast with the MyBatis family — IAM / BPM / ERP on the business side + hibernate-orm itself) |
| D · Frontend pairs | 7 | Official frontend repos of tier-A backends (Vue — **pair aggregation is not enabled; they are listed as standalone frontends**) |

> The full list is in [repos.yaml](repos.yaml). Snapshot IDs are truncated to 8 characters (full values in the `repos` block of `census/summary.json` — the machine-readable source).

### All repositories

| # | owner/repo | Tier | Report | Snapshot | Objects | Links | Files | Java files | Lines | Java lines | Pipeline |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | [macrozheng/mall](https://github.com/macrozheng/mall) | A | [report](reports/macrozheng/mall.json) | `104877ef` | 14,527 | 35,226 | 717 | 524 | 155,807 | 85,434 | ✅ |
| 2 | [macrozheng/mall-swarm](https://github.com/macrozheng/mall-swarm) | A | [report](reports/macrozheng/mall-swarm.json) | `867c82e8` | 14,878 | 36,007 | 782 | 533 | 158,492 | 87,880 | ✅ |
| 3 | [yangzongzhuan/RuoYi-Vue](https://github.com/yangzongzhuan/RuoYi-Vue) | A | [report](reports/yangzongzhuan/RuoYi-Vue.json) | `756caa24` | 2,560 | 7,765 | 334 | 266 | 43,618 | 34,332 | ✅ |
| 4 | [dromara/RuoYi-Vue-Plus](https://github.com/dromara/RuoYi-Vue-Plus) | A | [report](reports/dromara/RuoYi-Vue-Plus.json) | `a3e8b577` | 4,777 | 22,903 | 980 | 766 | 113,995 | 83,151 | ✅ |
| 5 | [jeecgboot/JeecgBoot](https://github.com/jeecgboot/JeecgBoot) | A | [report](reports/jeecgboot/JeecgBoot.json) | `3f1b932d` | 15,697 | 116,780 | 4,020 | 995 | 803,350 | 136,494 | ✅ |
| 6 | [lenve/vhr](https://github.com/lenve/vhr) | A | [report](reports/lenve/vhr.json) | `a359e4fa` | 991 | 1,436 | 242 | 91 | 20,328 | 5,581 | ✅ |
| 7 | [YunaiV/ruoyi-vue-pro](https://github.com/YunaiV/ruoyi-vue-pro) | A | [report](reports/YunaiV/ruoyi-vue-pro.json) | `2249ebcd` | 46,623 | 230,904 | 9,710 | 8,161 | 1,024,622 | 798,916 | ✅ |
| 8 | [yangzongzhuan/RuoYi-Cloud](https://github.com/yangzongzhuan/RuoYi-Cloud) | A | [report](reports/yangzongzhuan/RuoYi-Cloud.json) | `e7f1c4d0` | 2,532 | 8,741 | 407 | 274 | 43,949 | 32,652 | ✅ |
| 9 | [pig-mesh/pig](https://github.com/pig-mesh/pig) | A | [report](reports/pig-mesh/pig.json) | `3d9872f0` | 2,546 | 7,737 | 708 | 563 | 61,689 | 49,370 | ✅ |
| 10 | [newbee-ltd/newbee-mall](https://github.com/newbee-ltd/newbee-mall) | A | [report](reports/newbee-ltd/newbee-mall.json) | `fad84fb5` | 933 | 1,470 | 318 | 88 | 118,606 | 7,609 | ✅ |
| 11 | [stylefeng/Guns](https://github.com/stylefeng/Guns) | A ⚠️ | [report](reports/stylefeng/Guns.json) | `9dda3f5a` | 1,377 | 10,042 | 406 | 18 | 60,821 | 1,210 | ✅ |
| 12 | [renrenio/renren-fast](https://github.com/renrenio/renren-fast) | A | [report](reports/renrenio/renren-fast.json) | `41ba483e` | 777 | 3,326 | 223 | 143 | 39,002 | 8,821 | ✅ |
| 13 | [thinkgem/jeesite](https://github.com/thinkgem/jeesite) | A ⚠️ | [report](reports/thinkgem/jeesite.json) | `77063f14` | 2,670 | 14,623 | 845 | 0 | 92,527 | 0 | ✅ |
| 14 | [o2oa/o2oa](https://github.com/o2oa/o2oa) | A | [report](reports/o2oa/o2oa.json) | `c19b3102` | 70,501 | 710,059 | 27,933 | 7,824 | 2,751,818 | 773,636 | ✅ |
| 15 | [chillzhuang/SpringBlade](https://github.com/chillzhuang/SpringBlade) | A | [report](reports/chillzhuang/SpringBlade.json) | `779fd2e5` | 1,073 | 3,002 | 423 | 258 | 34,554 | 17,484 | ✅ |
| 16 | [dromara/dante-cloud](https://github.com/dromara/dante-cloud) | A ⚠️ | [report](reports/dromara/dante-cloud.json) | `2cdd68f7` | 476 | 728 | 892 | 77 | 144,080 | 5,737 | ✅ |
| 17 | [linlinjava/litemall](https://github.com/linlinjava/litemall) | A | [report](reports/linlinjava/litemall.json) | `4de8e93f` | 13,172 | 34,102 | 1,591 | 333 | 227,993 | 116,435 | ✅ |
| 18 | [metersphere/metersphere](https://github.com/metersphere/metersphere) | A | [report](reports/metersphere/metersphere.json) | `a5733632` | 43,718 | 157,807 | 4,716 | 2,706 | 860,678 | 372,881 | ✅ |
| 19 | [apache/dubbo](https://github.com/apache/dubbo) | B | [report](reports/apache/dubbo.json) | `c170d16e` | 34,065 | 136,879 | 4,861 | 4,060 | 524,398 | 484,107 | ✅ |
| 20 | [apache/fineract](https://github.com/apache/fineract) | B | [report](reports/apache/fineract.json) | `580ff321` | 54,054 | 266,418 | 9,115 | 7,647 | 1,538,051 | 1,005,293 | ✅ |
| 21 | [apache/rocketmq](https://github.com/apache/rocketmq) | B | [report](reports/apache/rocketmq.json) | `38fd86d7` | 26,486 | 109,906 | 2,805 | 2,318 | 437,047 | 401,952 | ✅ |
| 22 | [alibaba/nacos](https://github.com/alibaba/nacos) | B | [report](reports/alibaba/nacos.json) | `922f4ddb` | 57,387 | 435,556 | 7,382 | 5,442 | 1,320,342 | 849,146 | ✅ |
| 23 | [apache/shardingsphere](https://github.com/apache/shardingsphere) | B | [report](reports/apache/shardingsphere.json) | `82f2d160` | 56,172 | 447,822 | 17,467 | 9,916 | 1,501,418 | 836,710 | ✅ |
| 24 | [spring-projects/spring-boot](https://github.com/spring-projects/spring-boot) | B | [report](reports/spring-projects/spring-boot.json) | `4b21f1bf` | 65,047 | 141,756 | 11,620 | 8,443 | 922,863 | 752,549 | ✅ |
| 25 | [spring-projects/spring-framework](https://github.com/spring-projects/spring-framework) | B | [report](reports/spring-projects/spring-framework.json) | `8cdd2ce5` | 105,969 | 286,288 | 11,402 | 9,244 | 1,595,393 | 1,430,520 | ✅ |
| 26 | [alibaba/druid](https://github.com/alibaba/druid) | B | [report](reports/alibaba/druid.json) | `fe51de02` | 41,208 | 234,102 | 6,740 | 5,359 | 702,517 | 598,992 | ✅ |
| 27 | [spring-projects/spring-petclinic](https://github.com/spring-projects/spring-petclinic) | C | [report](reports/spring-projects/spring-petclinic.json) | `c604adfb` | 283 | 626 | 131 | 50 | 27,644 | 4,297 | ✅ |
| 28 | [elunez/eladmin](https://github.com/elunez/eladmin) | C | [report](reports/elunez/eladmin.json) | `8389435e` | 1,357 | 5,096 | 305 | 274 | 26,578 | 23,267 | ✅ |
| 29 | [keycloak/keycloak](https://github.com/keycloak/keycloak) | C | [report](reports/keycloak/keycloak.json) | `fa090d70` | 92,061 | 499,683 | 13,527 | 8,712 | 1,850,827 | 1,309,630 | ✅ |
| 30 | [flowable/flowable-engine](https://github.com/flowable/flowable-engine) | C | [report](reports/flowable/flowable-engine.json) | `6e898ac7` | 76,265 | 215,262 | 16,202 | 8,082 | 1,730,889 | 1,086,948 | ✅ |
| 31 | [Activiti/Activiti](https://github.com/Activiti/Activiti) | C | [report](reports/Activiti/Activiti.json) | `385b3aa1` | 24,203 | 85,736 | 5,387 | 3,095 | 476,182 | 353,553 | ✅ |
| 32 | [hibernate/hibernate-orm](https://github.com/hibernate/hibernate-orm) | C | [report](reports/hibernate/hibernate-orm.json) | `39412056` | 180,951 | 421,035 | 21,338 | 19,251 | 2,483,974 | 2,312,508 | ✅ |
| 33 | [dhis2/dhis2-core](https://github.com/dhis2/dhis2-core) | C | [report](reports/dhis2/dhis2-core.json) | `0607cfca` | 63,457 | 411,972 | 10,299 | 6,670 | 1,621,862 | 1,289,926 | ✅ |
| 34 | [BroadleafCommerce/BroadleafCommerce](https://github.com/BroadleafCommerce/BroadleafCommerce) | C | [report](reports/BroadleafCommerce/BroadleafCommerce.json) | `42c6eff8` | 25,682 | 108,282 | 3,866 | 2,983 | 563,954 | 353,597 | ✅ |
| 35 | [macrozheng/mall-admin-web](https://github.com/macrozheng/mall-admin-web) | D | [report](reports/macrozheng/mall-admin-web.json) | `a9ea2b99` | 1,662 | 29,228 | 358 | 0 | 36,098 | 0 | ✅ |
| 36 | [yangzongzhuan/RuoYi-Vue3](https://github.com/yangzongzhuan/RuoYi-Vue3) | D | [report](reports/yangzongzhuan/RuoYi-Vue3.json) | `f98278f7` | 1,078 | 6,243 | 281 | 0 | 26,397 | 0 | ✅ |
| 37 | [jeecgboot/jeecgboot-vue3](https://github.com/jeecgboot/jeecgboot-vue3) | D | [report](reports/jeecgboot/jeecgboot-vue3.json) | `5802e1ef` | 4,755 | 25,600 | 1,424 | 0 | 173,262 | 0 | ✅ |
| 38 | [pig-mesh/pig-ui](https://github.com/pig-mesh/pig-ui) | D | [report](reports/pig-mesh/pig-ui.json) | `11e95353` | 1,974 | 11,417 | 479 | 0 | 59,233 | 0 | ✅ |
| 39 | [yudaocode/yudao-ui-admin-vue3](https://github.com/yudaocode/yudao-ui-admin-vue3) | D | [report](reports/yudaocode/yudao-ui-admin-vue3.json) | `5ddd7597` | 16,456 | 3,065,439 | 3,274 | 0 | 509,620 | 0 | ✅ |
| 40 | [elunez/eladmin-web](https://github.com/elunez/eladmin-web) | D | [report](reports/elunez/eladmin-web.json) | `52df4d82` | 538 | 1,133 | 279 | 0 | 18,332 | 0 | ✅ |
| 41 | [newbee-ltd/newbee-mall-vue3-app](https://github.com/newbee-ltd/newbee-mall-vue3-app) | D | [report](reports/newbee-ltd/newbee-mall-vue3-app.json) | `c406ff31` | 181 | 382 | 59 | 0 | 10,854 | 0 | ✅ |

> ⚠️ **Tier drift**: `.java` is not the largest file group in 3 tier-A repos (stylefeng/Guns — 18 `.java` files against 163 `.vue` files; thinkgem/jeesite — 0 `.java` files against 409 `.typescript` files; dromara/dante-cloud — 77 `.java` files against 637 `.sql` files). They still count toward tier A (18 repos), but their Java-side metrics (A3/A4, domains B and C) have limited sample representativeness.

## Repository scale (files / lines)

Scale is collected during the scan (`scan-one.sh`, right after the clone and before the import — same working tree, same HEAD) by `scripts/repo-scale.py`. It is stored under `report.metrics.D3.scale` in each report and summarised per repo (`repos[]`) and across repos (`cohort.scale`) in `census/summary.json`. It is a size reference for the other metrics and is not scored.

### Definitions

| Field | Definition |
|---|---|
| Files `fileCount` | Tracked files, excluding directories the analyzer skips (`target` / `build` / `dist` / `node_modules`, …) and non-regular files such as symlinks. Same definition as the analyzer's `Repository.fileCount`; compared per repo during the scan (a mismatch only warns). |
| Java files `javaFiles` | The `.java` files among them |
| Lines `lineCount` | Physical lines of text files, comments and blank lines included — **not SLOC**. Binary files (NUL in the first 8000 bytes) are not counted. |
| Java lines `javaLines` | Physical lines of `.java` files |

### Totals across the corpus

| Measure | Sum over all repos | Smallest repo | Largest repo |
|---|---|---|---|
| Files | 203,848 | 59 | 27,933 |
| Java files | 125,166 | 0 | 19,251 |
| Lines | 24,913,664 | 10,854 | 2,751,818 |
| Java lines | 15,710,618 | 0 | 2,312,508 |

Java accounts for 63.1% of all counted lines and 61.4% of counted files. The 41 repos hold 204,788 tracked files in git (185,807 counted as text, 18,041 detected as binary and skipped). Collected by: `scan`.

### Distribution across repos

| Measure | N | Missing | Min | P25 | P50 | P75 | P90 | Max | Sum | Mean |
|---|---|---|---|---|---|---|---|---|---|---|
| Files `fileCount` | 41 | 0 | 59 | 406 | 1,424 | 7,382 | 13,527 | 27,933 | 203,848 | 4,972 |
| Java files `javaFiles` | 41 | 0 | 0 | 77 | 533 | 5,442 | 8,443 | 19,251 | 125,166 | 3,053 |
| Lines `lineCount` | 41 | 0 | 10,854 | 43,949 | 173,262 | 922,863 | 1,621,862 | 2,751,818 | 24,913,664 | 607,650 |
| Java lines `javaLines` | 41 | 0 | 0 | 5,581 | 85,434 | 752,549 | 1,086,948 | 2,312,508 | 15,710,618 | 383,186 |

Percentiles are nearest-rank values from `census/summary.json`.

### By tier

| Tier | Repos | Median files | Median lines | Median Java lines | Sum of Java lines |
|---|---|---|---|---|---|
| A · Admin / business systems | 18 | 749 | 116,300 | 41,851 | 2,617,623 |
| B · Large repositories | 8 | 8,248 | 1,121,602 | 794,629 | 6,359,269 |
| C · JPA data-access layer | 8 | 7,843 | 1,092,908 | 720,272 | 6,733,726 |
| D · Frontend pairs | 7 | 358 | 36,098 | 0 | 0 |

### Largest repositories

By Java lines:

| Repository | Java lines | Lines | Java files | Files |
|---|---|---|---|---|
| [hibernate/hibernate-orm](https://github.com/hibernate/hibernate-orm) | 2,312,508 | 2,483,974 | 19,251 | 21,338 |
| [spring-projects/spring-framework](https://github.com/spring-projects/spring-framework) | 1,430,520 | 1,595,393 | 9,244 | 11,402 |
| [keycloak/keycloak](https://github.com/keycloak/keycloak) | 1,309,630 | 1,850,827 | 8,712 | 13,527 |
| [dhis2/dhis2-core](https://github.com/dhis2/dhis2-core) | 1,289,926 | 1,621,862 | 6,670 | 10,299 |
| [flowable/flowable-engine](https://github.com/flowable/flowable-engine) | 1,086,948 | 1,730,889 | 8,082 | 16,202 |

By total lines:

| Repository | Lines | Java lines | Java files | Files |
|---|---|---|---|---|
| [o2oa/o2oa](https://github.com/o2oa/o2oa) | 2,751,818 | 773,636 | 7,824 | 27,933 |
| [hibernate/hibernate-orm](https://github.com/hibernate/hibernate-orm) | 2,483,974 | 2,312,508 | 19,251 | 21,338 |
| [keycloak/keycloak](https://github.com/keycloak/keycloak) | 1,850,827 | 1,309,630 | 8,712 | 13,527 |
| [flowable/flowable-engine](https://github.com/flowable/flowable-engine) | 1,730,889 | 1,086,948 | 8,082 | 16,202 |
| [dhis2/dhis2-core](https://github.com/dhis2/dhis2-core) | 1,621,862 | 1,289,926 | 6,670 | 10,299 |

### Lines by language

| Language (by extension) | Lines | Share | Files |
|---|---|---|---|
| `java` | 15,710,618 | 63.1% | 125,166 |
| `javascript` | 1,952,331 | 7.8% | 5,818 |
| `other` | 1,593,683 | 6.4% | 30,779 |
| `vue` | 1,028,838 | 4.1% | 5,497 |
| `xml` | 1,012,698 | 4.1% | 13,453 |
| `json` | 882,181 | 3.5% | 2,240 |
| `sql` | 404,530 | 1.6% | 4,431 |
| `html` | 387,821 | 1.6% | 2,016 |
| `typescript` | 371,773 | 1.5% | 4,074 |
| `yaml` | 313,054 | 1.3% | 2,330 |
| other (11 more) | 1,256,137 | 5.0% | 8,044 |

- **Java lines are the primary size reference.** Total lines are inflated by design documents, SVG and generated artifacts (in macrozheng/mall the `other` bucket — unrecognised extensions, here mostly the `.pdb` / `.pdm` design files — alone contributes 41,854 lines).
- Per-language detail (`linesByLanguage` / `filesByLanguage`) is part of each report.

## Metric status (all 16 cards, as listed)

Percentiles are nearest-rank values over each metric's own slice (from `census/summary.json`). **The status column is the point of this table** — N is the number of repos for which the metric is actually computable, and only slices with N ≥ 30 are statistically sufficient to serve as a reference line.

| Metric | Name | Direction | N | Missing | P25 | P50 | P75 | Status |
|---|---|---|---|---|---|---|---|---|
| A1 | Full-chain coverage | Higher is better | 18 | 23 | 0 | 0 | 0 | ⚠️ Below threshold (short by 12), degenerate distribution |
| A2 | Frontend-backend break rate | Lower is better | 18 | 23 | 1 | 1 | 1 | ⚠️ Below threshold (short by 12), degenerate distribution |
| A3 | Orphan-table rate | Lower is better | 29 | 12 | 0.21 | 0.5362 | 0.9806 | ⚠️ Below threshold (short by 1) |
| A4 | Table ↔ entity mapping rate | Higher is better | 29 | 12 | 0.0194 | 0.4638 | 0.79 | ⚠️ Below threshold (short by 1) |
| B1.backend | Circular dependency density (backend) | Lower is better | 33 | 8 | 0.0909 | 0.2126 | 0.4223 | ✅ Reference-ready |
| B1.frontend | Circular dependency density (frontend) | Lower is better | 27 | 14 | 0 | 0 | 0.003 | ⚠️ Below threshold (short by 3) |
| B2 | Package dependency density | Lower is better | 33 | 8 | 2.3617 | 4.6343 | 7.6102 | ✅ Reference-ready |
| B3 | God-class share | Lower is better | 33 | 8 | 0.0062 | 0.0253 | 0.0356 | ✅ Reference-ready |
| B4 | Component coupling | Lower is better | 17 | 24 | 0.0503 | 0.2294 | 0.3462 | ⚠️ Below threshold (short by 13) |
| C1 | End-to-end hop count | Range-type | 1 | 40 | — | — | — | ⛔ No percentiles (k-anonymity N < 5) |
| C2 | Cyclomatic complexity P90 | Lower is better | 33 | 8 | 2 | 3 | 3 | ✅ Reference-ready |
| C3 | Test-method share | Higher is better | 33 | 8 | 0.0043 | 0.0397 | 0.1672 | ✅ Reference-ready |
| C4 | God-method share | Lower is better | 33 | 8 | 0.0014 | 0.003 | 0.0073 | ✅ Reference-ready |
| D1 | Framework version coverage | Higher is better | 6 | 35 | 0.5 | 0.5 | 1 | ❌ Values not usable yet |
| D2 | Dependency homogeneity | Descriptive | cohort | — | — | value 0.375 | — | ❌ Values not usable yet |
| D3 | Scale profile | Descriptive | 41 | 0 | objects 181 | 14,527 | 180,951 | ℹ️ Descriptive |
| D4 | Year-over-year evolution | Descriptive | 0 | 41 | — | — | — | ⛔ No time series (single snapshot per repo) |

B1 is listed as two rows (backend / frontend), so the 16 cards appear as 17 rows.

### Per-metric notes

**Domain A (chain)**

- **A1 / A2 / C1**: `ApiEndpoint` is the frontend call-site object and pure backend repos do not produce it — the 23 repos without it are a definitional absence, not a scan failure. These three metrics are therefore only computable when frontend call sites and the paired backend coexist in one snapshot, and under the current sample no reference line can be formed:
  - of the 18 repos with a value, 7 are standalone tier-D frontends (no paired backend in the snapshot, so A1 is always 0 and A2 always 1);
  - among the other 11, only lenve/vhr reaches A1 = 1.0 (a denominator of 1 endpoint); the remaining 10 are at 0, with 1–123 endpoints;
  - C1 has a value for 1 repo(s); the other 17 with endpoints have no complete chain.
- **A3 / A4**: N = 29. Of the 12 missing repos, 7 are frontends and 5 are backends (thinkgem/jeesite, o2oa/o2oa, apache/dubbo, keycloak/keycloak and BroadleafCommerce/BroadleafCommerce) — their DDL is not in parseable inline `.sql` files, so there are no `Table` objects. Among the 29 repos with a value, 7 have A3 = 1.0 (every table orphaned) and 4 have A3 = 0; the distribution is clearly bimodal with a very wide P25–P75 range.

**Domain B (structure)**

- **B1.backend / B2 / B3**: N = 33, currently the most reliable group. The 8 missing repos are the 7 tier-D frontends plus thinkgem/jeesite (no `Package` / `Class` objects).
- **B1.frontend**: N = 27.
- **B4**: N = 17 — computable only for repos that have component objects.

**Domain C (code)**

- **C2 / C3 / C4**: N = 33, the same slice as the backend metrics of domain B.

**Domain D (stack)**

- **D1**: only 6 repos have a value, and the values are not usable. In Maven multi-module repos most dependency versions are inherited from a parent POM, so extraction yields an empty string or a property placeholder (`${...}` / `@x@`) — the 6 repos with a value have only 1–7 judgeable dependencies each, and `@x@`-style placeholders are still treated as judgeable versions and counted as out of range (spring-boot itself gets D1 = 0 that way).
- **D2**: the cohort value 0.375 is not usable — each framework is used by only 1–5 repos, and the dominant version of 2 of them is itself a placeholder string.

| Framework | Repos using | Distinct versions | Dominant version | Dominant share |
|---|---|---|---|---|
| druid | 5 | 5 | `${druid.version}` | 20.0% |
| mybatis | 1 | 1 | `3.4.0` | 100.0% |
| mysql-connector-j | 5 | 4 | `8.0.33` | 40.0% |
| spring-boot | 3 | 3 | `${springboot2.version}` | 33.3% |
| spring-framework | 2 | 2 | `6.1.21` | 50.0% |

- **D3**: describable for all 41 repos. Objects 181–180,951 (median 14,527); links 382–3,065,439 (median 35,226).
- **D4**: 0 repos have a value. Year-over-year evolution needs several periods of data; it only becomes meaningful once the monthly rescan has accumulated a few rounds.

## Census gating

| Item | Value |
|---|---|
| Samples included | **41** |
| Publish threshold (statistical sufficiency) | total N ≥ 30 → `published` (currently N = 41) |
| Privacy guard (k-anonymity, per metric) | slices with N < 5 get no percentiles |
| Current status | `published`, `schemaVersion=draft-v1` |
| validation | 41/41 four steps ok; consistency pass 41 / mismatch 0; reconciled with the scan matrix, missing 0 |

> **Reading note**: `census.py` currently applies the threshold of 30 to the **total sample**; individual metric slices only get the k-anonymity guard (percentiles as soon as N ≥ 5). The rule "each slice independently needs N ≥ 30 to produce a reference line" is not implemented yet, so slices with small N in `summary.json` also carry percentiles. Use the status column of the table above when citing numbers.

## Known limitations

1. **Tier slices and the corpus fitness score are not available yet.** The tiers are A18 / B8 / C8 / D7, each below 30; the total of 41 is also below the 50 the fitness score requires. At this stage only the whole-corpus slice is statistically sufficient.
2. **A1 / A2 / C1 depend on frontend-backend pair aggregation**, which is not enabled; tier-D frontends are listed as standalone repos.
3. **D1 / D2 depend on Maven version-inheritance resolution**, which the platform does not do yet.
4. **Consistency coverage is limited.** Repos without `ApiEndpoint` skip the graph-form comparison (23 repos); of the 41 passes, at most 18 actually ran the dual-path equivalence check.
5. **Some per-repo values await attribution.** yudaocode/yudao-ui-admin-vue3 has 3,065,439 links for 16,456 objects (about 186 links per object, far above the other repos); dhis2-core's A4 is only 0.0275.
6. **Tier drift** in 3 repos (see the ⚠️ marks in the repository index).

## Disclosure

- The list is a tiered selection of well-known Java repositories, **not a random sample** — there is self-selection bias, and the percentile reference lines do not represent an industry survey.
- Reports contain only aggregate counts and metric values, no source-code strings; only aggregate percentiles are published externally, and single-repo metric values are not published separately.

