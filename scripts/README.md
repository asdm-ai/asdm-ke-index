# scripts/

扫描管线脚本目录（占位——随管线建设填充）。

| 脚本 | 用途 |
|---|---|
| `install-cli.sh` | 下载 KE CLI（manifest latest + sha256 对账）并安装 |
| `scan-one.sh` | 单仓扫描：clone `--depth 1` → `ke import start`（三段上传直连） |
| `compute-metrics.py` | L1 指标计算 → `reports/{owner}/{repo}.json`（含分子分母与指令溯源） |
| `census.py` | 聚合分位（N<30 守门——accumulating 不出分位）→ `census/summary.json` |
| `repo-scale.py` | 仓规模采集（文件数 / 行数，分语言）——`scan-one.sh` clone 后调用 |
| `scan-matrix.sh` | 生成扫描矩阵：`repos.yaml` 去掉 skip 的仓，逐条并入 `build.yaml` 构建配置，可按 `scan_repos` 白名单收窄 |
| `build-step.sh` | 编译子步：对配置了构建的仓在 clone / 规模采集之后、import 之前编译；失败回退源码模式并写记录 `build/{owner}/{repo}.json` |
| `scale-backfill.py` | 存量 report 按定锚提交补采仓规模（回填 `D3.scale`，幂等） |
| C3 两种分母 | `compute-metrics.py` 给 C3 写 `calibers{allMethods,sourceAnchored}`：全部方法（冻结口径，顶层 `value`）与有源码方法体（`lineCount > 0`，不含接口/抽象方法与字节码补全方法）。`census.py` 对两种口径分别聚合、分别判 N≥30；入口页与 METRICS 文档两行并列，第二种口径未达门槛时不出行、不出数。没有 `calibers` 的存量 report 在第二种口径里记缺失（待重算 metrics） |
| `render-docs.py` | 由 `repos.yaml` / `census/` / `reports/` / `pipeline-status/` 渲染 `README.md` 与 `docs/`（中英两版）。任一仓管线未通过即拒绝写出；基线元数据写入 `docs/baseline.json` |
| `validate-docs.py` | 把渲染出的页面与产物逐项核对（数字、链接、锚点、中英结构、不应出现的内容），有错退出 1 |
| `push-with-retry.sh` | git push 按拒绝原因分类重试（产物入库步共用） |

文档只能通过 `render-docs.py` 修改：`scan.yml` 在每次扫描后自动重建并提交；`docs.yml` 可手动核对（缺省，与 main 有差异即失败）或重建（`commit=true`）。带 `scan_repos` 白名单的冒烟 run 不发布：census 不提交、文档不重建、基线不变。
