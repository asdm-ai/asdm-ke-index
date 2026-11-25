#!/usr/bin/env bash
# =============================================================================
# 穿行状态落盘（按仓穿行 ⑤ annotate——2026-11-25 用户裁决）
# -----------------------------------------------------------------------------
# 用法（env 注入——scan.yml Annotate 步）：
#   OWNER=<o> REPO=<r> [SOURCE_HEAD=<sha>] [SNAPSHOT_ID=<id>] [OBJECT_COUNT=<n>]
#   [IMPORT_STATUS=completed|skipped]
#   SCAN_C=success|failure|skipped PROJECTION_C=... METRICS_C=... CONSISTENCY_C=...
#   [CONSISTENCY_RC=0|2|1]（graph-metrics.py 退出码：0 PASS / 2 MISMATCH / 1 崩溃）
#   bash scripts/pipeline-status.sh
# 输出：pipeline-status/{owner}/{repo}.json（确定性——无墙钟字段）：
#   同仓同快照重跑逐字节一致 → 月度 dedup skip 不产生 git diff
# 结论语义（与 job conclusion 对齐——本脚本不改判，只落盘 + 提升可见性）：
#   overall = pass 当且仅当四子步全 ok（scan/projection/metrics/consistency）；
#   任一 failed → ::error:: 标注（job 已由失败子步置 failed）
# consistencyResult：pass / mismatch（rc=2）/ error（其它 rc）/ skipped
# =============================================================================
set -euo pipefail

: "${OWNER:?OWNER is required}"
: "${REPO:?REPO is required}"

map_c() {
  # GitHub Actions steps.<id>.conclusion → 状态机三值
  case "${1:-}" in
    success) echo "ok" ;;
    failure) echo "failed" ;;
    *)       echo "skipped" ;;
  esac
}

SCAN_OK=$(map_c "${SCAN_C:-}")
PROJ_OK=$(map_c "${PROJECTION_C:-}")
MET_OK=$(map_c "${METRICS_C:-}")
CONS_OK=$(map_c "${CONSISTENCY_C:-}")

case "${CONSISTENCY_C:-}" in
  success) CONS_RES="pass" ;;
  failure)
    if [ "${CONSISTENCY_RC:-}" = "2" ]; then
      CONS_RES="mismatch"
    else
      CONS_RES="error"
    fi
    ;;
  *) CONS_RES="skipped" ;;
esac

if [ "$SCAN_OK" = "ok" ] && [ "$PROJ_OK" = "ok" ] && [ "$MET_OK" = "ok" ] && [ "$CONS_OK" = "ok" ]; then
  OVERALL="pass"
else
  OVERALL="fail"
fi

mkdir -p "pipeline-status/$OWNER"
OUT="pipeline-status/$OWNER/$REPO.json"
jq -n \
  --arg owner "$OWNER" \
  --arg repo "$REPO" \
  --arg sourceHead "${SOURCE_HEAD:-}" \
  --arg snapshotId "${SNAPSHOT_ID:-}" \
  --argjson objectCount "${OBJECT_COUNT:-null}" \
  --arg importStatus "${IMPORT_STATUS:-}" \
  --arg scan "$SCAN_OK" \
  --arg projection "$PROJ_OK" \
  --arg metrics "$MET_OK" \
  --arg consistency "$CONS_OK" \
  --arg consistencyResult "$CONS_RES" \
  --arg overall "$OVERALL" \
  '{
    schemaVersion: "pipeline-status-v1",
    owner: $owner,
    repo: $repo,
    sourceHead: (if $sourceHead == "" then null else $sourceHead end),
    snapshotId: (if $snapshotId == "" then null else $snapshotId end),
    objectCount: $objectCount,
    importStatus: (if $importStatus == "" then null else $importStatus end),
    steps: {
      scan: $scan,
      projection: $projection,
      metrics: $metrics,
      consistency: $consistency
    },
    consistencyResult: $consistencyResult,
    overall: $overall
  }' > "$OUT"

echo "pipeline-status: $OWNER/$REPO overall=$OVERALL scan=$SCAN_OK projection=$PROJ_OK metrics=$MET_OK consistency=${CONS_OK}（${CONS_RES}）"

# 失败可见性：GitHub Actions annotation（job 页 annotation 区 + summary 聚合面）
if [ "$OVERALL" != "pass" ]; then
  NOT_OK=""
  if [ "$SCAN_OK" != "ok" ]; then NOT_OK="${NOT_OK:+$NOT_OK }scan:$SCAN_OK"; fi
  if [ "$PROJ_OK" != "ok" ]; then NOT_OK="${NOT_OK:+$NOT_OK }projection:$PROJ_OK"; fi
  if [ "$MET_OK" != "ok" ]; then NOT_OK="${NOT_OK:+$NOT_OK }metrics:$MET_OK"; fi
  if [ "$CONS_OK" != "ok" ]; then NOT_OK="${NOT_OK:+$NOT_OK }consistency:$CONS_OK($CONS_RES)"; fi
  echo "::error::穿行验证失败 ${OWNER}/${REPO}：${NOT_OK}（详见 pipeline-status/${OWNER}/${REPO}.json）"
fi
