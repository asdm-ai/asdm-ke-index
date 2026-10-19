# asdm-ke-index

KE Index 开源基准库冷启动仓库——开源仓库扫描清单、扫描管线脚本、指标报告与 census 聚合产物。

> 本仓库由 AOS / KE 平台的批量扫描管线（GitHub Actions）自动维护。
> 数据落点：[kengine.ai](https://kengine.ai)；指标口径：AOS Index Metrics Schema。

## 目录结构（随管线建设填充）

| 路径 | 内容 |
|---|---|
| `repos.yaml` | 扫描清单（owner/repo/branch/skip） |
| `scripts/` | `install-cli.sh` / `scan-one.sh` / `compute-metrics.py` / `census.py` |
| `.github/workflows/scan.yml` | 批量扫描 workflow（matrix，max-parallel 4） |
| `reports/{owner}/{repo}.json` | 单仓 L1 指标报告（含分子分母与指令溯源，可复算） |
| `census/summary.json` | 聚合分位（N<30 守门——accumulating 不出分位） |

## 复现说明

扫描由 GitHub Actions（`scan.yml`）自动执行；单仓扫描可本地复现：

```bash
# 1. 安装 KE CLI（manifest latest + sha256 对账 + 版本断言）
KE_API_KEY=<member key> bash scripts/install-cli.sh /tmp/ke-cli

# 2. 单仓扫描（clone --depth 1 → ke import start 三段上传直连）
OWNER=macrozheng REPO=mall CLI_DIR=/tmp/ke-cli \
KE_API_KEY=<member key> KE_SERVER_URL=https://console.kengine.ai \
bash scripts/scan-one.sh
# 步骤末行为导入 summary JSON（ok / status / objectCount）——失败 exit 1
```

- 触发：push 修改 `repos.yaml` / Actions 页手动触发；月度重扫随聚合轮启用
- 并发护栏：`max-parallel: 4`；对账：Action 步骤末行 `objectCount` 与平台快照列表逐位对照

## 仓库索引（随扫描批次填充）

| owner/repo | 快照 | Report | 状态 |
|---|---|---|---|
| `macrozheng/mall` | 待首跑 | 待首跑 | queued |

> 数据落点为 [kengine.ai](https://kengine.ai) 平台 `oss` 租户；report 产物可经 report 内
> 指令溯源逐项复算。

<!-- 徽章段占位：扫描批状态 / 已收录样本数 / census 守门状态（聚合轮填充） -->
