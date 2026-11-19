#!/usr/bin/env bash
# =============================================================================
# 单仓扫描（CLI 直连三段上传——P2H-D1）
# -----------------------------------------------------------------------------
# 用法：OWNER=<o> REPO=<r> KE_API_KEY=<key> [BRANCH=<b>] [CLI_DIR=<dir>] \
#         [SCAN_FORCE=true] bash scripts/scan-one.sh
# 调用形态：ke 指令（CI 由 Install 步骤经 GITHUB_PATH 注入；本地冒烟设 CLI_DIR
#         时由本脚本注入其 bin 到 PATH）——统一 ke 指令调用，不再 node 直调 ke.cjs
# 流程：clone --depth 1 → ke --mode server import start --repo <clone目录>
#       → stdout 末行 summary JSON 解析（import-cmd.ts 契约：
#         {ok, status, jobId, snapshotId, objectCount, linkCount, ...}）
#       → ok!=true 或 status!=completed 时 exit 1
# 重扫轨（R3）：SCAN_FORCE=true 时 import start 透传 --force——同 HEAD 异分析器
#       版本强制重建 manifest/links（默认 dedup skipped 会静默吞掉分析器修复）；
#       缺省（空/false）为月度重扫轨——同 HEAD dedup skipped 属正确行为不视为失败
# 出参：步骤末行回显原始 summary JSON（Action 日志对账锚——objectCount）
# =============================================================================
set -euo pipefail

: "${KE_API_KEY:?KE_API_KEY is required}"
: "${KE_SERVER_URL:?KE_SERVER_URL is required}"
: "${OWNER:?OWNER is required}"
: "${REPO:?REPO is required}"

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
CLI_DIR="${CLI_DIR:-$SCRIPT_DIR/../ke-cli}"
WORK="${WORKDIR:-$(mktemp -d)}"
BRANCH="${BRANCH:-}"
mkdir -p "$WORK"

# ke 指令解析：CLI_DIR 提供时注入其 bin（本地冒烟）；CI 走 GITHUB_PATH 预注入
export PATH="$CLI_DIR/bin:$PATH"
if ! command -v ke >/dev/null 2>&1; then
  echo "FAIL: ke 指令不可用（PATH 无 ke，且 $CLI_DIR/bin/ke 不存在——先运行 install-cli.sh）" >&2
  exit 1
fi

echo "== clone ${OWNER}/${REPO}（--depth 1${BRANCH:+，branch=$BRANCH}）=="
REPO_DIR="$WORK/$REPO"
rm -rf "$REPO_DIR"
if [ -n "$BRANCH" ]; then
  git clone --depth 1 --branch "$BRANCH" "https://github.com/$OWNER/$REPO.git" "$REPO_DIR"
else
  git clone --depth 1 "https://github.com/$OWNER/$REPO.git" "$REPO_DIR"
fi

# 源仓 HEAD 锚（preflight-skip.sh 跳过判据输入——compute-metrics.py 落 report.snapshot.sourceHead）
SCAN_HEAD=$(git -C "$REPO_DIR" rev-parse HEAD)
echo "scan-one: sourceHead=$SCAN_HEAD"
if [ -n "${GITHUB_OUTPUT:-}" ]; then
  echo "head=$SCAN_HEAD" >> "$GITHUB_OUTPUT"
fi

echo "== ke import start（--mode server → ${KE_SERVER_URL}$([ "${SCAN_FORCE:-}" = "true" ] && printf '，--force 重扫轨')）=="
FORCE_ARG=""
if [ "${SCAN_FORCE:-}" = "true" ]; then
  FORCE_ARG="--force"
fi
set +e
ke --mode server --url "$KE_SERVER_URL" --token "$KE_API_KEY" \
  import start --repo "$REPO_DIR" $FORCE_ARG > "$WORK/import.log" 2>&1
RC=$?
set -e
tail -n 15 "$WORK/import.log"

# summary 为美化多行 JSON（outputJSON——shared.ts 契约）：取最后一个行首 "{" 起的完整块
SUMMARY_LINE=$(grep -n '^{$' "$WORK/import.log" | tail -n 1 | cut -d: -f1)
if [ -z "$SUMMARY_LINE" ]; then
  echo "FAIL: import 输出中未找到 summary JSON 块（rc=${RC}）" >&2
  exit 1
fi
SUMMARY=$(tail -n +"$SUMMARY_LINE" "$WORK/import.log")
# CLI 契约（import-cmd.ts）：ok = status ∈ {completed, skipped}——skipped 为同源
# 同 HEAD 重扫的去重语义（月度重扫的正确行为，不视为失败）
if ! printf '%s' "$SUMMARY" | jq -e '.ok == true and (.status == "completed" or .status == "skipped")' >/dev/null 2>&1; then
  echo "FAIL: import summary 未通过（rc=${RC}）：$(printf '%s' "$SUMMARY" | jq -c . 2>/dev/null || echo "$SUMMARY")" >&2
  exit 1
fi

OBJECT_COUNT=$(printf '%s' "$SUMMARY" | jq -r '.objectCount')
SNAPSHOT_ID=$(printf '%s' "$SUMMARY" | jq -r '.snapshotId')
STATUS=$(printf '%s' "$SUMMARY" | jq -r '.status')
echo "scan-one: $OWNER/$REPO ${STATUS} objectCount=$OBJECT_COUNT snapshotId=$SNAPSHOT_ID"
# 末行回显单行紧凑 summary JSON（服务端对账锚——与 /api/snapshots objectCount 逐位对照）
printf '%s\n' "$SUMMARY" | jq -c .
