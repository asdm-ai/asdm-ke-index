#!/usr/bin/env python3
# =============================================================================
# KE Index · census 聚合（L2 cohort 层——分位守门）
# -----------------------------------------------------------------------------
# 用法（GitHub Actions 与本地复算同形）：
#   python3 scripts/census.py [--reports-dir reports] [--out census/summary.json]
#
# 输入：reports/{owner}/{repo}.json（compute-metrics.py 产物）
# 输出：census/summary.json——按指标聚合 N / mean / P25 / P50 / P75 / P90
#
# 守门口径（P2-D10 / P2H-D6——两个门槛显式区分，不混用）：
#   - 发布门槛（统计充分性）：总样本 N >= publishThreshold(30) → status
#     "published"，出 mean 与标准分位集；N < 30 → status "accumulating"，
#     每指标仅出样本计数与缺失标注，统计量全部置 null（不出分位）
#   - 隐私护栏（k-匿名，单指标级）：published 状态下指标切片 N < privacyFloor(5)
#     → 该指标整组不出分位（Schema §4.2——开源公开数据本不涉隐私，
#     护栏按 Schema 口径保留并显式标注）
#
# 聚合面：report.metrics 中 direction != "none" 的数值指标（A2/A3/A4/
# B1.backend/B1.frontend/B2/B3/B4/C2/C3/C4）；D3 规模画像、D2 cohort 级
# 指标与 dq.*（direction 均为 "none"）为描述面——不进分位分母。
# 缺失语义：指标在某仓为 null（nullMetrics 区）或 value 非数值 → 该样本
# 不进分位分母，计入 missing 并标注仓列表（missingRepos）。
#
# 分位算法：nearest-rank（Schema §4.2——升序第 ceil(p*N) 个值）。
# 输出确定性：同一批 report 产出逐字节一致的 summary（不含墙钟时间戳）。
#
# 依赖：Python 3.8+ 标准库（零第三方依赖）。
# =============================================================================
import argparse
import glob
import json
import os
import sys
from math import ceil

SCHEMA_VERSION = "draft-v1"
IMPLEMENTATION = "ke-index census.py (transitional; L2 aggregation over compute-metrics reports)"

# 标准分位集（Schema §4.2）
PERCENTILES = [("p25", 0.25), ("p50", 0.50), ("p75", 0.75), ("p90", 0.90)]


def nearest_rank(sorted_vals, p):
    """nearest-rank 分位：升序第 ceil(p*N) 个值（Schema §4.2 口径）。"""
    n = len(sorted_vals)
    if n == 0:
        return None
    idx = max(1, ceil(p * n))
    return sorted_vals[min(idx, n) - 1]


def is_number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def load_reports(reports_dir):
    """读 reports/{owner}/{repo}.json → [(owner, repo, report)]（排序保确定性）。"""
    out = []
    for path in sorted(glob.glob(os.path.join(reports_dir, "*", "*.json"))):
        owner = os.path.basename(os.path.dirname(path))
        repo = os.path.splitext(os.path.basename(path))[0]
        try:
            with open(path, encoding="utf-8") as f:
                out.append((owner, repo, json.load(f)))
        except (OSError, ValueError) as e:
            print("FAIL: report 不可读 %s：%s" % (path, e), file=sys.stderr)
            sys.exit(1)
    return out


