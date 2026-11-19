#!/usr/bin/env bash
# =============================================================================
# 扫描前置检查（本地短路——零漂移轨跳过判定，服务端锚版）
# -----------------------------------------------------------------------------
# 用法：OWNER=<o> REPO=<r> KE_API_KEY=<key> [BRANCH=<b>] [KE_SERVER_URL=<url>] \
#         [SCAN_FORCE=true] bash scripts/preflight-skip.sh
# 跳过判据（fail-open：任何取值失败一律不跳过，走全流程）：
#   0. SCAN_FORCE != true（force 重扫轨永不跳过——R3 语义）
#   A. 服务端锚（主判据——scan-one 传 import start --commit <sha> 落锚）：
#      该 sourceId 最新 complete 快照 sourceVersion == ls-remote 远端 HEAD
#      且 report 新鲜（report.cliVersion == manifest latest——R6 版本锚；
#      report.snapshot.snapshotId == 服务端最新 complete 快照 id——防"上次
#      metrics 失败 report 滞后"形态）。服务端为唯一真相源：快照被 ops 删除
#      即不命中 → 自然触发重建，无本地状态失真风险。
#   B. report 锚（兜底判据——存量 "head" 快照过渡期/服务端列表查询异常时）：
#      report.snapshot.sourceHead == 远端 HEAD 且 report.cliVersion == manifest。
# 迁移注记：存量快照 sourceVersion="head"（导入时未传 --commit）——首轮不满足
#   规则 A（"head" != sha）；report 无 sourceHead 时规则 B 亦不命中 → 全量
#   重导入一轮并以 --commit sha 落新锚，此后进入稳态（同 commit 秒级跳过、
#   新 commit 自动建新快照——五元组幂等键含 sourceVersion）。
# 出参（GITHUB_OUTPUT——CI 步骤间传递；本地冒烟 stdout 可见）：
#   skip=true|false   cli_version=<manifest latest>   remote_head=<sha>
# =============================================================================
set -euo pipefail

: "${KE_API_KEY:?KE_API_KEY is required}"
KE_SERVER_URL="${KE_SERVER_URL:-https://console.kengine.ai}"
: "${OWNER:?OWNER is required}"
: "${REPO:?REPO is required}"
BRANCH="${BRANCH:-}"
SCAN_FORCE="${SCAN_FORCE:-false}"
REPORT="reports/$OWNER/$REPO.json"

# manifest latest（fail-open：curl/jq 失败 → 空版本 → 版本锚永不满足 → 不跳过）
CLI_VERSION=$(curl -fsSL -m 15 -H "Authorization: Bearer $KE_API_KEY" \
  "$KE_SERVER_URL/api/downloads/cli/manifest" 2>/dev/null | jq -r '.version // empty' || true)

# 远端 HEAD（不 clone——单次 ls-remote 往返）
REMOTE_HEAD=""
if [ -n "$BRANCH" ]; then
  REMOTE_HEAD=$(git ls-remote "https://github.com/$OWNER/$REPO.git" "refs/heads/$BRANCH" 2>/dev/null | cut -f1 || true)
else
  REMOTE_HEAD=$(git ls-remote "https://github.com/$OWNER/$REPO.git" HEAD 2>/dev/null | cut -f1 || true)
fi

# 服务端快照（sourceId = repo 名；GET /api/snapshots?source=<id>——Bearer 同租户
# 过滤；取最新 complete 快照的 snapshotId/sourceVersion）
SNAP_ID=""; SNAP_VERSION=""
SNAP_JSON=$(curl -fsSL -m 20 -H "Authorization: Bearer $KE_API_KEY" \
  "$KE_SERVER_URL/api/snapshots?source=$(printf '%s' "$REPO" | jq -sRr @uri)" 2>/dev/null || true)
if [ -n "$SNAP_JSON" ]; then
  LATEST=$(printf '%s' "$SNAP_JSON" | jq -r \
    '[.snapshots[]? | select(.status == "complete")]
     | sort_by(.completedAt // .createdAt // "") | last
     | if . then "\(.snapshotId)\t\(.sourceVersion // "")" else empty end' 2>/dev/null || true)
  if [ -n "$LATEST" ]; then
    SNAP_ID=${LATEST%%$'\t'*}
    SNAP_VERSION=${LATEST#*$'\t'}
  fi
fi

SKIP="false"
SKIP_RULE=""
if [ "$SCAN_FORCE" != "true" ] && [ -n "$CLI_VERSION" ] && [ -n "$REMOTE_HEAD" ]; then
  # 规则 A：服务端锚 + report 新鲜度
  if [ -n "$SNAP_ID" ] && [ "$SNAP_VERSION" = "$REMOTE_HEAD" ] && [ -f "$REPORT" ]; then
    REPORT_CLI=$(jq -r '.cliVersion // empty' "$REPORT")
    REPORT_SNAP=$(jq -r '.snapshot.snapshotId // empty' "$REPORT")
    if [ "$REPORT_CLI" = "$CLI_VERSION" ] && [ "$REPORT_SNAP" = "$SNAP_ID" ]; then
      SKIP="true"; SKIP_RULE="A(server-anchor)"
    fi
  fi
  # 规则 B：report 锚兜底（sourceHead——过渡期/服务端列表不可用）
  if [ "$SKIP" != "true" ] && [ -f "$REPORT" ]; then
    REPORT_CLI=$(jq -r '.cliVersion // empty' "$REPORT")
    REPORT_HEAD=$(jq -r '.snapshot.sourceHead // empty' "$REPORT")
    if [ "$REPORT_CLI" = "$CLI_VERSION" ] && [ "$REPORT_HEAD" = "$REMOTE_HEAD" ]; then
      SKIP="true"; SKIP_RULE="B(report-anchor)"
    fi
  fi
fi

if [ -n "${GITHUB_OUTPUT:-}" ]; then
  {
    echo "skip=$SKIP"
    echo "cli_version=$CLI_VERSION"
    echo "remote_head=$REMOTE_HEAD"
  } >> "$GITHUB_OUTPUT"
fi

echo "preflight: $OWNER/$REPO skip=$SKIP cli_version=${CLI_VERSION:-<unavailable>} remote_head=${REMOTE_HEAD:-<unavailable>}"
echo "  server snapshot: id=${SNAP_ID:-<none>} sourceVersion=${SNAP_VERSION:-<none>}"
if [ "$SKIP" = "true" ]; then
  echo "  （规则 ${SKIP_RULE} 命中——跳过 CLI 装配/clone/import/metrics）"
fi
