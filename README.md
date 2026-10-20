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

## 仓库索引（种子批 10 仓——分层选样：admin/业务系统 6 + 大型 2 + JPA 2）

| owner/repo | 分层 | Report | 快照 | 状态 |
|---|---|---|---|---|
| [macrozheng/mall](https://github.com/macrozheng/mall) | A·业务系统 | [report](reports/macrozheng/mall.json) | 待首跑回填 | queued |
| [macrozheng/mall-swarm](https://github.com/macrozheng/mall-swarm) | A·业务系统 | [report](reports/macrozheng/mall-swarm.json) | 待首跑回填 | queued |
| [yangzongzhuan/RuoYi-Vue](https://github.com/yangzongzhuan/RuoYi-Vue) | A·admin 脚手架 | [report](reports/yangzongzhuan/RuoYi-Vue.json) | 待首跑回填 | queued |
| [dromara/RuoYi-Vue-Plus](https://github.com/dromara/RuoYi-Vue-Plus) | A·admin 脚手架 | [report](reports/dromara/RuoYi-Vue-Plus.json) | 待首跑回填 | queued |
| [jeecgboot/JeecgBoot](https://github.com/jeecgboot/JeecgBoot) | A·低代码平台 | [report](reports/jeecgboot/JeecgBoot.json) | 待首跑回填 | queued |
| [lenve/vhr](https://github.com/lenve/vhr) | A·业务系统 | [report](reports/lenve/vhr.json) | 待首跑回填 | queued |
| [apache/dubbo](https://github.com/apache/dubbo) | B·大型 | [report](reports/apache/dubbo.json) | 待首跑回填 | queued |
| [apache/fineract](https://github.com/apache/fineract) | B·大型 | [report](reports/apache/fineract.json) | 待首跑回填 | queued |
| [spring-projects/spring-petclinic](https://github.com/spring-projects/spring-petclinic) | C·JPA | [report](reports/spring-projects/spring-petclinic.json) | 待首跑回填 | queued |
| [elunez/eladmin](https://github.com/elunez/eladmin) | C·JPA | [report](reports/elunez/eladmin.json) | 待首跑回填 | queued |

> 数据落点为 [kengine.ai](https://kengine.ai) 平台 `oss` 租户；report 产物可经 report 内
> 指令溯源逐项复算；快照列随种子批首跑回填（census/summary.json 的 repos 区为机器可读源）。

<!-- 徽章段占位：扫描批状态 / 已收录样本数 / census 守门状态（聚合轮填充） -->
