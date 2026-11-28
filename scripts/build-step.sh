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
#             logTail（末 60 行编译输出——定位失败用；不进 docs，只入库 build/）/
#             httpRepositories（Maven 明文 HTTP 仓库被拦后带覆盖配置重试过 =
#             unblocked-on-retry；其余 null——见下方"明文 HTTP 仓库"注记）/
#             transientRetry（编译因瞬时传输失败——429 限流 / 传输中断——退避后按原命令
#             重试过 = retried-once；其余 null——见下方"瞬时传输失败"注记）
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
BUILD_RETRY_DELAY_SEC="${BUILD_RETRY_DELAY_SEC:-60}"

MODE="source"; REASON="not-configured"
TOOL=""; JDK="null"; ROOT="."
JAVA_HOME_RES=""; JAVA_VER=""; JAVAP_VER=""
COMMAND_JSON="[]"; EXIT_CODE="null"; TEST_EXIT_CODE="null"
CLASS_JSON='{"main":0,"test":0,"other":0}'
DUR_JSON='{"compile":0,"testCompile":0}'
LOG_TAIL_JSON="[]"
LOG=""
HTTP_REPOSITORIES=""
TRANSIENT_RETRY=""
MVN_SETTINGS=""
# 必须恒返回 0：EXIT 陷阱的返回值在部分 bash 版本里会覆盖脚本自己的 exit 状态
cleanup() {
  if [ -n "$LOG" ] && [ -f "$LOG" ]; then rm -f "$LOG"; fi
  if [ -n "$MVN_SETTINGS" ] && [ -f "$MVN_SETTINGS" ]; then rm -f "$MVN_SETTINGS"; fi
  return 0
}
trap cleanup EXIT

