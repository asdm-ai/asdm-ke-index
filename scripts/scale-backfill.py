#!/usr/bin/env python3
# =============================================================================
# KE Index · 仓规模补齐（存量 report 一次性回填 metrics.D3.scale）
# -----------------------------------------------------------------------------
# 用法：
#   python3 scripts/scale-backfill.py --repo <检出目录> --report reports/<owner>/<repo>.json
#   环境（可选）：KE_SERVER_URL / KE_API_KEY——齐备时做服务端 Repository.fileCount
#   对照（与扫描轨同判据）；缺失时对照置 null 并注记（fail-open）。
# 背景：仓规模采集（文件数 / 行数）2026-11-26 接入扫描轨（scan-one.sh clone 后
#   repo-scale.py）——此前落库的 report 无 D3.scale。preflight 零漂移短路下，
#   上游 HEAD 未前移的仓不会被重扫 → report 不重生成 → 只能靠本脚本按
#   report.snapshot.sourceHead 检出同一提交补采（确定性：同一提交逐字节同值，
#   与"当时扫描时采集"等价）。不碰服务端快照 / 投影 / 其它指标区。
# 前置（workflow 负责）：检出目录 HEAD 必须就是 report.snapshot.sourceHead
#   （git fetch --depth 1 origin <sha>）——本脚本二次断言，不等即 FAIL。
# 幂等：report 已有 D3.scale 时直接跳过（exit 0，不改文件）。
# D3.scale 形状与扫描轨同源：复用 compute-metrics.py scale_block（单一形状
#   来源），仅 collectedBy 标为 backfill。
# 依赖：Python 3.8+ 标准库 + git。
# =============================================================================
import argparse
import importlib.machinery
import importlib.util
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_module(filename, module_name):
    loader = importlib.machinery.SourceFileLoader(module_name, os.path.join(SCRIPT_DIR, filename))
    spec = importlib.util.spec_from_loader(module_name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class _NoServer:
    """未配置服务端凭据时的占位——compute-metrics.scale_block 对查询失败 fail-open。"""

    def __init__(self, error_cls):
        self.error_cls = error_cls

    def query(self, obj_type, fields, snapshot_id):
        raise self.error_cls("补齐轨未配置 KE_SERVER_URL / KE_API_KEY——跳过服务端 fileCount 对照")


def main():
    ap = argparse.ArgumentParser(description="KE Index 仓规模补齐（回填 report D3.scale）")
    ap.add_argument("--repo", required=True, help="源仓检出目录（HEAD = report.snapshot.sourceHead）")
    ap.add_argument("--report", required=True, help="report 路径（reports/<owner>/<repo>.json）")
    args = ap.parse_args()

    repo_scale = _load_module("repo-scale.py", "repo_scale")
    compute_metrics = _load_module("compute-metrics.py", "compute_metrics")

    try:
        with open(args.report, encoding="utf-8") as fh:
            report = json.load(fh)
    except (OSError, ValueError) as e:
        print("FAIL: report 不可读 %s：%s" % (args.report, e), file=sys.stderr)
        return 1
    snap = report.get("snapshot") or {}
    d3 = ((report.get("metrics") or {}).get("D3")) or {}
    if compute_metrics._is_int((d3.get("scale") or {}).get("fileCount")):
        print("backfill: %s 已有 D3.scale（fileCount=%d）——跳过" % (args.report, d3["scale"]["fileCount"]))
        return 0

    anchor = snap.get("sourceHead") or snap.get("sourceVersion") or ""
    if not isinstance(anchor, str) or len(anchor) != 40 or any(c not in "0123456789abcdef" for c in anchor):
        print("FAIL: %s 的 snapshot.sourceHead/sourceVersion 不是完整提交 sha（%r）——无法定锚补采"
              % (args.report, anchor), file=sys.stderr)
        return 1

    try:
        scale = repo_scale.measure(args.repo)
    except (RuntimeError, OSError) as e:
        print("FAIL: repo-scale：%s" % e, file=sys.stderr)
        return 1
    if scale.get("sourceHead") != anchor:
        print("FAIL: 检出目录 HEAD=%s != report 定锚提交 %s（补采对象错位）"
              % (scale.get("sourceHead"), anchor), file=sys.stderr)
        return 1

    url = os.environ.get("KE_SERVER_URL")
    token = os.environ.get("KE_API_KEY")
    if url and token:
        ke = compute_metrics.KeCli("ke", url, token)
    else:
        ke = _NoServer(compute_metrics.KeError)
    snap_id = snap.get("snapshotId")
    if not snap_id:
        print("FAIL: %s 的 snapshot.snapshotId 缺失——无法键控服务端对照" % args.report, file=sys.stderr)
        return 1
    block = compute_metrics.scale_block(ke, snap_id, scale)
    block["collectedBy"] = "backfill"
    d3["scale"] = block

    with open(args.report, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print("backfill: %s ← D3.scale（fileCount=%d javaFiles=%d lineCount=%d javaLines=%d serverFileCount=%s match=%s）" % (
        args.report, block["fileCount"], block["javaFiles"], block["lineCount"], block["javaLines"],
        block["serverFileCount"], block["fileCountMatch"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
