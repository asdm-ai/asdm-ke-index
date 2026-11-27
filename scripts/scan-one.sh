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
# 投影错峰（B3 / Hotfix-14 → 2026-11-25 按仓穿行）：DEFER_PROJECTION=true（缺省）
#       时 import start 透传 --defer-projection——commit 跳过在途 Neo4j 投影，
#       由同 job 的下一显式子步 ke project <snapshotId> 键控补投（穿行结构：
#       扫描→投影→指标→一致性四子步各自独立结论；防风暴背景 run #29——服务端
#       侧另有 obj_unique 唯一约束 + 投影并发上限 + 同快照互斥三重防护）
#       早期形态（projection-sweep 尾部 job 批量补投）已由穿行结构取代。
# 分桶 clone 缓存（B3）：CLONE_CACHE_DIR 提供时 clone 落桶目录（actions/cache
#       按仓键缓存——同仓重跑/重扫免全量 clone，命中桶 fetch --depth 1 增量刷新）
# 出参：步骤末行回显原始 summary JSON（Action 日志对账锚——objectCount）；
#       GITHUB_OUTPUT：head=<sha> snapshot_id=<id> snapshot_count=<n>
#       import_status=completed|skipped（穿行 ⑤ annotate 消费——子步结论落盘）
#       scale_json=<path>（仓规模采集产物——metrics 子步 --scale-json 消费）
#       build_json=<path>（编译记录——配置了构建的仓落 build/{owner}/{repo}.json；
#       未配置的仓落 $WORK，不入库）build_mode=bytecode|source（快照的实际模式）
# 编译子步（2026-11-27 用户裁决）：BUILD_JSON（build.yaml 单仓配置，经 matrix 注入）
#       非空时在 clone / 规模采集之后、import 之前编译（scripts/build-step.sh）；
#       失败回退源码模式但明确标注（report.build / pipeline-status / docs/BUILD_LOG）。
#       import 的 JAVA_HOME = 编译用的 JDK（javap 版本低于 class 文件版本时分析器
#       静默回退纯源码）。模式变化（source→bytecode）即 --force 重建：导入去重键不含
#       编译状态，否则 dedup skipped 会把旧快照当成新结论。dedup skipped 时快照未变，
#       记录里的模式取上一轮 report 的模式（这一轮编译没成但上一轮的编译版快照仍在）。
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
CLONE_CACHE_DIR="${CLONE_CACHE_DIR:-}"
if [ -n "$CLONE_CACHE_DIR" ] && mkdir -p "$CLONE_CACHE_DIR" 2>/dev/null; then
  # 分桶 clone 缓存（B3）：桶 = $CLONE_CACHE_DIR/<repo>（actions/cache 按仓键
  # 恢复/保存——矩阵各 job 独立 runner，同仓重跑命中免全量 clone）
  BUCKET="$CLONE_CACHE_DIR/$REPO"
  if [ -d "$BUCKET/.git" ]; then
    echo "== clone 缓存桶命中：fetch --depth 1 增量刷新 =="
    git -C "$BUCKET" fetch --depth 1 origin "${BRANCH:-HEAD}"
    git -C "$BUCKET" reset --hard FETCH_HEAD
    # -x：连被 ignore 的构建输出一起清（编译子步的 target/ build/ 不得跨轮残留）
    git -C "$BUCKET" clean -fdxq
  else
    rm -rf "$BUCKET"
    if [ -n "$BRANCH" ]; then
      git clone --depth 1 --branch "$BRANCH" "https://github.com/$OWNER/$REPO.git" "$BUCKET"
    else
      git clone --depth 1 "https://github.com/$OWNER/$REPO.git" "$BUCKET"
    fi
  fi
  REPO_DIR="$BUCKET"
else
  rm -rf "$REPO_DIR"
  if [ -n "$BRANCH" ]; then
    git clone --depth 1 --branch "$BRANCH" "https://github.com/$OWNER/$REPO.git" "$REPO_DIR"
  else
    git clone --depth 1 "https://github.com/$OWNER/$REPO.git" "$REPO_DIR"
  fi
