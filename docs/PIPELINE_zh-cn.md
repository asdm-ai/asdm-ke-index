# 数据怎么来的

[English](PIPELINE.md) | 简体中文

[参考线](../README_zh-cn.md)背后的 41 个系统是如何被扫描、度量和复核的。当前基线：run #36（`45829165719`），2026-11-26T13:26:27Z 至 2026-11-26T18:13:24Z UTC（4h 46m 57s）。

## 目录结构

| 路径 | 内容 |
|---|---|
| `repos.yaml` | 扫描清单（owner/repo/branch/skip/notes，notes 首字符为分层字母） |
| `.github/workflows/scan.yml` | 批量扫描 workflow（matrix，按仓穿行，`max-parallel: 1`） |
| `scripts/install-cli.sh` | 下载 KE CLI（manifest latest + sha256 对账 + 版本断言，当前锚 `0.3.10`） |
| `scripts/preflight-skip.sh` | 零漂移短路（远端 HEAD 与 report 新鲜度命中即整仓跳过） |
| `scripts/scan-one.sh` | 单仓扫描：clone 后 `ke import start`（默认 `--defer-projection`） |
| `scripts/repo-scale.py` | 仓规模采集（文件数 / 行数，分语言），clone 之后立即执行 |
| `scripts/compute-metrics.py` | 单仓指标计算，产出 `reports/{owner}/{repo}.json`（分子分母与溯源信息，可复算） |
| `scripts/graph-metrics.py` | 链路类指标的图形态重算与双路径等价比对（`--compare`，MISMATCH exit 2） |
| `scripts/pipeline-status.sh` | 四个子步的结论落盘到 `pipeline-status/{owner}/{repo}.json` |
| `scripts/census.py` | 聚合分位、逐仓管线校验、矩阵对账与规模分布，产出 `census/summary.json` |
| `scripts/push-with-retry.sh` | bot 提交推送重试（仅在 non-FF 时 rebase，瞬时 5xx 退避重试） |
| `scripts/scale-backfill.py`、`.github/workflows/scale-backfill.yml` | 存量 report 按定锚提交补采仓规模（幂等，手动 dispatch） |
| `reports/{owner}/{repo}.json` | 单仓报告 |
| `pipeline-status/{owner}/{repo}.json` | 单仓管线结论 |
| `census/summary.json` | 聚合产物：样本清单、各指标分位、validation、cohort、规模分布 |

## 扫描管线

每仓一个 job，job 内串行执行完整链路；任一子步不通过即该仓任务失败（`fail-fast: false` + `max-parallel: 1`：单仓失败不级联，也不阻断尾部 census）。

```
preflight（零漂移短路）
  1. scan         clone 后 import --defer-projection（仅 MySQL 落库）
  2. projection   ke project <snapshotId>（Neo4j 投影）
  3. metrics      compute-metrics.py（MySQL 直查）
  4. consistency   graph-metrics.py --compare（仅链路类指标：图形态重算 + 双路径等价比对）
  5. annotate     pipeline-status 落盘 + 报告入库
census           聚合成功产物，汇总全部仓子步结论，并与扫描矩阵对账
```

- **触发**：push 修改 `repos.yaml`、Actions 页手动触发（可选 `scan_force`）、月度 schedule `0 2 1 * *`（首次 2026-12-01）。run 级 `concurrency` 让三触发面互斥。
- **默认轨去重**：仓 HEAD 与 CLI 版本均未变时，preflight 直接跳过整个 job。
- **并发护栏**：`max-parallel: 1` 单仓串行，投影天然独占窗口。

## 核对了什么、没核对什么

- **管线子步。**四个子步 41/41 全部完成，失败 0 个。
- **链路类指标。**第 4 步只覆盖链路类指标，不能作为 README 上已发布参考线的证据；后者的复核情况见 [docs/METRICS_zh-cn.md](METRICS_zh-cn.md)。
- **文件数。**规模采集的文件数与服务端 `Repository.fileCount` 在 41/41 个仓上一致（不一致 0，未知 0）。
- **对账。**每个扫描步骤末行的 `objectCount` 与平台快照列表一致，各仓 report 与 pipeline-status 的 snapshotId / objectCount / sourceHead 三者一致。

## census 守门

| 项 | 值 |
|---|---|
| 已收录样本 | **41** |
| 发布门槛（统计充分性） | 总样本 N ≥ 30 即状态 `published` |
| 隐私护栏（k-匿名单指标级） | 切片 N < 5 不出分位 |
| validation | 四子步 ok 41/41；consistency pass 41 / mismatch 0；与扫描矩阵对账，缺失 0 |

> 该门槛作用在总样本上。具体哪些参考线在 README 上发布，由 [docs/METRICS_zh-cn.md](METRICS_zh-cn.md) 的逐条规则决定，并在生成本文档时强制检查。

## 复现说明

```bash
# 1. 安装 KE CLI（manifest latest + sha256 对账 + 版本断言）
KE_API_KEY=<member key> bash scripts/install-cli.sh /tmp/ke-cli

# 2. 单仓扫描（clone --depth 1 后 ke import start 三段上传直连）
OWNER=macrozheng REPO=mall CLI_DIR=/tmp/ke-cli \
KE_API_KEY=<member key> KE_SERVER_URL=https://console.kengine.ai \
bash scripts/scan-one.sh
# 步骤末行为导入 summary JSON（ok / status / snapshotId / objectCount），失败 exit 1
```
- 对账：Action 步骤末行 `objectCount` 与平台快照列表逐位对照；仓级 report 与 pipeline-status 的 snapshotId / objectCount / sourceHead 三者一致。

### 重扫轨说明（分析器版本升级后的口径修正重扫）

仓 HEAD 不变时，`ke import start` 撞已 complete 的快照会 **dedup skipped**（静默跳过）。这是月度重扫的正确去重行为，但会吞掉分析器升级带来的口径修正。因此**分析器版本升级后的重扫必须走 force 轨**（Actions 页手动触发时勾选 `scan_force`，或本地 `SCAN_FORCE=true`）：

```bash
SCAN_FORCE=true OWNER=dromara REPO=RuoYi-Vue-Plus CLI_DIR=/tmp/ke-cli \
KE_API_KEY=<member key> KE_SERVER_URL=https://console.kengine.ai \
bash scripts/scan-one.sh
```
- 判别：force 轨 summary `status == "completed"`（重建）；默认轨同 HEAD 为 `"skipped"`（数值不变）。
- 口径分界：force 重扫 commit 即口径前后的自然分界（git 历史可追溯）。

[基线扫描记录](https://github.com/asdm-ai/asdm-ke-index/actions/runs/45829165719)
