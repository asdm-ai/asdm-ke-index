#!/usr/bin/env bash
# =============================================================================
# 编译子步（bytecode 模式——2026-11-27 用户裁决）
# -----------------------------------------------------------------------------
# 用法：REPO_DIR=<clone 目录> [BUILD_JSON=<build.yaml 单仓配置；空或 null = 未配置>]
#         [OUT=<记录输出路径>] [BUILD_JAVA_HOME=<dir>]（本地冒烟：直接指定 JDK）
#         bash scripts/build-step.sh
# 位置：scan-one.sh 的 clone / 仓规模采集之后、ke import 之前。目的：让 KE 的字节码
#       能力（javap 读 invoke 指令——calls 边、Lombok 补全方法）有输入。
# 结论（写入 OUT，记录 schema build-v1）：
#   mode      bytecode ——主源码编译成功且产出了 .class（import 时字节码路径生效）
#             source   ——未配置构建 / 配置非法 / 找不到 JDK 或 wrapper / 编译失败 /
#                         超时 / 无 .class。编译失败不算管线失败（用户裁决：回退源码
#                         模式，但结果里必须明确标注，fallback=true）
#   reason    not-configured | invalid-config | jdk-not-found | wrapper-not-found |
#             compiled | compile-failed | compile-timeout | no-class-files
#   其余字段：tool / jdk / root / javaHome / javaVersion / javapVersion / command /
#             exitCode / testExitCode / classFiles{main,test,other} / durationSec /
#             logTail（末 60 行编译输出——定位失败用；不进 docs，只入库 build/）
# 约束：
#   - 失败回退时清掉本次产生的全部编译输出（部分模块编过的 .class 不留——否则是
#     介于两种模式之间的第三种口径）；成功时输出保留到 import 结束，由 scan-one 清理
#   - 调用方必须用记录里的 javaHome 作为 import 阶段的 JAVA_HOME——javap 版本低于
#     class 文件版本时分析器静默回退纯源码（不报错），编译与解析必须是同一个 JDK
#   - 本脚本只在脚本自身出错时非零退出；编译失败一律 exit 0 + 记录
# =============================================================================
set -euo pipefail

: "${REPO_DIR:?REPO_DIR is required}"
BUILD_JSON="${BUILD_JSON:-}"
[ "$BUILD_JSON" = "null" ] && BUILD_JSON=""
OUT="${OUT:-build-record.json}"
BUILD_TIMEOUT_SEC="${BUILD_TIMEOUT_SEC:-1800}"
BUILD_TEST_TIMEOUT_SEC="${BUILD_TEST_TIMEOUT_SEC:-900}"
LOG_TAIL_LINES="${LOG_TAIL_LINES:-60}"

MODE="source"; REASON="not-configured"
TOOL=""; JDK="null"; ROOT="."
JAVA_HOME_RES=""; JAVA_VER=""; JAVAP_VER=""
COMMAND_JSON="[]"; EXIT_CODE="null"; TEST_EXIT_CODE="null"
CLASS_JSON='{"main":0,"test":0,"other":0}'
DUR_JSON='{"compile":0,"testCompile":0}'
LOG_TAIL_JSON="[]"
LOG=""
# 必须恒返回 0：EXIT 陷阱的返回值在部分 bash 版本里会覆盖脚本自己的 exit 状态
cleanup() { if [ -n "$LOG" ] && [ -f "$LOG" ]; then rm -f "$LOG"; fi; return 0; }
trap cleanup EXIT

