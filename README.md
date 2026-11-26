# ASDM KE Index

English | [简体中文](README_zh-cn.md)

**The public benchmark of KE, the Legacy System Cognition Engine.** Let AI understand the systems a company has run for ten years, and take over every iteration of them.

[Reference lines](#reference-lines) · [Data scale and coverage](#data-scale-and-coverage) · [How to use it](#how-to-use-it) · [Where the data comes from](#where-the-data-comes-from) · [Scope and limits](#scope-and-limits)

| Systems | Lines of code | Reference lines | Baseline |
|---|---|---|---|
| **41 open-source systems** | **24.9M lines** | **6** | **2026-11-26** |

## The problem

AI writes code quickly now, but understanding a system that has been maintained for ten years is still slow. Before AI can safely take over changes to such a system, three questions need answers: how tangled is its structure, what does one change touch, and how healthy is the code?

KE answers the first two with a knowledge graph and impact analysis. KE Index answers the third: it runs 41 well-known open-source Java systems through the same engine and turns the results into a public, checkable yardstick. Once your own system is on board, its measurements have something to be compared against.

It is written for architecture teams modernising a core system, engineering organisations adopting AI coding tools at scale, and technical leads who need to report on system health.

## What KE measures

| Capability | Question it answers | Reference lines |
|---|---|---|
| Read the structure | How tangled are the dependencies between modules | circular dependency density, package dependency density |
| See code quality | How hard is the code to change, and how much of it is tested | giant-class share, cyclomatic complexity (P90), test-method share, giant-method share |

All 6 published reference lines cover back-end Java code. Definitions and raw numbers: [docs/METRICS.md](docs/METRICS.md).

## Reference lines

> Sample: 33 of the 41 systems (the other 8 are 7 frontend projects and 1 without a Java package structure). Baseline: 2026-11-26. How the numbers are checked: [Where the data comes from](#where-the-data-comes-from).

| Reference line | What it measures | Direction | P25 | Median (P50) | P75 |
|---|---|---|---|---|---|
| Circular dependency density | Share of all packages that sit in a dependency cycle (two or more packages that can reach each other) | Lower is better | 9.1% | 21.3% | 42.2% |
| Package dependency density | Dependency edges between packages divided by the number of packages | Range | 2.3617 | 4.6343 | 7.6102 |
| Giant-class share | Share of all classes with more than 500 lines | Lower is better | 0.62% | 2.5% | 3.6% |
| Cyclomatic complexity (P90) | The cyclomatic complexity that 90% of methods stay within (90th percentile over methods that carry a complexity value) | Lower is better | 2 | 3 | 3 |
| Test-method share | Test methods as a share of all methods | Higher is better | 0.43% | 4.0% | 16.7% |
| Giant-method share | Share of methods with more than 80 lines, among methods with a recorded line count | Lower is better | 0.14% | 0.30% | 0.73% |

The median splits the sample in half; P25 to P75 covers the middle half of the systems. On a "lower is better" line, a value above P75 means the system is worse than three quarters of the sample. A range-type line has no good or bad direction: a value between P25 and P75 is common.

## Data scale and coverage

Every system below was scanned by the KE engine itself; nothing is copied from a third-party statistic. Objects and links are the nodes and relationships of the knowledge graph KE built from the system. Files and lines are counted on the source tree of the scanned commit (physical lines, comments and blank lines included).

All 41 systems in the order of [repos.yaml](repos.yaml).

| # | Repository | Type | Objects | Links | Files | Java files | Lines | Java lines |
|---|---|---|---|---|---|---|---|---|
| 1 | [macrozheng/mall](https://github.com/macrozheng/mall) | Business systems | 14,527 | 35,226 | 717 | 524 | 155,807 | 85,434 |
| 2 | [macrozheng/mall-swarm](https://github.com/macrozheng/mall-swarm) | Business systems | 14,878 | 36,007 | 782 | 533 | 158,492 | 87,880 |
| 3 | [yangzongzhuan/RuoYi-Vue](https://github.com/yangzongzhuan/RuoYi-Vue) | Business systems | 2,560 | 7,765 | 334 | 266 | 43,618 | 34,332 |
| 4 | [dromara/RuoYi-Vue-Plus](https://github.com/dromara/RuoYi-Vue-Plus) | Business systems | 4,777 | 22,903 | 980 | 766 | 113,995 | 83,151 |
| 5 | [jeecgboot/JeecgBoot](https://github.com/jeecgboot/JeecgBoot) | Business systems | 15,697 | 116,780 | 4,020 | 995 | 803,350 | 136,494 |
| 6 | [lenve/vhr](https://github.com/lenve/vhr) | Business systems | 991 | 1,436 | 242 | 91 | 20,328 | 5,581 |
| 7 | [YunaiV/ruoyi-vue-pro](https://github.com/YunaiV/ruoyi-vue-pro) | Business systems | 46,623 | 230,904 | 9,710 | 8,161 | 1,024,622 | 798,916 |
| 8 | [yangzongzhuan/RuoYi-Cloud](https://github.com/yangzongzhuan/RuoYi-Cloud) | Business systems | 2,532 | 8,741 | 407 | 274 | 43,949 | 32,652 |
| 9 | [pig-mesh/pig](https://github.com/pig-mesh/pig) | Business systems | 2,546 | 7,737 | 708 | 563 | 61,689 | 49,370 |
| 10 | [newbee-ltd/newbee-mall](https://github.com/newbee-ltd/newbee-mall) | Business systems | 933 | 1,470 | 318 | 88 | 118,606 | 7,609 |
| 11 | [stylefeng/Guns](https://github.com/stylefeng/Guns) | Business systems | 1,377 | 10,042 | 406 | 18 | 60,821 | 1,210 |
| 12 | [renrenio/renren-fast](https://github.com/renrenio/renren-fast) | Business systems | 777 | 3,326 | 223 | 143 | 39,002 | 8,821 |
| 13 | [thinkgem/jeesite](https://github.com/thinkgem/jeesite) | Business systems | 2,670 | 14,623 | 845 | 0 | 92,527 | 0 |
| 14 | [o2oa/o2oa](https://github.com/o2oa/o2oa) | Business systems | 70,501 | 710,059 | 27,933 | 7,824 | 2,751,818 | 773,636 |
| 15 | [chillzhuang/SpringBlade](https://github.com/chillzhuang/SpringBlade) | Business systems | 1,073 | 3,002 | 423 | 258 | 34,554 | 17,484 |
| 16 | [dromara/dante-cloud](https://github.com/dromara/dante-cloud) | Business systems | 476 | 728 | 892 | 77 | 144,080 | 5,737 |
| 17 | [linlinjava/litemall](https://github.com/linlinjava/litemall) | Business systems | 13,172 | 34,102 | 1,591 | 333 | 227,993 | 116,435 |
| 18 | [metersphere/metersphere](https://github.com/metersphere/metersphere) | Business systems | 43,718 | 157,807 | 4,716 | 2,706 | 860,678 | 372,881 |
| 19 | [apache/dubbo](https://github.com/apache/dubbo) | Large multi-module | 34,065 | 136,879 | 4,861 | 4,060 | 524,398 | 484,107 |
| 20 | [apache/fineract](https://github.com/apache/fineract) | Large multi-module | 54,054 | 266,418 | 9,115 | 7,647 | 1,538,051 | 1,005,293 |
| 21 | [apache/rocketmq](https://github.com/apache/rocketmq) | Large multi-module | 26,486 | 109,906 | 2,805 | 2,318 | 437,047 | 401,952 |
| 22 | [alibaba/nacos](https://github.com/alibaba/nacos) | Large multi-module | 57,387 | 435,556 | 7,382 | 5,442 | 1,320,342 | 849,146 |
| 23 | [apache/shardingsphere](https://github.com/apache/shardingsphere) | Large multi-module | 56,172 | 447,822 | 17,467 | 9,916 | 1,501,418 | 836,710 |
| 24 | [spring-projects/spring-boot](https://github.com/spring-projects/spring-boot) | Large multi-module | 65,047 | 141,756 | 11,620 | 8,443 | 922,863 | 752,549 |
| 25 | [spring-projects/spring-framework](https://github.com/spring-projects/spring-framework) | Large multi-module | 105,969 | 286,288 | 11,402 | 9,244 | 1,595,393 | 1,430,520 |
| 26 | [alibaba/druid](https://github.com/alibaba/druid) | Large multi-module | 41,208 | 234,102 | 6,740 | 5,359 | 702,517 | 598,992 |
| 27 | [spring-projects/spring-petclinic](https://github.com/spring-projects/spring-petclinic) | JPA applications | 283 | 626 | 131 | 50 | 27,644 | 4,297 |
| 28 | [elunez/eladmin](https://github.com/elunez/eladmin) | JPA applications | 1,357 | 5,096 | 305 | 274 | 26,578 | 23,267 |
| 29 | [keycloak/keycloak](https://github.com/keycloak/keycloak) | JPA applications | 92,061 | 499,683 | 13,527 | 8,712 | 1,850,827 | 1,309,630 |
| 30 | [flowable/flowable-engine](https://github.com/flowable/flowable-engine) | JPA applications | 76,265 | 215,262 | 16,202 | 8,082 | 1,730,889 | 1,086,948 |
| 31 | [Activiti/Activiti](https://github.com/Activiti/Activiti) | JPA applications | 24,203 | 85,736 | 5,387 | 3,095 | 476,182 | 353,553 |
| 32 | [hibernate/hibernate-orm](https://github.com/hibernate/hibernate-orm) | JPA applications | 180,951 | 421,035 | 21,338 | 19,251 | 2,483,974 | 2,312,508 |
| 33 | [dhis2/dhis2-core](https://github.com/dhis2/dhis2-core) | JPA applications | 63,457 | 411,972 | 10,299 | 6,670 | 1,621,862 | 1,289,926 |
| 34 | [BroadleafCommerce/BroadleafCommerce](https://github.com/BroadleafCommerce/BroadleafCommerce) | JPA applications | 25,682 | 108,282 | 3,866 | 2,983 | 563,954 | 353,597 |
| 35 | [macrozheng/mall-admin-web](https://github.com/macrozheng/mall-admin-web) | Frontend projects | 1,662 | 29,228 | 358 | 0 | 36,098 | 0 |
| 36 | [yangzongzhuan/RuoYi-Vue3](https://github.com/yangzongzhuan/RuoYi-Vue3) | Frontend projects | 1,078 | 6,243 | 281 | 0 | 26,397 | 0 |
| 37 | [jeecgboot/jeecgboot-vue3](https://github.com/jeecgboot/jeecgboot-vue3) | Frontend projects | 4,755 | 25,600 | 1,424 | 0 | 173,262 | 0 |
| 38 | [pig-mesh/pig-ui](https://github.com/pig-mesh/pig-ui) | Frontend projects | 1,974 | 11,417 | 479 | 0 | 59,233 | 0 |
| 39 | [yudaocode/yudao-ui-admin-vue3](https://github.com/yudaocode/yudao-ui-admin-vue3) | Frontend projects | 16,456 | 3,065,439 | 3,274 | 0 | 509,620 | 0 |
| 40 | [elunez/eladmin-web](https://github.com/elunez/eladmin-web) | Frontend projects | 538 | 1,133 | 279 | 0 | 18,332 | 0 |
| 41 | [newbee-ltd/newbee-mall-vue3-app](https://github.com/newbee-ltd/newbee-mall-vue3-app) | Frontend projects | 181 | 382 | 59 | 0 | 10,854 | 0 |
| | **Total (41)** | | **1,171,119** | **8,348,519** | **203,848** | **125,166** | **24,913,664** | **15,710,618** |

- **Business systems (18)**: Java scaffolds and business systems: the RuoYi family, Jeecg, yudao, pig and more, plus e-commerce / office / tooling systems
- **Large multi-module (8)**: very large multi-module repositories, mostly Gradle: Apache middleware and cornerstone repos of the Spring ecosystem
- **JPA applications (8)**: JPA-shaped systems: IAM / BPM / ERP applications and hibernate-orm itself
- **Frontend projects (7)**: the official frontend repos of the business systems (Vue)

**Spread.** The systems run from 10,854 to 2,751,818 lines of code (median 173,262) and from 181 to 180,951 objects.

**What this covers, and what it does not yet.** 41 systems are not enough to stand for the open-source community as a whole. The corpus is being extended step by step, with the goal of reaching a sample proportion that is statistically meaningful. Until then, the reference lines describe this corpus.

**One link count still to be explained.** yudaocode/yudao-ui-admin-vue3 alone accounts for about 37% of all links (3,065,439 links for 16,456 objects, about 186 links per object, far above the other systems). The cause has not been attributed yet; see [docs/CORPUS.md](docs/CORPUS.md).

Source version, snapshot and per-repository detail: [docs/CORPUS.md](docs/CORPUS.md).

## How to use it

1. Connect your system's repository on [kengine.ai](https://kengine.ai).
2. The engine builds its knowledge graph and computes the measurements.
3. Compare your values with the reference lines above to see where the system sits.

Reference lines move with each rescan, so compare against the baseline date shown here.

## Where the data comes from

- **One run, one analyzer version.** All 41 systems were scanned in a single run on 2026-11-26 with the same analyzer version.
- **Every system passed the pipeline.** Scan, graph build, metric computation and the consistency step completed for 41 of 41 repositories, with 0 failed and none missing.
- **Cross-checked lines.** For giant-class share, cyclomatic complexity (P90), test-method share, giant-method share, one of the two counts behind the line was compared, system by system, with a separate filtered count from the server: 33 of 33 match on every line.
- **Lines without a cross-check yet.** circular dependency density, package dependency density are computed in one pass from the package dependency list; there is no second check for these lines yet.
- **File counts.** Compared with the server's own count for each repository: 41 of 41 match.
- **Check it yourself.** Per-repository reports, pipeline conclusions and aggregates are all in this repository (`reports/`, `pipeline-status/`, `census/`); the method is in [docs/PIPELINE.md](docs/PIPELINE.md).
- **Rescanned monthly.** The corpus is rescanned on the first day of each month (the monthly schedule starts on 2026-12-01). [This baseline's scan run](https://github.com/asdm-ai/asdm-ke-index/actions/runs/45829165719): 2026-11-26, 13:26–18:13 UTC, 4h 46m 57s.

## Scope and limits

1. **A curated selection, not a random sample.** The corpus is a tiered pick of well-known Java repositories and carries self-selection bias. The reference lines are not an industry survey or an industry benchmark.
2. **Whole-corpus only.** Each reference line covers all 33 systems together. No single type has 30 or more systems yet, so there are no per-type reference lines.
3. **Back-end Java only.** Frontend projects take part in the scale statistics only.
4. **Three systems carry little Java at their current version** (stylefeng/Guns, thinkgem/jeesite, dromara/dante-cloud), which limits how representative they are for the reference lines.
5. **Lines are physical lines**, comments and blank lines included, not SLOC. The definition is in [docs/CORPUS.md](docs/CORPUS.md).
6. **A single point in time.** The baseline is a cross-section that is refreshed with each rescan.

## License and citation

- License: [Apache License 2.0](LICENSE).
- Cite as: ASDM KE Index, baseline run #36 (`45829165719`), 2026-11-26.
- Corpus: every system is an open-source project owned by its respective authors. This repository publishes counts and metric values only and contains no source code of the corpus.
- Feedback: [Issues](https://github.com/asdm-ai/asdm-ke-index/issues).