fi

# 源仓 HEAD 锚（preflight-skip.sh 服务端锚判据输入——import start --commit 落
# 服务端快照 sourceVersion + compute-metrics.py 落 report.snapshot.sourceHead）
SCAN_HEAD=$(git -C "$REPO_DIR" rev-parse HEAD)
echo "scan-one: sourceHead=$SCAN_HEAD"
if [ -n "${GITHUB_OUTPUT:-}" ]; then
  echo "head=$SCAN_HEAD" >> "$GITHUB_OUTPUT"
fi

# 仓规模采集（文件数 / 行数——扫描的同时生成：clone 之后、import 之前，同一工作树
# 同一 HEAD，与导入分析的输入同源）。产物路径经 GITHUB_OUTPUT scale_json 传给
# metrics 子步（compute-metrics.py --scale-json → report D3 规模画像）。
# 失败即本步失败：与穿行结构"任何子步失败即该仓任务失败"一致——规模数据缺失的
# report 不算完整结论，不静默降级（用户裁决 2026-11-26）。
# scale.sourceHead 必须等于 SCAN_HEAD（同一工作树的两次读数——不等即采集对象错位）
SCALE_OUT="${SCALE_OUT:-$WORK/repo-scale.json}"
python3 "$SCRIPT_DIR/repo-scale.py" --repo "$REPO_DIR" --out "$SCALE_OUT"
SCALE_HEAD=$(jq -r '.sourceHead // ""' "$SCALE_OUT")
if [ "$SCALE_HEAD" != "$SCAN_HEAD" ]; then
  echo "FAIL: repo-scale sourceHead=$SCALE_HEAD != scan HEAD=${SCAN_HEAD}（采集对象错位）" >&2
  exit 1
fi
if [ -n "${GITHUB_OUTPUT:-}" ]; then
  echo "scale_json=$SCALE_OUT" >> "$GITHUB_OUTPUT"
fi

# 编译子步：BUILD_JSON 非空 = 该仓在 build.yaml 里配置了构建。记录路径——配置了的仓
# 直接落 build/{owner}/{repo}.json（与 report / status 同一步入库；含编译输出末 60 行，
# 定位失败用），未配置的仓落 ${WORK}（不入库：未配置仓的重跑不产生 git diff）。
BUILD_JSON="${BUILD_JSON:-}"
[ "$BUILD_JSON" = "null" ] && BUILD_JSON=""
BUILD_OUT="$WORK/build.json"
if [ -n "$BUILD_JSON" ]; then
  mkdir -p "build/$OWNER"
  BUILD_OUT="build/$OWNER/$REPO.json"
fi
REPO_DIR="$REPO_DIR" BUILD_JSON="$BUILD_JSON" OUT="$BUILD_OUT" bash "$SCRIPT_DIR/build-step.sh"
BUILD_MODE=$(jq -r '.mode' "$BUILD_OUT")
# 上一轮 report 记录的快照模式（存量 report 无 build 字段 = 源码模式）
PREV_MODE=$(jq -r '.build.mode // "source"' "reports/$OWNER/$REPO.json" 2>/dev/null || echo source)
# 编译与解析同一个 JDK：javap 经 PATH 解析，版本低于 class 文件版本时分析器静默回退
BUILD_JAVA_HOME=$(jq -r '.javaHome // ""' "$BUILD_OUT")
if [ -n "$BUILD_JAVA_HOME" ]; then
  export JAVA_HOME="$BUILD_JAVA_HOME"
  export PATH="$JAVA_HOME/bin:$PATH"
fi
if [ -n "${GITHUB_OUTPUT:-}" ]; then
  echo "build_json=$BUILD_OUT" >> "$GITHUB_OUTPUT"
fi

# 投影错峰轨（B3）：缺省 defer（批扫投影风暴治理）；DEFER_PROJECTION=false 显式关闭
DEFER_PROJECTION="${DEFER_PROJECTION:-true}"
DEFER_ARG="--defer-projection"
DEFER_LABEL="，--defer-projection 投影错峰"
if [ "$DEFER_PROJECTION" = "false" ]; then
  DEFER_ARG=""
  DEFER_LABEL=""