emit() {
  jq -n \
    --argjson configured "$CONFIGURED" \
    --arg mode "$MODE" --arg reason "$REASON" \
    --arg tool "$TOOL" --argjson jdk "$JDK" --arg root "$ROOT" \
    --arg javaHome "$JAVA_HOME_RES" --arg javaVersion "$JAVA_VER" --arg javapVersion "$JAVAP_VER" \
    --argjson command "$COMMAND_JSON" \
    --argjson exitCode "$EXIT_CODE" --argjson testExitCode "$TEST_EXIT_CODE" \
    --argjson classFiles "$CLASS_JSON" --argjson durationSec "$DUR_JSON" \
    --argjson logTail "$LOG_TAIL_JSON" \
    '{schemaVersion: "build-v1",
      configured: $configured,
      mode: $mode,
      fallback: ($configured and $mode == "source"),
      reason: $reason,
      tool: (if $configured then $tool else null end),
      jdk: (if $configured then $jdk else null end),
      root: (if $configured then $root else null end),
      javaHome: (if $javaHome == "" then null else $javaHome end),
      javaVersion: (if $javaVersion == "" then null else $javaVersion end),
      javapVersion: (if $javapVersion == "" then null else $javapVersion end),
      command: $command,
      exitCode: $exitCode,
      testExitCode: $testExitCode,
      classFiles: $classFiles,
      durationSec: $durationSec,
      logTail: $logTail}' > "$OUT.tmp"
  mv "$OUT.tmp" "$OUT"
  echo "build-step: mode=$MODE reason=$REASON tool=${TOOL:--} jdk=${JDK} classFiles=$CLASS_JSON exitCode=$EXIT_CODE testExitCode=$TEST_EXIT_CODE"
}

count_classes() {
  find "$REPO_DIR" -type f -name '*.class' -not -path '*/.git/*' | awk '
    /\/target\/classes\/.*\.class$/ || /\/build\/classes\/java\/main\/.*\.class$/ {m++; next}
    /\/target\/test-classes\/.*\.class$/ || /\/build\/classes\/java\/test\/.*\.class$/ {t++; next}
    {o++; next}
    END {printf "{\"main\":%d,\"test\":%d,\"other\":%d}\n", m, t, o}'
}

clean_outputs() {
  if git -C "$REPO_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    # -x：连被 ignore 的构建输出（target/ build/ .gradle）一起清
    git -C "$REPO_DIR" clean -fdxq
  else
    find "$REPO_DIR" -type f -name '*.class' -not -path '*/.git/*' -delete
  fi
}

take_log_tail() {
  [ -n "$LOG" ] && [ -f "$LOG" ] || { LOG_TAIL_JSON="[]"; return 0; }
  LOG_TAIL_JSON=$(sed 's/\x1b\[[0-9;]*[a-zA-Z]//g' "$LOG" | tr -d '\r' \
    | awk '{print substr($0, 1, 400)}' | tail -n "$LOG_TAIL_LINES" | jq -Rn '[inputs]')
}

# ---- 未配置：源码模式（清单内没有 build 条目的仓走这里）----
if [ -z "$BUILD_JSON" ]; then
  CONFIGURED=false
  emit
  exit 0
fi
CONFIGURED=true

# ---- 配置解析与校验 ----
if ! printf '%s' "$BUILD_JSON" | jq -e 'type == "object"' >/dev/null 2>&1; then
  REASON="invalid-config"; emit; exit 0
fi
TOOL=$(printf '%s' "$BUILD_JSON" | jq -r '.tool // ""')
JDK=$(printf '%s' "$BUILD_JSON" | jq -c '.jdk // null')
ROOT=$(printf '%s' "$BUILD_JSON" | jq -r '.root // "."')
ARGS_JSON=$(printf '%s' "$BUILD_JSON" | jq -c '.args // []')
if [ "$TOOL" != "maven" ] && [ "$TOOL" != "gradle" ]; then
  REASON="invalid-config"; TOOL=""; JDK="null"; emit; exit 0
fi
if ! [ "$JDK" = "null" ] && ! printf '%s' "$JDK" | jq -e 'type == "number" and . > 0' >/dev/null 2>&1; then
  REASON="invalid-config"; JDK="null"; emit; exit 0
fi
if ! printf '%s' "$ARGS_JSON" | jq -e 'type == "array" and all(.[]; type == "string")' >/dev/null 2>&1; then
  REASON="invalid-config"; emit; exit 0
