#!/usr/bin/env bash
# =============================================================================
# KE CLI 安装（GitHub Actions Runner / 本地冒烟通用）
# -----------------------------------------------------------------------------
# 用法：KE_API_KEY=<key> bash scripts/install-cli.sh [安装目录]
#       （缺省安装目录 $PWD/ke-cli）
# 流程：manifest latest → 版本断言 → 下载 zip + .sha256 → 对账 → 解压 →
#       npm ci --omit=dev → bin/ke symlink → ke --version 断言（R6——锁 latest 并断言版本）
# 调用形态：安装后以 ke 指令统一调用（bin/ 内制品文件名为 ke.cjs——npm bin 契约
#       声明 ke 入口但私有 zip 分发不走 npm 全局装配，故手工建 symlink；
#       调用方负责将 <安装目录>/bin 注入 PATH，如 GITHUB_PATH / export PATH）
# 凭证：KE_API_KEY（最小权限 member key——仅下载通道 Bearer）
# =============================================================================
set -euo pipefail

: "${KE_API_KEY:?KE_API_KEY is required}"
KE_SERVER_URL="${KE_SERVER_URL:-https://console.kengine.ai}"
# 版本锚点随生产发版联动升级（R6）：0.3.10 = 1.3.9-1125-002（0→1 执行计划
# B1/B2——投影并发治理 + deferProjection + ke project + fetch failed 自愈）
# （0.3.9 = 1.3.9-1122-001（Part02 第二轮 Hotfix-5/6/7/9）；
#   0.3.8 = 1.3.9-1121-002 applyOpsMysql spread 爆栈修复——Hotfix-4；
#   @TableName / BaseMapper 泛型 / @Select 注解三轨——A3/A4 口径修正；0.3.4 重扫
#   run 43804026050 发现渐进轨伪投影缺 MP 三字段后递增重发，0.3.4 制品已放量不覆盖）
EXPECTED_VERSION="${EXPECTED_CLI_VERSION:-0.3.10}"
DEST="${1:-$PWD/ke-cli}"

if command -v shasum >/dev/null 2>&1; then
  SHASUM="shasum -a 256"
else
  SHASUM="sha256sum"
fi

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

echo "== manifest（${KE_SERVER_URL}）=="
MANIFEST=$(curl -fsSL -H "Authorization: Bearer $KE_API_KEY" "$KE_SERVER_URL/api/downloads/cli/manifest")
ZIP_NAME=$(printf '%s' "$MANIFEST" | jq -r '.latest')
MANIFEST_VERSION=$(printf '%s' "$MANIFEST" | jq -r '.version')
echo "latest=$ZIP_NAME version=$MANIFEST_VERSION"
if [ "$MANIFEST_VERSION" != "$EXPECTED_VERSION" ]; then
  echo "FAIL: manifest version $MANIFEST_VERSION != expected $EXPECTED_VERSION" >&2
  exit 1
fi

curl -fsSL -H "Authorization: Bearer $KE_API_KEY" -o "$TMP/$ZIP_NAME" "$KE_SERVER_URL/api/downloads/cli/$ZIP_NAME"
curl -fsSL -H "Authorization: Bearer $KE_API_KEY" -o "$TMP/$ZIP_NAME.sha256" "$KE_SERVER_URL/api/downloads/cli/$ZIP_NAME.sha256"

echo "== sha256 对账 =="
(cd "$TMP" && $SHASUM -c "$ZIP_NAME.sha256")

echo "== 解压 + 安装依赖（npm ci --omit=dev）=="
mkdir -p "$DEST"
unzip -q -o "$TMP/$ZIP_NAME" -d "$DEST"
(cd "$DEST" && npm ci --omit=dev --no-fund --no-audit --silent)

# ke 指令入口：制品 bin/ 内文件名为 ke.cjs（package.json bin 契约声明 ke，
# 但私有 zip 分发不产生 npm 全局装配的 symlink）——手工建相对 symlink，
# 调用方将 $DEST/bin 注入 PATH 后即可 ke 指令调用
ln -sf ke.cjs "$DEST/bin/ke"

echo "== 版本断言（ke 指令形态）=="
VERSION=$(PATH="$DEST/bin:$PATH" ke --version)
echo "KE CLI version: $VERSION"
if [ "$VERSION" != "$EXPECTED_VERSION" ]; then
  echo "FAIL: ke --version $VERSION != expected $EXPECTED_VERSION" >&2
  exit 1
fi
echo "install-cli: OK → $DEST（ke 指令入口：$DEST/bin/ke）"