emit() {
  jq -n \
    --argjson configured "$CONFIGURED" \
    --arg mode "$MODE" --arg reason "$REASON" \
    --arg tool "$TOOL" --argjson jdk "$JDK" --arg root "$ROOT" \
    --arg javaHome "$JAVA_HOME_RES" --arg javaVersion "$JAVA_VER" --arg javapVersion "$JAVAP_VER" \
    --arg httpRepositories "$HTTP_REPOSITORIES" \
    --arg transientRetry "$TRANSIENT_RETRY" \
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
      httpRepositories: (if $httpRepositories == "" then null else $httpRepositories end),
      transientRetry: (if $transientRetry == "" then null else $transientRetry end),
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

# ---- Maven 明文 HTTP 仓库（Maven 3.8.1+ 内置镜像 maven-default-http-blocker）----
# 有些仓在 pom 里声明 http:// 仓库（如 maven.aliyun.com 的旧地址），Maven 自 3.8.1 起
# 默认一律拦截——"Blocked mirror for repositories"，连父 POM 都读不到。缺省不放开：
# 首次编译因此失败时，带一份只覆盖该 blocker 的用户级 settings（-s，同 id 镜像覆盖
# 全局 settings 里的 blocker，其余配置不动）重试一次，并在记录里标注
# httpRepositories=unblocked-on-retry；重试仍失败 → 照常 compile-failed 回退。
# 依据：编译第三方仓本身就在执行它的构建脚本，放开明文下载不构成新增风险。
write_maven_http_settings() { # $1 = settings 输出路径
  cat > "$1" <<'XML'
<settings xmlns="http://maven.apache.org/SETTINGS/1.0.0">
  <mirrors>
    <mirror>
      <id>maven-default-http-blocker</id>
      <mirrorOf>ke-index-no-repository-matches</mirrorOf>
      <url>http://0.0.0.0/</url>
    </mirror>
  </mirrors>
</settings>
XML
}
blocked_by_http_mirror() { # 编译日志里是否出现 blocker 的报错
  [ -n "$LOG" ] && [ -f "$LOG" ] && grep -q -e 'maven-default-http-blocker' -e 'Blocked mirror for repositories' "$LOG"
}

# ---- 瞬时传输失败（下载被限流 / 传输中断）----
# 构建子步没有依赖缓存，每次冷编译都从中央仓库全量拉取。GitHub runner 的出口被
# Maven Central 限流（HTTP 429）或传输中断时，与仓内构建配置无关的任何仓都会回退——
# run #42 lenve/vhr 实证：拉父 POM 时 "status code: 429 … Too Many Requests"，33s 失败，
# 不改配置重跑即 compiled。处置与上面的明文 HTTP 仓库重试同一形态：编译失败且日志里
# 出现瞬时传输失败的报错 → 退避 BUILD_RETRY_DELAY_SEC 后按原命令重试一次，记录
# transientRetry=retried-once；重试仍失败 → 照常 compile-failed 回退。
# 标记只取"下载本身失败"的措辞（Maven 与 Gradle 两种），编译报错、找不到依赖、
# 版本冲突等确定性失败不会命中，不被重试。
# 超时（exit 124）不在此列：日志末尾未必有传输报错，且一次就已用满时间上限。
transient_transfer_failure() { # 编译日志里是否出现瞬时传输失败的报错
  [ -n "$LOG" ] && [ -f "$LOG" ] && grep -q -e 'status code: 429' -e 'Too Many Requests' \
    -e 'Could not transfer artifact' -e 'Connection reset' -e 'Read timed out' \
    -e "Could not GET '" -e "Could not HEAD '" "$LOG"
}
transient_marker() { # 命中的第一条措辞（写进 job 日志——重试会覆盖编译日志）
  { grep -o -e 'status code: 429' -e 'Too Many Requests' -e 'Could not transfer artifact' \
      -e 'Connection reset' -e 'Read timed out' -e "Could not GET '" -e "Could not HEAD '" "$LOG" || true; } | head -1
}

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
    # （没有 .mvn/wrapper/maven-wrapper.properties 时 sed 非零——pipefail 下必须吞掉，
    #   否则脚本在此中止、既不出记录也不回退）
    wv=$({ sed -nE 's/.*apache-maven-([0-9]+)\.([0-9]+)\.[0-9]+-(bin|all)\.zip.*/\1.\2/p' \
      "$REPO_DIR/$ROOT/.mvn/wrapper/maven-wrapper.properties" 2>/dev/null || true; } | head -1)
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
if [ "$MAIN_RC" != 0 ] && [ "$TOOL" = "maven" ] && blocked_by_http_mirror; then
  MVN_SETTINGS=$(mktemp)
  write_maven_http_settings "$MVN_SETTINGS"
  HTTP_REPOSITORIES="unblocked-on-retry"
  echo "build-step: Maven 拦截了 pom 声明的明文 HTTP 仓库——带 blocker 覆盖配置重试一次（记录 httpRepositories=unblocked-on-retry）"
  # 选项位置无所谓：mvn [--settings <file>] <原参数…> <goal>
  MCMD=("${MCMD[0]}" --settings "$MVN_SETTINGS" "${MCMD[@]:1}")
  TCMD=("${MCMD[@]:0:${#MCMD[@]}-1}" test-compile)
  COMMAND_JSON=$(jq -cn --argjson m "$(printf '%s\n' "${MCMD[@]}" | to_json_array)" \
    --argjson t "$(printf '%s\n' "${TCMD[@]}" | to_json_array)" '[$m, $t]')
  set +e
  ( cd "$REPO_DIR/$ROOT" && run_limited "$BUILD_TIMEOUT_SEC" "${MCMD[@]}" ) > "$LOG" 2>&1
  MAIN_RC=$?
  set -e
fi
# 瞬时传输失败：退避后按原命令（含上面可能加上的 --settings）重试一次
if [ "$MAIN_RC" != 0 ] && ! detect_timeout "$MAIN_RC" && transient_transfer_failure; then
  TRANSIENT_RETRY="retried-once"
  echo "build-step: 编译因瞬时传输失败中止（$(transient_marker)）——${BUILD_RETRY_DELAY_SEC}s 后按原命令重试一次（记录 transientRetry=retried-once）"
  sleep "$BUILD_RETRY_DELAY_SEC"
  set +e
  ( cd "$REPO_DIR/$ROOT" && run_limited "$BUILD_TIMEOUT_SEC" "${MCMD[@]}" ) > "$LOG" 2>&1
  MAIN_RC=$?
  set -e
fi
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
