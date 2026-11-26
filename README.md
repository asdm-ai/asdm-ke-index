# asdm-ke-index

KE Index 开源基准库冷启动仓库——开源仓库扫描清单、扫描管线脚本、指标报告与 census 聚合产物。

> 本仓库由 AOS / KE 平台的批量扫描管线（GitHub Actions）自动维护。
> 数据落点：[kengine.ai](https://kengine.ai)；指标口径：AOS Index Metrics Schema（16 卡——A 链路 / B 结构 / C 代码 / D 技术栈）。

## 当前状态（2026-11-25 快照基线）

| 项 | 值 |
|---|---|
| 清单 / report / pipeline-status | **41 / 41 / 41** |
| 产品链路（scan → projection → metrics → consistency） | 41/41 四子步全 ok，consistency 等价比对 41 pass / 0 mismatch |
| 分析器版本 | KE CLI `0.3.10`（41 仓同质基线——数值可比） |
| 数据规模 | 对象 1,170,444 / 链接 8,343,496 |
| census | `samples=41`，`status=published`，`schemaVersion=draft-v1` |
| 可出参考线的指标（N ≥ 30） | **6 / 16**（见[指标状况](#指标状况按-16-卡如实列出)） |

全量基线由 run #33（`45617313621`）建立，run #34（`45705197312`）补齐 hibernate-orm 并重扫 4 个
上游 HEAD 已前移的仓。两轮合计零失败、零僵尸。

## 目录结构

| 路径 | 内容 |
|---|---|
| `repos.yaml` | 扫描清单（owner/repo/branch/skip/notes——notes 首字符为分层标记） |
| `.github/workflows/scan.yml` | 批量扫描 workflow（matrix，按仓穿行，`max-parallel: 1`） |
| `scripts/install-cli.sh` | 下载 KE CLI（manifest latest + sha256 对账 + 版本断言，当前锚 `0.3.10`） |
| `scripts/preflight-skip.sh` | 零漂移短路（远端 HEAD 与 report 新鲜度命中即整仓跳过） |
| `scripts/scan-one.sh` | 单仓扫描：clone → `ke import start`（默认 `--defer-projection`） |
| `scripts/compute-metrics.py` | 单仓指标计算 → `reports/{owner}/{repo}.json`（分子分母 + 指令溯源，可复算） |
| `scripts/graph-metrics.py` | 图查询形态重算 A1/C1 + 双路径等价比对（`--compare`，MISMATCH exit 2） |
| `scripts/framework-policy.json` | D1 目标版本区间策略表 |
| `scripts/pipeline-status.sh` | 四子步结论落盘 → `pipeline-status/{owner}/{repo}.json` |
| `scripts/census.py` | 聚合分位 + 穿行 validation roll-up + 矩阵对账 + 仓规模分布 → `census/summary.json` |
| `scripts/push-with-retry.sh` | bot 提交推送重试（按拒绝原因分类：non-FF 才 rebase，瞬时 5xx 退避重试） |
| `scripts/repo-scale.py` | 仓规模采集（文件数 / 行数，分语言）——扫描时 clone 后调用，口径见[仓规模口径](#仓规模口径文件数--行数) |
| `scripts/scale-backfill.py` | 存量 report 按定锚提交补采仓规模（回填 `D3.scale`，幂等） |
| `.github/workflows/scale-backfill.yml` | 仓规模一次性补齐 workflow（手动 dispatch） |
| `reports/{owner}/{repo}.json` | 单仓指标报告 |
| `pipeline-status/{owner}/{repo}.json` | 单仓链路结论（确定性产物） |
| `census/summary.json` | 聚合产物（样本清单 + 各指标分位 + validation + D2 cohort） |

## 扫描管线

每仓一个 job，job 内串行执行完整链路；任一子步不通过即该仓任务失败（`fail-fast: false` +
`max-parallel: 1`——单仓失败不级联，也不阻断尾部 census）：

```
preflight（零漂移短路）
  → ① scan         clone → import --defer-projection（仅 MySQL 落库）
  → ② projection   ke project <snapshotId>（Neo4j 投影）
  → ③ metrics      compute-metrics.py（MySQL 直查）
  → ④ consistency  graph-metrics.py --compare（图形态重算 + 双路径等价比对）
  → ⑤ annotate     pipeline-status 落盘 + 报告入库
census（聚合成功产物 + 汇总全部仓子步结论 + 与扫描矩阵对账——缺仓即判失败）
```

- **触发**：push 修改 `repos.yaml` / Actions 页手动触发（可选 `scan_force`）。月度 schedule 尚未启用（保持注释态）。
- **默认轨去重**：仓 HEAD 与 CLI 版本均未变时，preflight 直接跳过整个 job（run #34 实证：41 仓中 36 仓秒级跳过，样本数零漂移）。
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

| # | owner/repo | 分层 | Report | 快照 | 对象数 | 链接数 | 管线 |
|---|---|---|---|---|---|---|---|
| 1 | [macrozheng/mall](https://github.com/macrozheng/mall) | A | [report](reports/macrozheng/mall.json) | `3440ab25` | 14,527 | 35,226 | ✅ |
| 2 | [macrozheng/mall-swarm](https://github.com/macrozheng/mall-swarm) | A | [report](reports/macrozheng/mall-swarm.json) | `37ddc9ab` | 14,878 | 36,007 | ✅ |
| 3 | [yangzongzhuan/RuoYi-Vue](https://github.com/yangzongzhuan/RuoYi-Vue) | A | [report](reports/yangzongzhuan/RuoYi-Vue.json) | `d3415eb1` | 2,560 | 7,765 | ✅ |
| 4 | [dromara/RuoYi-Vue-Plus](https://github.com/dromara/RuoYi-Vue-Plus) | A | [report](reports/dromara/RuoYi-Vue-Plus.json) | `34aacaa5` | 4,777 | 22,903 | ✅ |
| 5 | [jeecgboot/JeecgBoot](https://github.com/jeecgboot/JeecgBoot) | A | [report](reports/jeecgboot/JeecgBoot.json) | `6cb1a82a` | 15,697 | 116,780 | ✅ |
| 6 | [lenve/vhr](https://github.com/lenve/vhr) | A | [report](reports/lenve/vhr.json) | `f2fb4546` | 991 | 1,436 | ✅ |
| 7 | [YunaiV/ruoyi-vue-pro](https://github.com/YunaiV/ruoyi-vue-pro) | A | [report](reports/YunaiV/ruoyi-vue-pro.json) | `7b0666a4` | 46,623 | 230,904 | ✅ |
| 8 | [yangzongzhuan/RuoYi-Cloud](https://github.com/yangzongzhuan/RuoYi-Cloud) | A | [report](reports/yangzongzhuan/RuoYi-Cloud.json) | `d9545f2a` | 2,532 | 8,741 | ✅ |
| 9 | [pig-mesh/pig](https://github.com/pig-mesh/pig) | A | [report](reports/pig-mesh/pig.json) | `feb1b04a` | 2,546 | 7,737 | ✅ |
| 10 | [newbee-ltd/newbee-mall](https://github.com/newbee-ltd/newbee-mall) | A | [report](reports/newbee-ltd/newbee-mall.json) | `a1b165a0` | 933 | 1,470 | ✅ |
| 11 | [stylefeng/Guns](https://github.com/stylefeng/Guns) | A ⚠️ | [report](reports/stylefeng/Guns.json) | `c75b708b` | 1,377 | 10,042 | ✅ |
| 12 | [renrenio/renren-fast](https://github.com/renrenio/renren-fast) | A | [report](reports/renrenio/renren-fast.json) | `c6105573` | 777 | 3,326 | ✅ |
| 13 | [thinkgem/jeesite](https://github.com/thinkgem/jeesite) | A ⚠️ | [report](reports/thinkgem/jeesite.json) | `b6300c52` | 2,670 | 14,623 | ✅ |
| 14 | [o2oa/o2oa](https://github.com/o2oa/o2oa) | A | [report](reports/o2oa/o2oa.json) | `569db6c6` | 70,501 | 710,059 | ✅ |
| 15 | [chillzhuang/SpringBlade](https://github.com/chillzhuang/SpringBlade) | A | [report](reports/chillzhuang/SpringBlade.json) | `8f677038` | 1,073 | 3,002 | ✅ |
| 16 | [dromara/dante-cloud](https://github.com/dromara/dante-cloud) | A ⚠️ | [report](reports/dromara/dante-cloud.json) | `cc27d728` | 476 | 728 | ✅ |
| 17 | [linlinjava/litemall](https://github.com/linlinjava/litemall) | A | [report](reports/linlinjava/litemall.json) | `35f50e65` | 13,172 | 34,102 | ✅ |
| 18 | [metersphere/metersphere](https://github.com/metersphere/metersphere) | A | [report](reports/metersphere/metersphere.json) | `9525ad71` | 43,718 | 157,807 | ✅ |
| 19 | [apache/dubbo](https://github.com/apache/dubbo) | B | [report](reports/apache/dubbo.json) | `3c195b28` | 34,065 | 136,879 | ✅ |
| 20 | [apache/fineract](https://github.com/apache/fineract) | B | [report](reports/apache/fineract.json) | `a595220d` | 53,936 | 265,882 | ✅ |
| 21 | [apache/rocketmq](https://github.com/apache/rocketmq) | B | [report](reports/apache/rocketmq.json) | `1a8a8aaf` | 26,411 | 109,365 | ✅ |
| 22 | [alibaba/nacos](https://github.com/alibaba/nacos) | B | [report](reports/alibaba/nacos.json) | `3821b9eb` | 57,376 | 433,824 | ✅ |
| 23 | [apache/shardingsphere](https://github.com/apache/shardingsphere) | B | [report](reports/apache/shardingsphere.json) | `3c9663b5` | 56,172 | 447,822 | ✅ |
| 24 | [spring-projects/spring-boot](https://github.com/spring-projects/spring-boot) | B | [report](reports/spring-projects/spring-boot.json) | `97e4378f` | 65,024 | 141,706 | ✅ |
| 25 | [spring-projects/spring-framework](https://github.com/spring-projects/spring-framework) | B | [report](reports/spring-projects/spring-framework.json) | `ad67282d` | 105,968 | 286,287 | ✅ |
| 26 | [alibaba/druid](https://github.com/alibaba/druid) | B | [report](reports/alibaba/druid.json) | `df9c2523` | 41,208 | 234,102 | ✅ |
| 27 | [spring-projects/spring-petclinic](https://github.com/spring-projects/spring-petclinic) | C | [report](reports/spring-projects/spring-petclinic.json) | `636f6857` | 283 | 626 | ✅ |
| 28 | [elunez/eladmin](https://github.com/elunez/eladmin) | C | [report](reports/elunez/eladmin.json) | `5f43da18` | 1,357 | 5,096 | ✅ |
| 29 | [keycloak/keycloak](https://github.com/keycloak/keycloak) | C | [report](reports/keycloak/keycloak.json) | `8824d864` | 91,998 | 498,423 | ✅ |
| 30 | [flowable/flowable-engine](https://github.com/flowable/flowable-engine) | C | [report](reports/flowable/flowable-engine.json) | `682bf7a1` | 76,265 | 215,262 | ✅ |
| 31 | [Activiti/Activiti](https://github.com/Activiti/Activiti) | C | [report](reports/Activiti/Activiti.json) | `b4a8661c` | 24,198 | 85,691 | ✅ |
| 32 | [hibernate/hibernate-orm](https://github.com/hibernate/hibernate-orm) | C | [report](reports/hibernate/hibernate-orm.json) | `580817a3` | 180,572 | 420,177 | ✅ |
| 33 | [dhis2/dhis2-core](https://github.com/dhis2/dhis2-core) | C | [report](reports/dhis2/dhis2-core.json) | `d3c20ab4` | 63,457 | 411,972 | ✅ |
| 34 | [BroadleafCommerce/BroadleafCommerce](https://github.com/BroadleafCommerce/BroadleafCommerce) | C | [report](reports/BroadleafCommerce/BroadleafCommerce.json) | `f2964888` | 25,682 | 108,282 | ✅ |
| 35 | [macrozheng/mall-admin-web](https://github.com/macrozheng/mall-admin-web) | D | [report](reports/macrozheng/mall-admin-web.json) | `b61b793d` | 1,662 | 29,228 | ✅ |
| 36 | [yangzongzhuan/RuoYi-Vue3](https://github.com/yangzongzhuan/RuoYi-Vue3) | D | [report](reports/yangzongzhuan/RuoYi-Vue3.json) | `fbc90f26` | 1,078 | 6,243 | ✅ |
| 37 | [jeecgboot/jeecgboot-vue3](https://github.com/jeecgboot/jeecgboot-vue3) | D | [report](reports/jeecgboot/jeecgboot-vue3.json) | `896b3950` | 4,755 | 25,600 | ✅ |
| 38 | [pig-mesh/pig-ui](https://github.com/pig-mesh/pig-ui) | D | [report](reports/pig-mesh/pig-ui.json) | `1f9ae681` | 1,974 | 11,417 | ✅ |
| 39 | [yudaocode/yudao-ui-admin-vue3](https://github.com/yudaocode/yudao-ui-admin-vue3) | D | [report](reports/yudaocode/yudao-ui-admin-vue3.json) | `e260a772` | 16,456 | 3,065,439 | ✅ |
| 40 | [elunez/eladmin-web](https://github.com/elunez/eladmin-web) | D | [report](reports/elunez/eladmin-web.json) | `6d998bf1` | 538 | 1,133 | ✅ |
| 41 | [newbee-ltd/newbee-mall-vue3-app](https://github.com/newbee-ltd/newbee-mall-vue3-app) | D | [report](reports/newbee-ltd/newbee-mall-vue3-app.json) | `c770e3d8` | 181 | 382 | ✅ |

> ⚠️ **分层漂移**：Guns / jeesite / dante-cloud 在被扫描的 HEAD 上已不是选样时假设的 Java 后端形态
> （`.java` 文件分别只有 18 / 0 / 77 个；其中 Guns 与 jeesite 的 `.vue` 文件分别为 163 / 301 个，实为前端形态）。三仓仍计入 A 层 18 仓，但
> 其 Java 侧指标（A3/A4、B、C 域）样本代表性有限。

### 仓规模口径（文件数 / 行数）

仓规模在扫描的同时采集（`scan-one.sh` clone 之后、import 之前，同一工作树同一 HEAD），落 `report.metrics.D3.scale`，
并在 `census/summary.json` 给出逐仓字段（`repos[]`）与跨仓分布（`cohort.scale`）。作为各指标的规模参照，不参与评分。

| 字段 | 口径 |
|---|---|
| 文件数 `fileCount` | tracked 文件数，剔除分析器跳过目录（`target` / `build` / `dist` / `node_modules` 等）与符号链接等非普通文件；与分析器 `Repository.fileCount` 同口径，扫描时逐仓对照（不一致只告警不置红） |
| Java 文件 `javaFiles` | 其中 `.java` 文件数 |
| 总行数 `lineCount` | 文本文件的物理行数，含注释与空行，**不是 SLOC**；二进制文件（首 8000 字节含 NUL）不计 |
| Java 行数 `javaLines` | 其中 `.java` 文件的物理行数 |

- **规模参照以 Java 行数为主指标。** 总行数会被设计文档、SVG、生成物显著抬高（mall 的总行数里有 4.1 万行来自 `.pdb` / `.pdm` 设计文件）。
- 分语言明细（`linesByLanguage` / `filesByLanguage`）随 report 一并给出。
- 2026-11-26 之前落库的 report 由 `scale-backfill` workflow 按同一提交补采，数值与扫描时采集等价（`collectedBy: "backfill"`）。

## 指标状况（按 16 卡如实列出）

分位为全体切片的 nearest-rank 值（取自 `census/summary.json`）。**状态列是本表的重点**——N 为该指标
实际可算的仓数，只有 N ≥ 30 的切片具备出参考线的统计充分性。

| 指标 | 名称 | 方向 | N | 缺失 | P25 | P50 | P75 | 状态 |
|---|---|---|---|---|---|---|---|---|
| A1 | 全链路贯通率 | 越高越好 | 18 | 23 | 0 | 0 | 0 | ⚠️ 未达门槛，分布退化 |
| A2 | 前后端断链率 | 越低越好 | 18 | 23 | 1 | 1 | 1 | ⚠️ 未达门槛，分布退化 |
| A3 | 孤儿表率 | 越低越好 | 29 | 12 | 0.21 | 0.5362 | 0.9806 | ⚠️ 未达门槛（差 1 仓） |
| A4 | 表↔实体映射率 | 越高越好 | 29 | 12 | 0.0194 | 0.4638 | 0.79 | ⚠️ 未达门槛（差 1 仓） |
| B1.backend | 循环依赖密度（后端） | 越低越好 | 33 | 8 | 0.0909 | 0.2126 | 0.4223 | ✅ 可出参考线 |
| B1.frontend | 循环依赖密度（前端） | 越低越好 | 27 | 14 | 0 | 0 | 0.003 | ⚠️ 未达门槛（差 3 仓） |
| B2 | 包依赖密度 | 区间型 | 33 | 8 | 2.3617 | 4.6335 | 7.6072 | ✅ 可出参考线 |
| B3 | 巨型类占比 | 越低越好 | 33 | 8 | 0.0062 | 0.0253 | 0.0357 | ✅ 可出参考线 |
| B4 | 组件耦合度 | 越低越好 | 17 | 24 | 0.0503 | 0.2294 | 0.3462 | ⚠️ 未达门槛 |
| C1 | 端到端跳数 | 区间型 | 1 | 40 | — | — | — | ⛔ 无分位（k-匿名 N<5） |
| C2 | 圈复杂度 P90 | 越低越好 | 33 | 8 | 2 | 3 | 3 | ✅ 可出参考线 |
| C3 | 测试方法占比 | 越高越好 | 33 | 8 | 0.0043 | 0.0397 | 0.1662 | ✅ 可出参考线 |
| C4 | 巨型方法占比 | 越低越好 | 33 | 8 | 0.0014 | 0.003 | 0.0073 | ✅ 可出参考线 |
| D1 | 技术栈版本覆盖率 | 越高越好 | 6 | 35 | 0.5 | 0.5 | 1 | ❌ 值待修正，不可用 |
| D2 | 依赖同质度 | 描述性 | cohort | — | 值 0.375 | | | ❌ 值待修正，不可用 |
| D3 | 规模画像 | 描述性 | 41 | 0 | 对象数 181 | 14,527 | 180,572 | ℹ️ 描述性统计 |
| D4 | 年度演进趋势 | 描述性 | 4 | 37 | — | — | — | ⛔ 无时序（非年度间隔） |

### 逐指标说明

**A 域（链路）**

- **A1 / A2 / C1**：`ApiEndpoint` 是前端调用点对象，纯后端仓不产出该类型——23 仓置空属口径性缺失，不是扫描失败。
  但这意味着这三个指标只在"同一快照内前端调用点与配对后端并存"时可算，当前样本下无法形成参考线：
  - 18 个有值仓中，7 个是 D 层独立扫描的前端（同快照内没有配对后端，A1 恒为 0、A2 恒为 1）；
  - 其余 11 仓中仅 lenve/vhr 为 A1 = 1.0（分母只有 1 个端点），另 10 仓为 0，端点数为 1–123；
  - C1 只有 1 个仓有值，另 17 仓有端点但无贯通链。
- **A3 / A4**：N=29，距门槛差 1 仓。12 个缺失仓中 7 个是前端，5 个是后端（BroadleafCommerce / dubbo / jeesite / keycloak / o2oa）——
  这些仓的 DDL 不在可解析的内联 `.sql` 文件中，因此无 `Table` 对象。29 个有值仓里 7 个 A3 = 1.0（表全部为孤儿）、4 个 A3 = 0，
  分布明显双峰，P25–P75 区间很宽。

**B 域（结构）**

- **B1.backend / B2 / B3**：N=33，当前最可靠的一组。缺失 8 仓 = 7 个 D 层前端 + jeesite（无 `Package` / `Class` 对象）。
- **B1.frontend**：N=27，差 3 仓。
- **B4**：N=17，仅含组件对象的仓可算。

**C 域（代码）**

- **C2 / C3 / C4**：N=33，与 B 域后端口径一致。

**D 域（技术栈）**

- **D1**：仅 6 仓有值，且值不可用。Maven 多模块仓的依赖版本大多由父 POM 继承，抽取结果是空串或属性占位符
  （`${...}` / `@x@`）——6 个有值仓的分子分母只有 1–7 条依赖；`@x@` 形式的占位符还会被当作可判定版本并计入"超范围"
  （spring-boot 自身因此得到 D1 = 0.0）。
- **D2**：cohort 值 0.375 不可用——各框架可用仓数只有 1–5 个（mybatis 1 / spring-framework 2 / spring-boot 3 / druid 5 / mysql-connector-j 5），
  且部分"众数版本"本身是占位符串。
- **D3**：41 仓全量可描述。对象数 181–180,572（中位 14,527），链接数 382–3,065,439（中位 35,226）。
- **D4**：仅 4 仓有值，且来自 run #33 与 run #34 相隔数小时的两个快照——能验证计算逻辑，但不构成年度趋势。
  需要月度重扫启用后积累多期数据。

## census 守门状态

| 项 | 值 |
|---|---|
| 已收录样本 | **41** |
| 发布门槛（统计充分性） | 总样本 N ≥ 30 → `published`（当前 N=41） |
| 隐私护栏（k-匿名单指标级） | 切片 N < 5 整组不出分位 |
| 当前状态 | `published`，`schemaVersion=draft-v1` |
| validation | 41/41 四子步 ok；consistency pass 41 / mismatch 0；与扫描矩阵对账 missing 0 |

> **阅读提示**：`census.py` 目前把 30 的门槛作用在**总样本**上，各指标切片只施 k-匿名护栏（N ≥ 5 即出分位）。
> "每个切片独立 N ≥ 30 才出参考线"的门槛尚未实现，所以 `summary.json` 里 N = 6 / 17 / 18 的切片也带分位值。
> 引用数值时请以上表状态列为准。

## 已知限制

1. **分层切片与体质分当前不可得。** 分层为 A18 / B8 / C8 / D7，各层都低于 30；总量 41 也低于体质分要求的 50。
   现阶段只有全体切片具备统计充分性。
2. **A1 / A2 / C1 依赖前后端配对聚合。** 配对聚合尚未启用，D 层前端按独立仓入列。
3. **D1 / D2 依赖 Maven 版本继承解析。** 平台侧暂不解析父 POM 管理的版本。
4. **consistency 的覆盖面有限。** 无 `ApiEndpoint` 的仓会跳过图形态比对（23 仓），41 个 pass 中实际执行双路径等价比对的不超过 18 仓。
5. **个别仓的数值待归因。** yudao-ui-admin-vue3 链接数 3,065,439（约 186 条/对象，远高于其它仓）；dhis2-core 的 A4 仅 0.0275。
6. **三仓分层漂移**（见仓库索引的 ⚠️ 标注）。

## 披露

- 本清单为分层选样的知名 Java 仓库，**非随机抽样**——存在自选择偏差，分位参考线不代表行业普查结果。
- report 仅含聚合计数与指标值，不含源码字符串内容；对外只发布聚合分位，单仓指标值不单独发布。
