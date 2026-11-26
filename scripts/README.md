# scripts/

扫描管线脚本目录（占位——随管线建设填充）。

| 脚本 | 用途 |
|---|---|
| `install-cli.sh` | 下载 KE CLI（manifest latest + sha256 对账）并安装 |
| `scan-one.sh` | 单仓扫描：clone `--depth 1` → `ke import start`（三段上传直连） |
| `compute-metrics.py` | L1 指标计算 → `reports/{owner}/{repo}.json`（含分子分母与指令溯源） |
| `census.py` | 聚合分位（N<30 守门——accumulating 不出分位）→ `census/summary.json` |
| `repo-scale.py` | 仓规模采集（文件数 / 行数，分语言）——`scan-one.sh` clone 后调用 |
| `scale-backfill.py` | 存量 report 按定锚提交补采仓规模（回填 `D3.scale`，幂等） |
| `render-docs.py` | 由 `repos.yaml` / `census/` / `reports/` / `pipeline-status/` 渲染 `README.md` 与 `docs/`（中英两版）。任一仓管线未通过即拒绝写出；基线元数据写入 `docs/baseline.json` |
| `validate-docs.py` | 把渲染出的页面与产物逐项核对（数字、链接、锚点、中英结构、不应出现的内容），有错退出 1 |
| `push-with-retry.sh` | git push 按拒绝原因分类重试（产物入库步共用） |

文档只能通过 `render-docs.py` 修改：`scan.yml` 在每次扫描后自动重建并提交；`docs.yml` 可手动核对（缺省，与 main 有差异即失败）或重建（`commit=true`）。