fi
if ! [ -d "$REPO_DIR/$ROOT" ]; then
  REASON="invalid-config"; emit; exit 0
fi
JDK_NUM=$(printf '%s' "$JDK" | jq -r 'if . == null then "" else tostring end')
ARGS=()
while IFS= read -r a; do [ -n "$a" ] && ARGS+=("$a"); done < <(printf '%s' "$ARGS_JSON" | jq -r '.[]')

# 清掉工作树里既有的构建输出（缓存桶里可能残留——不得混入本次结论）
clean_outputs

# ---- JDK 定位（候选逐个核对主版本——javap 版本低于 class 文件版本时分析器静默回退，
#      所以"找到了一个 JDK"不够，必须是指定的那一个）----
# 候选顺序：BUILD_JAVA_HOME（本地冒烟）→ runner 的 JAVA_HOME_<v>_X64 → /usr/lib/jvm 通配
#   （JAVA_HOME_<v>_X64 由 scan.yml 的 setup-java 步按 build.yaml 的主版本导出——runner
#     镜像只预装部分 JDK；/usr/lib/jvm 仅作兜底）
#            → macOS java_home（逐架构——arm64 机器上不指定架构时它会回落到默认 JDK）
java_major() { # $1 = JDK 目录 → stdout 主版本号；取不到则非零
  local vv
  vv=$("$1/bin/javap" -version 2>/dev/null | awk '{print $NF}')
  [ -n "$vv" ] || return 1
  case "$vv" in 1.*) vv=${vv#1.} ;; esac
  echo "${vv%%.*}"
}
find_java_home() {
  local v="$1" cand a
  if [ -n "${BUILD_JAVA_HOME:-}" ]; then
    if [ -x "$BUILD_JAVA_HOME/bin/javac" ] && [ "$(java_major "$BUILD_JAVA_HOME")" = "$v" ]; then
      echo "$BUILD_JAVA_HOME"; return 0
    fi
    echo "build-step: BUILD_JAVA_HOME=$BUILD_JAVA_HOME 的主版本不是 ${v}（$(java_major "$BUILD_JAVA_HOME" 2>/dev/null || echo 未知)）——不采用" >&2
  fi
  eval "cand=\${JAVA_HOME_${v}_X64:-}"
  for cand in "$cand" /usr/lib/jvm/*-"${v}"-* /usr/lib/jvm/*-"${v}" /usr/lib/jvm/jdk-"${v}"*; do
    if [ -n "$cand" ] && [ -x "$cand/bin/javac" ] && [ "$(java_major "$cand")" = "$v" ]; then
      echo "$cand"; return 0
    fi
  done
  if [ -x /usr/libexec/java_home ]; then
    for a in arm64 x86_64 ""; do
      cand=$(/usr/libexec/java_home -v "$v" ${a:+-a "$a"} 2>/dev/null || true)
      if [ -n "$cand" ] && [ -x "$cand/bin/javac" ] && [ "$(java_major "$cand")" = "$v" ]; then
        echo "$cand"; return 0
      fi
    done
  fi
  return 1
}
if [ "$JDK" = "null" ] || ! JAVA_HOME_RES=$(find_java_home "$JDK_NUM"); then
  JAVA_HOME_RES=""; JDK="null"; REASON="jdk-not-found"; EXIT_CODE="null"
  clean_outputs; CLASS_JSON=$(count_classes); emit; exit 0
fi
export JAVA_HOME="$JAVA_HOME_RES"
export PATH="$JAVA_HOME/bin:$PATH"
JAVA_VER=$(java -version 2>&1 | sed -n 1p | sed -E 's/.*"([^"]+)".*/\1/')
JAVAP_VER=$(javap -version 2>/dev/null | sed -n 1p | awk '{print $NF}' || true)

TIMEOUT_BIN=$(command -v timeout || command -v gtimeout || true)
run_limited() { # run_limited <timeout-sec> <cmd...> → 退出码（超时记 124）
  local t="$1"; shift
  if [ -n "$TIMEOUT_BIN" ]; then "$TIMEOUT_BIN" "$t" "$@"; else "$@"; fi
}
detect_timeout() { [ "$1" = "124" ] && [ -n "$TIMEOUT_BIN" ]; }

# ---- 编译（主源码成功即 bytecode；测试源码编译尽力而为，失败只记录）----
to_json_array() { jq -Rn '[inputs]'; }
LOG=$(mktemp)
MAIN_RC=1; TEST_RC="null"; DUR_MAIN=0; DUR_TEST=0
t0=$(date +%s)
if [ "$TOOL" = "maven" ]; then
  MVN="mvn"; NTP=1
  if [ -x "$REPO_DIR/$ROOT/mvnw" ]; then
    MVN="./mvnw"
    # -ntp 自 Maven 3.6.1 起才有；老 wrapper 分发包不认这个参数
    wv=$(sed -nE 's/.*apache-maven-([0-9]+)\.([0-9]+)\.[0-9]+-(bin|all)\.zip.*/\1.\2/p' \
      "$REPO_DIR/$ROOT/.mvn/wrapper/maven-wrapper.properties" 2>/dev/null | head -1)
    if ! printf '%s' "$wv" | awk -F. '{exit !($1 > 3 || ($1 == 3 && $2 >= 6))}'; then NTP=0; fi
  fi
  MCMD=("$MVN" -B); [ "$NTP" = 1 ] && MCMD+=(-ntp)
  MCMD+=(-DskipTests ${ARGS[@]+"${ARGS[@]}"} compile)
  TCMD=("${MCMD[@]:0:${#MCMD[@]}-1}" test-compile)
else
  if [ ! -x "$REPO_DIR/$ROOT/gradlew" ]; then
    REASON="wrapper-not-found"; EXIT_CODE="null"
    CLASS_JSON=$(count_classes); emit; exit 0
  fi
  GCMD=(./gradlew --no-daemon -q --console=plain ${ARGS[@]+"${ARGS[@]}"} compileJava)
  TCMD=(./gradlew --no-daemon -q --console=plain ${ARGS[@]+"${ARGS[@]}"} compileTestJava)
  MCMD=("${GCMD[@]}")
fi
COMMAND_JSON=$(jq -cn --argjson m "$(printf '%s\n' "${MCMD[@]}" | to_json_array)" \
  --argjson t "$(printf '%s\n' "${TCMD[@]}" | to_json_array)" '[$m, $t]')
set +e
( cd "$REPO_DIR/$ROOT" && run_limited "$BUILD_TIMEOUT_SEC" "${MCMD[@]}" ) > "$LOG" 2>&1
MAIN_RC=$?
set -e
DUR_MAIN=$(( $(date +%s) - t0 ))
if [ "$MAIN_RC" = 0 ]; then
  t0=$(date +%s)
  set +e
  ( cd "$REPO_DIR/$ROOT" && run_limited "$BUILD_TEST_TIMEOUT_SEC" "${TCMD[@]}" ) >> "$LOG" 2>&1
  TEST_RC=$?
  set -e
  DUR_TEST=$(( $(date +%s) - t0 ))
fi
EXIT_CODE=$MAIN_RC
TEST_EXIT_CODE=$TEST_RC
DUR_JSON=$(jq -cn --argjson a "$DUR_MAIN" --argjson b "$DUR_TEST" '{compile:$a, testCompile:$b}')

if [ "$MAIN_RC" != 0 ]; then
  REASON="compile-failed"
  detect_timeout "$MAIN_RC" && REASON="compile-timeout"
  clean_outputs
elif detect_timeout "$TEST_RC"; then
  TEST_RC=124
fi
CLASS_JSON=$(count_classes)
if [ "$MAIN_RC" = 0 ]; then
  if [ "$(printf '%s' "$CLASS_JSON" | jq '.main + .test')" = 0 ]; then
    REASON="no-class-files"
  else
    MODE="bytecode"; REASON="compiled"
  fi
fi
take_log_tail
emit
exit 0
