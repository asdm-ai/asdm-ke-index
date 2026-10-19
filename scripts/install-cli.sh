#!/usr/bin/env bash
# =============================================================================
# KE CLI 安装（GitHub Actions Runner / 本地冒烟通用）
# -----------------------------------------------------------------------------
# 用法：KE_API_KEY=<key> bash scripts/install-cli.sh [安装目录]
#       （缺省安装目录 $PWD/ke-cli）
# 流程：manifest latest → 版本断言 → 下载 zip + .sha256 → 对账 → 解压 →
#       npm ci --omit=dev → bin/ke.cjs --version 断言（R6——锁 latest 并断言版本）
# 凭证：KE_API_KEY（最小权限 member key——仅下载通道 Bearer）
# =============================================================================
set -euo pipefail

: "${KE_API_KEY:?KE_API_KEY is required}"
KE_SERVER_URL="${KE_SERVER_URL:-https://console.kengine.ai}"
EXPECTED_VERSION="${EXPECTED_CLI_VERSION:-0.3.0}"
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

echo "== 版本断言 =="
VERSION=$(node "$DEST/bin/ke.cjs" --version)
echo "KE CLI version: $VERSION"
if [ "$VERSION" != "$EXPECTED_VERSION" ]; then
  echo "FAIL: ke --version $VERSION != expected $EXPECTED_VERSION" >&2
  exit 1
fi
echo "install-cli: OK → $DEST"
