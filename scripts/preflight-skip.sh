#!/usr/bin/env bash
# =============================================================================
# 扫描前置检查（本地短路——月度重扫零漂移轨的跳过判定）
# -----------------------------------------------------------------------------
# 用法：OWNER=<o> REPO=<r> KE_API_KEY=<key> [BRANCH=<b>] [KE_SERVER_URL=<url>] \
#         [SCAN_FORCE=true] bash scripts/preflight-skip.sh
# 判据（全部满足才跳过——fail-open：任何取值失败一律不跳过，走全流程）：
#   1. SCAN_FORCE != true（force 重扫轨永不跳过——R3 语义）
#   2. reports/$OWNER/$REPO.json 存在
#   3. report.cliVersion == manifest latest（CLI 版本漂移即过期——R6 同锚）
#   4. report.snapshot.sourceHead == git ls-remote 远端 HEAD（无新提交零漂移）
# 出参（GITHUB_OUTPUT——CI 步骤间传递；本地冒烟 stdout 可见）：
#   skip=true|false   cli_version=<manifest latest>   remote_head=<sha>
# 注意：
#   - sourceHead 由 scan-one.sh clone 后提取、compute-metrics.py 落 report——
#     存量 report 无该字段时本判据不满足（首轮不跳过，跑一次即回填锚）
#   - ops 删除服务端快照后本地 report 仍在——需配 dispatch scan_force=true
#     或删除对应 report 文件，否则本短路会误跳过重建
# =============================================================================
set -euo pipefail

: "${KE_API_KEY:?KE_API_KEY is required}"
KE_SERVER_URL="${KE_SERVER_URL:-https://console.kengine.ai}"
: "${OWNER:?OWNER is required}"
: "${REPO:?REPO is required}"
BRANCH="${BRANCH:-}"
SCAN_FORCE="${SCAN_FORCE:-false}"
REPORT="reports/$OWNER/$REPO.json"

# manifest latest（fail-open：curl/jq 失败 → 空版本 → 判据 3 永不满足 → 不跳过）
CLI_VERSION=$(curl -fsSL -m 15 -H "Authorization: Bearer $KE_API_KEY" \
  "$KE_SERVER_URL/api/downloads/cli/manifest" 2>/dev/null | jq -r '.version // empty' || true)

# 远端 HEAD（不 clone——单次 ls-remote 往返）
REMOTE_HEAD=""
if [ -n "$BRANCH" ]; then
  REMOTE_HEAD=$(git ls-remote "https://github.com/$OWNER/$REPO.git" "refs/heads/$BRANCH" 2>/dev/null | cut -f1 || true)
else
  REMOTE_HEAD=$(git ls-remote "https://github.com/$OWNER/$REPO.git" HEAD 2>/dev/null | cut -f1 || true)
fi

SKIP="false"
if [ "$SCAN_FORCE" != "true" ] && [ -f "$REPORT" ] \
   && [ -n "$CLI_VERSION" ] && [ -n "$REMOTE_HEAD" ]; then
  REPORT_CLI=$(jq -r '.cliVersion // empty' "$REPORT")
  REPORT_HEAD=$(jq -r '.snapshot.sourceHead // empty' "$REPORT")
  if [ "$REPORT_CLI" = "$CLI_VERSION" ] && [ "$REPORT_HEAD" = "$REMOTE_HEAD" ]; then
    SKIP="true"
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
if [ "$SKIP" = "true" ]; then
  echo "  （report 锚命中——cliVersion 与 sourceHead 均无漂移，跳过 CLI 装配/clone/import/metrics）"
fi
