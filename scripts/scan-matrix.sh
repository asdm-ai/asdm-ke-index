#!/usr/bin/env bash
# =============================================================================
# 扫描矩阵生成（scan.yml prepare 步）
# -----------------------------------------------------------------------------
# 用法：[SCAN_REPOS="owner/repo,owner/repo"] bash scripts/scan-matrix.sh
# 输出：单行 JSON {"include":[{owner, repo, branch, build}]}
#   build = build.yaml 里该仓的构建配置（{tool, jdk, root, args}），没有条目即 null
#   SCAN_REPOS 非空时只保留白名单内的仓（冒烟用：小范围重扫不惊动其余仓）；留空 = 全量
# 失败（非零退出）：build.yaml 引用了 repos.yaml 里不存在或被 skip 的仓，或配置不合法。
# 解析用 ruby stdlib YAML（runner 预装），与 scan.yml 既有做法一致。
# =============================================================================
set -euo pipefail
cd "$(dirname "$0")/.."

TOJSON='puts JSON.generate(YAML.load_file(ARGV[0]))'
REPOS=$(ruby -ryaml -rjson -e "$TOJSON" repos.yaml)
if [ -f build.yaml ]; then
  BUILDS=$(ruby -ryaml -rjson -e "$TOJSON" build.yaml)
else
  BUILDS='{"builds":[]}'
fi
SCAN_REPOS="${SCAN_REPOS:-}"

printf '%s' "$BUILDS" | jq -e '
  (.builds // []) | all(.[];
    has("owner") and has("repo")
    and (.tool == "maven" or .tool == "gradle")
    and (.jdk | type == "number")
    and ((has("root")) | not or (.root | type == "string"))
    and ((has("args")) | not or (.args | type == "array" and all(.[]; type == "string"))))' >/dev/null \
  || { echo "FAIL: build.yaml 配置不合法（tool 须为 maven|gradle，jdk 须为数字，args 须为字符串数组）" >&2; exit 1; }

BUILD_MAP=$(printf '%s' "$BUILDS" | jq -c '[(.builds // [])[] | {key: (.owner + "/" + .repo), value: {tool, jdk, root: (.root // "."), args: (.args // [])}}] | from_entries')

# build.yaml 的每个条目必须对应清单内未被 skip 的仓
MISSING=$(jq -r --argjson b "$BUILD_MAP" '
  [.repos[] | select((.skip // false) | not) | .owner + "/" + .repo] as $live
  | $b | keys[] | select(. as $k | ($live | index($k)) == null)' <(printf '%s' "$REPOS"))
if [ -n "$MISSING" ]; then
  echo "FAIL: build.yaml 引用了 repos.yaml 里不存在或被 skip 的仓：" >&2
  printf '%s\n' "$MISSING" >&2
  exit 1
fi

jq -cn --argjson repos "$REPOS" --argjson builds "$BUILD_MAP" --arg allow "$SCAN_REPOS" '
  def wanted($a; $o; $r): ($a == "") or any($a | gsub("[[:space:]]"; "") | split(",") | map(select(length > 0))[]; . == "\($o)/\($r)");
  {include: [$repos.repos[] | select((.skip // false) | not) | select(wanted($allow; .owner; .repo))
             | {owner, repo, branch: (.branch // ""), build: ($builds["\(.owner)/\(.repo)"] // null)}]}'