fi
# 花括号展开里不放非 ASCII 字符（bash 3.2 解析缺陷——本地冒烟会误报 unbound variable）
FORCE_LABEL=""
JDK_LABEL=""
if [ -n "${JAVA_HOME:-}" ]; then JDK_LABEL="，JAVA_HOME=$JAVA_HOME"; fi
echo "== ke import start（--mode server → ${KE_SERVER_URL}，--commit ${SCAN_HEAD:0:12}$FORCE_LABEL${DEFER_LABEL}，build=${BUILD_MODE}（上轮 ${PREV_MODE}）${JDK_LABEL}）=="
FORCE_ARG=""
FORCE_WHY=""
if [ "${SCAN_FORCE:-}" = "true" ]; then
  FORCE_ARG="--force"
  FORCE_WHY="scan_force"
  FORCE_LABEL="，--force 重扫轨"
elif [ "$BUILD_MODE" = "bytecode" ] && [ "$PREV_MODE" != "bytecode" ]; then
  # 模式变化：源码模式的旧快照不能当作 bytecode 的结论——强制重建
  FORCE_ARG="--force"
  FORCE_WHY="build-mode-change:$PREV_MODE->bytecode"
fi
[ -n "$FORCE_WHY" ] && echo "scan-one: --force（${FORCE_WHY}）"
set +e
ke --mode server --url "$KE_SERVER_URL" --token "$KE_API_KEY" \
  import start --repo "$REPO_DIR" --commit "$SCAN_HEAD" $FORCE_ARG $DEFER_ARG > "$WORK/import.log" 2>&1
RC=$?
set -e
# 编译输出不留进 clone 缓存桶（体量大；留了只会撑爆缓存配额）
if [ -n "$BUILD_JSON" ] && [ "$BUILD_MODE" = "bytecode" ]; then
  git -C "$REPO_DIR" clean -fdxq || true
fi
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
# 快照的实际模式：import 新建/重建 → 本轮编译结论；dedup skipped → 快照未变，
# 沿用上一轮 report 的模式（本轮编译失败但上一轮的编译版快照仍在时不降级）
BUILD_NOTE=""
if [ "$STATUS" = "skipped" ] && [ "$BUILD_MODE" != "$PREV_MODE" ]; then
  BUILD_NOTE="dedup skipped：本轮编译结论 ${BUILD_MODE}，快照未变，沿用上一轮模式 ${PREV_MODE}"
  jq --arg m "$PREV_MODE" --arg note "$BUILD_NOTE" \
    '.attemptMode = .mode | .attemptReason = .reason | .mode = $m
     | .fallback = (.configured and $m == "source") | .note = $note' \
    "$BUILD_OUT" > "$BUILD_OUT.tmp"
  mv "$BUILD_OUT.tmp" "$BUILD_OUT"
  BUILD_MODE="$PREV_MODE"
fi
if [ -n "$BUILD_NOTE" ]; then
  echo "scan-one: $BUILD_NOTE"
fi
# snapshot_id/count 出参（B3）：穿行结构下由同 job 投影/指标/一致性子步消费
# （ke project 键控补投对象 + metrics --snapshot 显式键控 + annotate 状态落盘）
if [ -n "${GITHUB_OUTPUT:-}" ] && [ -n "$SNAPSHOT_ID" ] && [ "$SNAPSHOT_ID" != "null" ]; then
  echo "snapshot_id=$SNAPSHOT_ID" >> "$GITHUB_OUTPUT"
  echo "snapshot_count=${OBJECT_COUNT:-0}" >> "$GITHUB_OUTPUT"
  echo "import_status=${STATUS}" >> "$GITHUB_OUTPUT"
  echo "build_mode=$BUILD_MODE" >> "$GITHUB_OUTPUT"
fi
# 末行回显单行紧凑 summary JSON（服务端对账锚——与 /api/snapshots objectCount 逐位对照）
printf '%s\n' "$SUMMARY" | jq -c .
