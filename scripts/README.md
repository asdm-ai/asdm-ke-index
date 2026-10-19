# scripts/

扫描管线脚本目录（占位——随管线建设填充）。

| 脚本 | 用途 |
|---|---|
| `install-cli.sh` | 下载 KE CLI（manifest latest + sha256 对账）并安装 |
| `scan-one.sh` | 单仓扫描：clone `--depth 1` → `ke import start`（三段上传直连） |
| `compute-metrics.py` | L1 指标计算 → `reports/{owner}/{repo}.json`（含分子分母与指令溯源） |
| `census.py` | 聚合分位（N<30 守门——accumulating 不出分位）→ `census/summary.json` |
