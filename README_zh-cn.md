# asdm-ke-index

[English](README.md) | 简体中文

KE Index 开源基准库冷启动仓库——开源仓库扫描清单、扫描管线脚本、指标报告与 census 聚合产物。

> 本仓库由 AOS / KE 平台的批量扫描管线（GitHub Actions）自动维护。  
> 数据落点：[kengine.ai](https://kengine.ai)；指标口径：AOS Index Metrics Schema（16 卡——A 链路 / B 结构 / C 代码 / D 技术栈）。

## 当前状态（2026-11-26 全量基线）

| 项 | 值 |
|---|---|
| 清单 / report / pipeline-status | **41 / 41 / 41** |
| 产品链路（scan → projection → metrics → consistency） | 41/41 四子步全 ok，consistency 等价比对 41 pass / 0 mismatch；链路 overall 41 / 41 pass |
| 分析器版本 | KE CLI `0.3.10`（41 仓同质基线——数值可比） |
| 数据规模 | 对象 1,171,119 / 链接 8,348,519 |
| 仓规模（文件数 / 行数） | 41/41 report 均有采集；文件数与服务端 `Repository.fileCount` 对照 **41 / 41 一致**；Java 行数 P50 85,434 / P90 1,086,948（见[仓规模](#仓规模文件数--行数)） |
| census | `samples=41`，`status=published`，`schemaVersion=draft-v1` |
| 可出参考线的指标（N ≥ 30） | **6 / 16**（见[指标状况](#指标状况按-16-卡如实列出)） |

全量基线由 run #36（`45829165719`）重建：数据全量清空后手动 dispatch 的整库重扫，41 仓全部按上游 HEAD 重新克隆扫描（preflight 零跳过）；零失败、零僵尸快照。

运行窗口：2026-11-26T13:26:27Z → 2026-11-26T18:13:24Z UTC（4h 46m 57s）；链路失败仓 0 个。

## 目录结构

| 路径 | 内容 |
|---|---|
| `repos.yaml` | 扫描清单（owner/repo/branch/skip/notes——notes 首字符为分层标记） |
| `.github/workflows/scan.yml` | 批量扫描 workflow（matrix，按仓穿行，`max-parallel: 1`） |
| `scripts/install-cli.sh` | 下载 KE CLI（manifest latest + sha256 对账 + 版本断言，当前锚 `0.3.10`） |
| `scripts/preflight-skip.sh` | 零漂移短路（远端 HEAD 与 report 新鲜度命中即整仓跳过） |
| `scripts/scan-one.sh` | 单仓扫描：clone → `ke import start`（默认 `--defer-projection`） |
| `scripts/repo-scale.py` | 仓规模采集（文件数 / 行数，分语言）——clone 之后、import 之前调用 |
| `scripts/compute-metrics.py` | 单仓指标计算 → `reports/{owner}/{repo}.json`（分子分母 + 指令溯源，可复算） |
| `scripts/graph-metrics.py` | 图查询形态重算 A1/C1 + 双路径等价比对（`--compare`，MISMATCH exit 2） |
| `scripts/framework-policy.json` | D1 目标版本区间策略表 |
| `scripts/pipeline-status.sh` | 四子步结论落盘 → `pipeline-status/{owner}/{repo}.json` |
| `scripts/census.py` | 聚合分位 + 穿行 validation roll-up + 矩阵对账 + 仓规模分布 → `census/summary.json` |
| `scripts/push-with-retry.sh` | bot 提交推送重试（按拒绝原因分类：non-FF 才 rebase，瞬时 5xx 退避重试） |
| `scripts/scale-backfill.py`、`.github/workflows/scale-backfill.yml` | 存量 report 按定锚提交补采仓规模（幂等，手动 dispatch） |
| `reports/{owner}/{repo}.json` | 单仓指标报告 |
| `pipeline-status/{owner}/{repo}.json` | 单仓链路结论（确定性产物） |
| `census/summary.json` | 聚合产物（样本清单 + 各指标分位 + validation + D2 cohort + 仓规模分布） |

## 扫描管线

每仓一个 job，job 内串行执行完整链路；任一子步不通过即该仓任务失败（`fail-fast: false` + `max-parallel: 1`——单仓失败不级联，也不阻断尾部 census）：

```
preflight（零漂移短路）
  → ① scan         clone → import --defer-projection（仅 MySQL 落库）
  → ② projection   ke project <snapshotId>（Neo4j 投影）
  → ③ metrics      compute-metrics.py（MySQL 直查）
  → ④ consistency  graph-metrics.py --compare（图形态重算 + 双路径等价比对）
  → ⑤ annotate     pipeline-status 落盘 + 报告入库
census（聚合成功产物 + 汇总全部仓子步结论 + 与扫描矩阵对账——缺仓即判失败）
```

- **触发**：push 修改 `repos.yaml` / Actions 页手动触发（可选 `scan_force`）/ 月度 schedule `0 2 1 * *`（首次 2026-12-01）。run 级 `concurrency` 让三触发面互斥。
- **默认轨去重**：仓 HEAD 与 CLI 版本均未变时，preflight 直接跳过整个 job。
- **并发护栏**：`max-parallel: 1` 单仓串行，投影天然独占窗口。

## 复现说明

```bash
# 1. 安装 KE CLI（manifest latest + sha256 对账 + 版本断言）
KE_API_KEY=<member key> bash scripts/install-cli.sh /tmp/ke-cli

# 2. 单仓扫描（clone --depth 1 → ke import start 三段上传直连）
OWNER=macrozheng REPO=mall CLI_DIR=/tmp/ke-cli \
KE_API_KEY=<member key> KE_SERVER_URL=https://console.kengine.ai \
bash scripts/scan-one.sh
# 步骤末行为导入 summary JSON（ok / status / snapshotId / objectCount）——失败 exit 1
```

- 对账：Action 步骤末行 `objectCount` 与平台快照列表逐位对照；仓级 report 与 pipeline-status 的 snapshotId / objectCount / sourceHead 三者一致。

### 重扫轨说明（分析器版本升级后的口径修正重扫）

仓 HEAD 不变时，`ke import start` 撞已 complete 的快照会 **dedup skipped**（静默跳过——月度重扫的正确去重行为，但会吞掉分析器升级带来的口径修正）。因此**分析器版本升级后的重扫必须走 force 轨**（Actions 页手动触发时勾选 `scan_force`，或本地 `SCAN_FORCE=true`）：

```bash
SCAN_FORCE=true OWNER=dromara REPO=RuoYi-Vue-Plus CLI_DIR=/tmp/ke-cli \
KE_API_KEY=<member key> KE_SERVER_URL=https://console.kengine.ai \
bash scripts/scan-one.sh
```

- 判别：force 轨 summary `status == "completed"`（重建）；默认轨同 HEAD 为 `"skipped"`（数值不变）
- 口径分界：force 重扫 commit 即口径前后的自然分界（git 历史可追溯）

## 仓库索引（41 仓）

### 分层构成

| 分层 | 数量 | 形态说明 |
|---|---|---|
| A·admin/业务系统 | 18 | Java 脚手架与业务系统（MyBatis/MP/JPA 混合形态——RuoYi 系/Jeecg/芋道/Pig 等多脚手架对照 + 电商/办公/工具型业务系统） |
| B·大型仓 | 8 | 超大型多模块（Gradle 轨为主——Apache 系中间件 + Spring 生态基石仓） |
| C·JPA 数据访问层 | 8 | JPA 形态（与 MyBatis 系对照——IAM/BPM/ERP 业务侧 + hibernate-orm 实现本体） |
| D·前后端配对 | 7 | A 层仓的官方前端仓（Vue 系——**配对聚合未启用，按独立前端形态入列**） |

> 全量清单见 [repos.yaml](repos.yaml)。快照 ID 截取前 8 位（完整值见 `census/summary.json` 的 repos 区——机器可读源）。

### 全部仓库

| # | owner/repo | 分层 | Report | 快照 | 对象数 | 链接数 | 文件数 | Java 文件 | 行数 | Java 行数 | 管线 |
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

> ⚠️ **分层漂移**：3 个 A 层仓被扫描的 HEAD 上 `.java` 已不是最大的文件类别（stylefeng/Guns（18 个 `.java` 对 163 个 `.vue`）；thinkgem/jeesite（0 个 `.java` 对 409 个 `.typescript`）；dromara/dante-cloud（77 个 `.java` 对 637 个 `.sql`））。这些仓仍计入 A 层 18 仓，但其 Java 侧指标（A3/A4、B、C 域）样本代表性有限。

## 仓规模（文件数 / 行数）

仓规模在扫描的同时采集（`scan-one.sh` clone 之后、import 之前，同一工作树同一 HEAD），由 `scripts/repo-scale.py` 完成。它落在各 report 的 `report.metrics.D3.scale`，并在 `census/summary.json` 给出逐仓字段（`repos[]`）与跨仓分布（`cohort.scale`）。作为各指标的规模参照，不参与评分。

### 口径

| 字段 | 口径 |
|---|---|
| 文件数 `fileCount` | tracked 文件数，剔除分析器跳过目录（`target` / `build` / `dist` / `node_modules` 等）与符号链接等非普通文件；与分析器 `Repository.fileCount` 同口径，扫描时逐仓对照（不一致只告警不置红） |
| Java 文件 `javaFiles` | 其中 `.java` 文件数 |
| 总行数 `lineCount` | 文本文件的物理行数，含注释与空行，**不是 SLOC**；二进制文件（首 8000 字节含 NUL）不计 |
| Java 行数 `javaLines` | 其中 `.java` 文件的物理行数 |

### 全库合计

| 指标 | 全部仓合计 | 最小仓 | 最大仓 |
|---|---|---|---|
| 文件数 | 203,848 | 59 | 27,933 |
| Java 文件数 | 125,166 | 0 | 19,251 |
| 总行数 | 24,913,664 | 10,854 | 2,751,818 |
| Java 行数 | 15,710,618 | 0 | 2,312,508 |

Java 占全部计入行数的 63.1%、计入文件数的 61.4%。41 个仓在 git 中共有 204,788 个 tracked 文件（计入文本 185,807 个，判定为二进制并跳过 18,041 个）。采集方式：`scan`。

### 跨仓分布

| 指标 | N | 缺失 | Min | P25 | P50 | P75 | P90 | Max | 合计 | 均值 |
|---|---|---|---|---|---|---|---|---|---|---|
| 文件数 `fileCount` | 41 | 0 | 59 | 406 | 1,424 | 7,382 | 13,527 | 27,933 | 203,848 | 4,972 |
| Java 文件 `javaFiles` | 41 | 0 | 0 | 77 | 533 | 5,442 | 8,443 | 19,251 | 125,166 | 3,053 |
| 总行数 `lineCount` | 41 | 0 | 10,854 | 43,949 | 173,262 | 922,863 | 1,621,862 | 2,751,818 | 24,913,664 | 607,650 |
| Java 行数 `javaLines` | 41 | 0 | 0 | 5,581 | 85,434 | 752,549 | 1,086,948 | 2,312,508 | 15,710,618 | 383,186 |

分位取自 `census/summary.json`，为 nearest-rank 值。

### 分层对照

| 分层 | 仓数 | 文件数中位 | 行数中位 | Java 行数中位 | Java 行数合计 |
|---|---|---|---|---|---|
| A·admin/业务系统 | 18 | 749 | 116,300 | 41,851 | 2,617,623 |
| B·大型仓 | 8 | 8,248 | 1,121,602 | 794,629 | 6,359,269 |
| C·JPA 数据访问层 | 8 | 7,843 | 1,092,908 | 720,272 | 6,733,726 |
| D·前后端配对 | 7 | 358 | 36,098 | 0 | 0 |

### 规模最大的仓

按 Java 行数：

| 仓库 | Java 行数 | 总行数 | Java 文件 | 文件数 |
|---|---|---|---|---|
| [hibernate/hibernate-orm](https://github.com/hibernate/hibernate-orm) | 2,312,508 | 2,483,974 | 19,251 | 21,338 |
| [spring-projects/spring-framework](https://github.com/spring-projects/spring-framework) | 1,430,520 | 1,595,393 | 9,244 | 11,402 |
| [keycloak/keycloak](https://github.com/keycloak/keycloak) | 1,309,630 | 1,850,827 | 8,712 | 13,527 |
| [dhis2/dhis2-core](https://github.com/dhis2/dhis2-core) | 1,289,926 | 1,621,862 | 6,670 | 10,299 |
| [flowable/flowable-engine](https://github.com/flowable/flowable-engine) | 1,086,948 | 1,730,889 | 8,082 | 16,202 |

按总行数：

| 仓库 | 总行数 | Java 行数 | Java 文件 | 文件数 |
|---|---|---|---|---|
| [o2oa/o2oa](https://github.com/o2oa/o2oa) | 2,751,818 | 773,636 | 7,824 | 27,933 |
| [hibernate/hibernate-orm](https://github.com/hibernate/hibernate-orm) | 2,483,974 | 2,312,508 | 19,251 | 21,338 |
| [keycloak/keycloak](https://github.com/keycloak/keycloak) | 1,850,827 | 1,309,630 | 8,712 | 13,527 |
| [flowable/flowable-engine](https://github.com/flowable/flowable-engine) | 1,730,889 | 1,086,948 | 8,082 | 16,202 |
| [dhis2/dhis2-core](https://github.com/dhis2/dhis2-core) | 1,621,862 | 1,289,926 | 6,670 | 10,299 |

### 分语言行数

| 语言（按扩展名） | 行数 | 占比 | 文件数 |
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
| 其余 11 类 | 1,256,137 | 5.0% | 8,044 |

- **规模参照以 Java 行数为主指标。** 总行数会被设计文档、SVG、生成物显著抬高（mall 的 `other` 类——未识别扩展名，这里主要是 `.pdb` / `.pdm` 设计文件——就有 41,854 行）。
- 分语言明细（`linesByLanguage` / `filesByLanguage`）随 report 一并给出。

## 指标状况（按 16 卡如实列出）

分位为各指标自身切片的 nearest-rank 值（取自 `census/summary.json`）。**状态列是本表的重点**——N 为该指标实际可算的仓数，只有 N ≥ 30 的切片具备出参考线的统计充分性。

| 指标 | 名称 | 方向 | N | 缺失 | P25 | P50 | P75 | 状态 |
|---|---|---|---|---|---|---|---|---|
| A1 | 全链路贯通率 | 越高越好 | 18 | 23 | 0 | 0 | 0 | ⚠️ 未达门槛（差 12 仓），分布退化 |
| A2 | 前后端断链率 | 越低越好 | 18 | 23 | 1 | 1 | 1 | ⚠️ 未达门槛（差 12 仓），分布退化 |
| A3 | 孤儿表率 | 越低越好 | 29 | 12 | 0.21 | 0.5362 | 0.9806 | ⚠️ 未达门槛（差 1 仓） |
| A4 | 表↔实体映射率 | 越高越好 | 29 | 12 | 0.0194 | 0.4638 | 0.79 | ⚠️ 未达门槛（差 1 仓） |
| B1.backend | 循环依赖密度（后端） | 越低越好 | 33 | 8 | 0.0909 | 0.2126 | 0.4223 | ✅ 可出参考线 |
| B1.frontend | 循环依赖密度（前端） | 越低越好 | 27 | 14 | 0 | 0 | 0.003 | ⚠️ 未达门槛（差 3 仓） |
| B2 | 包依赖密度 | 越低越好 | 33 | 8 | 2.3617 | 4.6343 | 7.6102 | ✅ 可出参考线 |
| B3 | 巨型类占比 | 越低越好 | 33 | 8 | 0.0062 | 0.0253 | 0.0356 | ✅ 可出参考线 |
| B4 | 组件耦合度 | 越低越好 | 17 | 24 | 0.0503 | 0.2294 | 0.3462 | ⚠️ 未达门槛（差 13 仓） |
| C1 | 端到端跳数 | 区间型 | 1 | 40 | — | — | — | ⛔ 无分位（k-匿名 N<5） |
| C2 | 圈复杂度 P90 | 越低越好 | 33 | 8 | 2 | 3 | 3 | ✅ 可出参考线 |
| C3 | 测试方法占比 | 越高越好 | 33 | 8 | 0.0043 | 0.0397 | 0.1672 | ✅ 可出参考线 |
| C4 | 巨型方法占比 | 越低越好 | 33 | 8 | 0.0014 | 0.003 | 0.0073 | ✅ 可出参考线 |
| D1 | 技术栈版本覆盖率 | 越高越好 | 6 | 35 | 0.5 | 0.5 | 1 | ❌ 值待修正，不可用 |
| D2 | 依赖同质度 | 描述性 | cohort | — | — | value 0.375 | — | ❌ 值待修正，不可用 |
| D3 | 规模画像 | 描述性 | 41 | 0 | objects 181 | 14,527 | 180,951 | ℹ️ 描述性统计 |
| D4 | 年度演进趋势 | 描述性 | 0 | 41 | — | — | — | ⛔ 无时序（各仓仅单次快照） |

B1 分后端 / 前端两行，16 卡共 17 行。

### 逐指标说明

**A 域（链路）**

- **A1 / A2 / C1**：`ApiEndpoint` 是前端调用点对象，纯后端仓不产出该类型——23 仓置空属口径性缺失，不是扫描失败。因此这三个指标只在“同一快照内前端调用点与配对后端并存”时可算，当前样本下无法形成参考线：
  - 18 个有值仓中，7 个是 D 层独立前端（同快照内没有配对后端，A1 恒为 0、A2 恒为 1）；
  - 其余 11 仓中仅 lenve/vhr 达到 A1 = 1.0（分母 1 个端点）；另 10 仓为 0，端点数 1–123；
  - C1 只有 1 个仓有值，另 17 个有端点的仓无贯通链。
- **A3 / A4**：N = 29。12 个缺失仓中 7 个是前端，5 个是后端（thinkgem/jeesite, o2oa/o2oa, apache/dubbo, keycloak/keycloak 与 BroadleafCommerce/BroadleafCommerce）——这些仓的 DDL 不在可解析的内联 `.sql` 文件中，因此无 `Table` 对象。29 个有值仓里 7 个 A3 = 1.0（表全部为孤儿）、4 个为 0，分布明显双峰，P25–P75 区间很宽。

**B 域（结构）**

- **B1.backend / B2 / B3**：N = 33，当前最可靠的一组。缺失 8 仓 = 7 个 D 层前端 + thinkgem/jeesite（无 `Package` / `Class` 对象）。
- **B1.frontend**：N = 27。
- **B4**：N = 17，仅含组件对象的仓可算。

**C 域（代码）**

- **C2 / C3 / C4**：N = 33，与 B 域后端口径一致。

**D 域（技术栈）**

- **D1**：仅 6 仓有值，且值不可用。Maven 多模块仓的依赖版本大多由父 POM 继承，抽取结果是空串或属性占位符（`${...}` / `@x@`）——6 个有值仓的分子分母只有 1–7 条依赖，且 `@x@` 形式的占位符还会被当作可判定版本并计入“超范围”（spring-boot 自身因此得到 D1 = 0）。
- **D2**：cohort 值 0.375 不可用——各框架可用仓数只有 1–5 个，且其中 2 个框架的“众数版本”本身是占位符串。

| 框架 | 使用仓数 | 不同版本数 | 众数版本 | 众数占比 |
|---|---|---|---|---|
| druid | 5 | 5 | `${druid.version}` | 20.0% |
| mybatis | 1 | 1 | `3.4.0` | 100.0% |
| mysql-connector-j | 5 | 4 | `8.0.33` | 40.0% |
| spring-boot | 3 | 3 | `${springboot2.version}` | 33.3% |
| spring-framework | 2 | 2 | `6.1.21` | 50.0% |

- **D3**：41 仓全量可描述。对象数 181–180,951（中位 14,527），链接数 382–3,065,439（中位 35,226）。
- **D4**：0 个仓有值。年度演进趋势需要多期数据，月度重扫积累数轮之后才有意义。

## census 守门状态

| 项 | 值 |
|---|---|
| 已收录样本 | **41** |
| 发布门槛（统计充分性） | 总样本 N ≥ 30 → `published`（当前 N=41） |
| 隐私护栏（k-匿名单指标级） | 切片 N < 5 整组不出分位 |
| 当前状态 | `published`，`schemaVersion=draft-v1` |
| validation | 41/41 四子步 ok；consistency pass 41 / mismatch 0；与扫描矩阵对账 missing 0 |

> **阅读提示**：`census.py` 目前把 30 的门槛作用在**总样本**上，各指标切片只施 k-匿名护栏（N ≥ 5 即出分位）。“每个切片独立 N ≥ 30 才出参考线”的门槛尚未实现，所以 `summary.json` 里 N 较小的切片也带分位值。引用数值时请以上表状态列为准。

## 已知限制

1. **分层切片与体质分当前不可得。** 分层为 A18 / B8 / C8 / D7，各层都低于 30；总量 41 也低于体质分要求的 50。现阶段只有全体切片具备统计充分性。
2. **A1 / A2 / C1 依赖前后端配对聚合。** 配对聚合尚未启用，D 层前端按独立仓入列。
3. **D1 / D2 依赖 Maven 版本继承解析。** 平台侧暂不解析父 POM 管理的版本。
4. **consistency 的覆盖面有限。** 无 `ApiEndpoint` 的仓会跳过图形态比对（23 仓），41 个 pass 中实际执行双路径等价比对的不超过 18 仓。
5. **个别仓的数值待归因。** yudaocode/yudao-ui-admin-vue3 链接数 3,065,439（16,456 个对象，约 186 条/对象，远高于其它仓）；dhis2-core 的 A4 仅 0.0275。
6. **3 仓分层漂移**（见仓库索引的 ⚠️ 标注）。

## 披露

- 本清单为分层选样的知名 Java 仓库，**非随机抽样**——存在自选择偏差，分位参考线不代表行业普查结果。
- report 仅含聚合计数与指标值，不含源码字符串内容；对外只发布聚合分位，单仓指标值不单独发布。

