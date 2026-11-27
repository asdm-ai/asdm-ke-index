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
#   B. report 锚（兜底判据——仅限服务端列表查询失败时：fail-open 兜底；
#      服务端正常响应（含空列表 = ops 清库/从 0 重扫）禁用——服务端为唯一
#      真相源，空列表即明确重建指令）：report.snapshot.sourceHead == 远端 HEAD
#      且 report.cliVersion == manifest。
# 迁移注记：存量快照 sourceVersion="head"（导入时未传 --commit）——首轮不满足
#   规则 A（"head" != sha）；report 无 sourceHead 时规则 B 亦不命中 → 全量
#   重导入一轮并以 --commit sha 落新锚，此后进入稳态（同 commit 秒级跳过、
#   新 commit 自动建新快照——五元组幂等键含 sourceVersion）。
# 编译模式锚（2026-11-27 编译子步）：BUILD_JSON 非空 = 该仓在 build.yaml 配置了构建，
#   期望模式 bytecode；report.build.mode 不等于期望模式即不跳过（存量 report 无 build
#   字段 = 源码模式）。效果：配置了构建的仓在拿到编译版快照之前每次都重跑（上一轮
#   回退源码的仓下一轮自动重试编译）；scan-one 据模式变化决定是否 --force 重建。
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

# 编译模式锚：期望模式（配置了构建 = bytecode）对比 report 记录的快照模式
BUILD_JSON="${BUILD_JSON:-}"
[ "$BUILD_JSON" = "null" ] && BUILD_JSON=""
DESIRED_MODE="source"
[ -n "$BUILD_JSON" ] && DESIRED_MODE="bytecode"
REPORT_MODE="source"
if [ -f "$REPORT" ]; then
  REPORT_MODE=$(jq -r '.build.mode // "source"' "$REPORT" 2>/dev/null || echo source)
fi
MODE_FRESH="false"
[ "$REPORT_MODE" = "$DESIRED_MODE" ] && MODE_FRESH="true"

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
# SERVER_OK：区分「服务端查询失败」与「服务端正常返回空列表」——前者允许
# 规则 B 兜底（fail-open），后者 = 服务端明确无快照（如 ops 清库/从 0 重扫）
# 必须重建（服务端为唯一真相源，见头注；2026-11-24 修复——run #28 曾因此
# 误跳过 39/41：快照已清但旧 report 双锚命中规则 B）
SNAP_ID=""; SNAP_VERSION=""; SERVER_OK="false"
SNAP_JSON=$(curl -fsSL -m 20 -H "Authorization: Bearer $KE_API_KEY" \
  "$KE_SERVER_URL/api/snapshots?source=$(printf '%s' "$REPO" | jq -sRr @uri)" 2>/dev/null || true)
if printf '%s' "${SNAP_JSON:-}" | jq -e 'has("snapshots")' >/dev/null 2>&1; then
  SERVER_OK="true"
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
MODE_NOTE="模式已对齐（${DESIRED_MODE}）"
[ "$MODE_FRESH" = "true" ] || MODE_NOTE="期望 ${DESIRED_MODE}、report 记录 ${REPORT_MODE}（编译模式锚不满足——不跳过）"
if [ "$SCAN_FORCE" != "true" ] && [ "$MODE_FRESH" = "true" ] && [ -n "$CLI_VERSION" ] && [ -n "$REMOTE_HEAD" ]; then
  # 规则 A：服务端锚 + report 新鲜度
  if [ -n "$SNAP_ID" ] && [ "$SNAP_VERSION" = "$REMOTE_HEAD" ] && [ -f "$REPORT" ]; then
    REPORT_CLI=$(jq -r '.cliVersion // empty' "$REPORT")
    REPORT_SNAP=$(jq -r '.snapshot.snapshotId // empty' "$REPORT")
    if [ "$REPORT_CLI" = "$CLI_VERSION" ] && [ "$REPORT_SNAP" = "$SNAP_ID" ]; then
      SKIP="true"; SKIP_RULE="A(server-anchor)"
    fi
  fi
  # 规则 B：report 锚兜底（sourceHead）——仅限服务端查询失败（SERVER_OK != true）。
  # 服务端正常响应（含空列表）时禁用：快照被 ops 删除 = 服务端真相源明确要求重建，
  # 兜底判据不得越过服务端否决（2026-11-24 门控修正）。
  if [ "$SKIP" != "true" ] && [ "$SERVER_OK" != "true" ] && [ -f "$REPORT" ]; then
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
echo "  server snapshot: id=${SNAP_ID:-<none>} sourceVersion=${SNAP_VERSION:-<none>} server_ok=$SERVER_OK"
if [ "$SKIP" = "true" ]; then
  echo "  （规则 ${SKIP_RULE} 命中——跳过 CLI 装配/clone/import/metrics）"
fi
echo "  build mode: $MODE_NOTE"