def main():
    ap = argparse.ArgumentParser(description="KE Index census 聚合（N 守门）")
    ap.add_argument("--reports-dir", default="reports", help="report 目录（缺省 reports/）")
    ap.add_argument("--out", default="census/summary.json", help="输出文件（缺省 census/summary.json）")
    ap.add_argument("--publish-threshold", type=int, default=30, help="发布门槛（统计充分性——P2-D10）")
    ap.add_argument("--privacy-floor", type=int, default=5, help="k-匿名隐私护栏（单指标级——Schema §4.2）")
    args = ap.parse_args()

    reports = load_reports(args.reports_dir)
    if not reports:
        print("FAIL: %s 下无 report（先跑 compute-metrics.py）" % args.reports_dir, file=sys.stderr)
        return 1
    samples = len(reports)

    # ---- 守门判定（两个门槛显式区分）----
    published = samples >= args.publish_threshold
    status = "published" if published else "accumulating"
    status_reason = (
        "N=%d >= %d（统计充分——发布分位）" % (samples, args.publish_threshold)
        if published
        else "N=%d < %d（accumulating——不出分位，仅样本计数与缺失标注）" % (samples, args.publish_threshold)
    )

    # ---- 仓库索引（README 索引表数据源）----
    repo_index = []
    for owner, repo, r in reports:
        snap = r.get("snapshot", {})
        repo_index.append({
            "owner": owner,
            "repo": repo,
            "sourceId": r.get("sourceId", repo),
            "snapshotId": snap.get("snapshotId"),
            "objectCount": snap.get("objectCount"),
            "linkCount": snap.get("linkCount"),
            "schemaVersion": r.get("schemaVersion"),
        })

    # ---- 按指标聚合 ----
    # 聚合面 = metrics 区 direction != "none"（跨仓收集指标元数据 + 样本值/缺失）
    agg = {}  # metric_id -> {meta..., values: [], missing: [(owner/repo, reason)]}
    for owner, repo, r in reports:
        rep_label = "%s/%s" % (owner, repo)
        metrics = r.get("metrics", {})
        nulls = r.get("nullMetrics", {})
        for mid, m in metrics.items():
            if m.get("direction") == "none":
                continue
            entry = agg.setdefault(mid, {
                "name": m.get("name"), "label": m.get("label"),
                "domain": m.get("domain"), "direction": m.get("direction"),
                "values": [], "missing": [],
            })
            v = m.get("value")
            if is_number(v):
                entry["values"].append(v)
            else:
                entry["missing"].append((rep_label, "metrics 区 value 非数值"))
        for mid, m in nulls.items():
            if m.get("direction") == "none":
                continue
            entry = agg.setdefault(mid, {
                "name": m.get("name"), "label": m.get("label"),
                "domain": m.get("domain"), "direction": m.get("direction"),
                "values": [], "missing": [],
            })
            entry["missing"].append((rep_label, m.get("reason", "null")))

    metrics_out = {}
    for mid in sorted(agg):
        e = agg[mid]
        vals = sorted(e["values"])
        n = len(vals)
        privacy_blocked = published and n < args.privacy_floor
        entry = {
            "id": mid,
            "name": e["name"],
            "label": e["label"],
            "domain": e["domain"],
            "direction": e["direction"],
            "N": n,
            "missing": len(e["missing"]),
            "missingRepos": [
                {"repo": rep, "reason": reason} for rep, reason in sorted(e["missing"])
            ],
            # 统计量（守门：accumulating 全 null；published 且 N>=privacyFloor 出值）
            "mean": round(sum(vals) / n, 6) if (published and not privacy_blocked and n) else None,
            "percentiles": (
                {k: nearest_rank(vals, p) for k, p in PERCENTILES}
                if published and not privacy_blocked and n else None
            ),
            "percentileMethod": "nearest-rank (Schema §4.2)",
        }
        if privacy_blocked:
            entry["gateNote"] = "k-匿名隐私护栏：切片 N=%d < %d，整组不出分位（与发布门槛显式区分）" % (
                n, args.privacy_floor)
        metrics_out[mid] = entry

    summary = {
        "schemaVersion": SCHEMA_VERSION,
        "implementation": IMPLEMENTATION,
        "status": status,
        "samples": samples,
        "gate": {
            "publishThreshold": args.publish_threshold,
            "privacyFloor": args.privacy_floor,
            "statusReason": status_reason,
            "note": "publishThreshold 为统计充分性门槛（P2-D10）；privacyFloor 为 k-匿名隐私护栏（Schema §4.2）——两者显式区分，不混用",
        },
        "repos": repo_index,
        "metrics": metrics_out,
    }

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print("census written: %s（status=%s samples=%d metrics=%d）" % (
        args.out, status, samples, len(metrics_out)))
    for mid in sorted(metrics_out):
        m = metrics_out[mid]
        print("  %s: N=%d missing=%d mean=%s" % (mid, m["N"], m["missing"], m["mean"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
