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
# 聚合面：report.metrics 中 direction != "none" 的数值指标（A1/A2/A3/A4/
# B1.backend/B1.frontend/B2/B3/B4/C1/C2/C3/C4/D1）；D3 规模画像与 dq.*
# （direction 均为 "none"）为描述面——不进分位分母。
# 缺失语义：指标在某仓为 null（nullMetrics 区）或 value 非数值 → 该样本
# 不进分位分母，计入 missing 并标注仓列表（missingRepos）。
#
# 5.1.4.5 D2 cohort 聚合层：数据源 = 各 report metrics.D1.frameworkDeps——
# 逐框架跨仓版本分布 + 主版本众数份额（依赖同质度）；direction "none"
# 描述面（cohort 区，不进分位分母）。
#
# 按仓穿行验证 roll-up（2026-11-25 用户裁决）：数据源 = pipeline-status/
# {owner}/{repo}.json（scan job ⑤ annotate 确定性产物）——汇总各仓四子步
# （scan/projection/metrics/consistency）结论与 consistencyResult 分布；
# 单仓失败不阻断聚合（能聚合多少聚合多少）——reports 区聚合成功产物，
# validation 区汇总全部状态含失败仓（产品验证面）。
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
import re
import sys
from math import ceil

SCHEMA_VERSION = "draft-v1"
IMPLEMENTATION = "ke-index census.py (5.1.4: L2 aggregation + D2 cohort + per-repo pipeline validation roll-up)"

# 标准分位集（Schema §4.2）
PERCENTILES = [("p25", 0.25), ("p50", 0.50), ("p75", 0.75), ("p90", 0.90)]

# 穿行子步键（与 pipeline-status.sh 状态机对齐——ok/failed/skipped 三值）
PIPELINE_STEPS = ["scan", "projection", "metrics", "consistency"]
CONSISTENCY_RESULTS = ["pass", "mismatch", "error", "skipped"]


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


def load_statuses(status_dir):
    """读 pipeline-status/{owner}/{repo}.json → [(owner, repo, status)]。

    容错：单文件坏/缺失不阻断聚合（穿行裁决——聚合多少算多少，warn 后跳过）。
    """
    out = []
    for path in sorted(glob.glob(os.path.join(status_dir, "*", "*.json"))):
        owner = os.path.basename(os.path.dirname(path))
        repo = os.path.splitext(os.path.basename(path))[0]
        try:
            with open(path, encoding="utf-8") as f:
                out.append((owner, repo, json.load(f)))
        except (OSError, ValueError) as e:
            print("WARN: pipeline-status 不可读（跳过）%s：%s" % (path, e), file=sys.stderr)
    return out


def main():
    ap = argparse.ArgumentParser(description="KE Index census 聚合（N 守门）")
    ap.add_argument("--reports-dir", default="reports", help="report 目录（缺省 reports/）")
    ap.add_argument("--status-dir", default="pipeline-status",
                    help="穿行状态目录（缺省 pipeline-status/——validation roll-up 数据源）")
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

    # ---- 5.1.4.5 D2 cohort 聚合（依赖同质度——跨仓框架版本一致性）----
    # 数据源 = 各 report metrics.D1.frameworkDeps；仓代表版本 = 该仓命中的
    # 框架依赖中最大版本（同仓多版本记 mixedRepos 披露）；D2 总值 = 逐框架
    # 众数份额按使用仓数加权平均（direction "none"——cohort 描述面）。
    def _version_key(v):
        parts = re.split(r"[.\-_]", str(v))
        nums = []
        for p in parts:
            if p.isdigit():
                nums.append(int(p))
                continue
            lead = ""
            for ch in p:
                if ch.isdigit():
                    lead += ch
                else:
                    break
            if lead:
                nums.append(int(lead))
            break
        return tuple(nums)

    fw_repos = {}   # framework -> {rep_label: set(versions)}
    for owner, repo, r in reports:
        rep_label = "%s/%s" % (owner, repo)
        d1 = (r.get("metrics", {}) or {}).get("D1") or {}
        for fd in d1.get("frameworkDeps") or []:
            fw = fd.get("framework")
            if not fw:
                continue
            fw_repos.setdefault(fw, {}).setdefault(rep_label, set()).add(
                fd.get("version") or "")
    cohort_d2 = {}
    weighted = []
    for fw in sorted(fw_repos):
        per_repo = fw_repos[fw]
        users = {rep: vs for rep, vs in per_repo.items() if any(vs)}
        n = len(users)
        if n == 0:
            cohort_d2[fw] = {"reposUsing": 0}
            continue
        mixed = sum(1 for vs in users.values()
                    if len({v for v in vs if v}) > 1)
        version_count = {}
        for vs in users.values():
            rep_ver = max((v for v in vs if v), key=_version_key)
            version_count[rep_ver] = version_count.get(rep_ver, 0) + 1
        dominant, dom_count = max(sorted(version_count.items()), key=lambda kv: kv[1])
        share = round(dom_count / n, 6)
        weighted.append((n, dom_count))
        cohort_d2[fw] = {
            "reposUsing": n,
            "distinctVersions": len(version_count),
            "dominantVersion": dominant,
            "dominantShare": share,
            "mixedVersionRepos": mixed,
            "versionDistribution": dict(sorted(version_count.items())),
        }
    total_using = sum(n for n, _ in weighted)
    d2_overall = (round(sum(d for _, d in weighted) / total_using, 6)
                  if total_using else None)

    # ---- 按仓穿行验证 roll-up（2026-11-25——单仓失败不阻断聚合）----
    statuses = load_statuses(args.status_dir)
    step_counts = {k: {"ok": 0, "failed": 0, "skipped": 0} for k in PIPELINE_STEPS}
    cons_counts = {r: 0 for r in CONSISTENCY_RESULTS}
    overall_counts = {"pass": 0, "fail": 0}
    failed_repos = []
    for owner, repo, st in statuses:
        rep_label = "%s/%s" % (owner, repo)
        ov = st.get("overall")
        if ov in overall_counts:
            overall_counts[ov] += 1
        steps = st.get("steps") or {}
        bad_steps = []
        for k in PIPELINE_STEPS:
            v = steps.get(k)
            if v in step_counts[k]:
                step_counts[k][v] += 1
            if v != "ok":
                bad_steps.append("%s:%s" % (k, v or "missing"))
        cr = st.get("consistencyResult")
        if cr in cons_counts:
            cons_counts[cr] += 1
        if ov != "pass" and bad_steps:
            failed_repos.append({"repo": rep_label, "failedSteps": bad_steps})
    validation = {
        "reposWithStatus": len(statuses),
        "overall": overall_counts,
        "steps": step_counts,
        "consistencyResult": cons_counts,
        "failedRepos": sorted(failed_repos, key=lambda x: x["repo"]),
        "basis": "pipeline-status/{owner}/{repo}.json（scan job ⑤ annotate 确定性产物）——单仓失败不阻断聚合：reports 区聚合成功产物，本区汇总全部仓子步结论",
    }

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
        "validation": validation,
        "cohort": {
            "D2": {
                "id": "D2",
                "name": "dependency-homogeneity",
                "label": "依赖同质度",
                "domain": "D",
                "direction": "none",
                "value": d2_overall,
                "frameworks": cohort_d2,
                "basis": "逐框架主版本众数份额（仓代表版本 = 命中依赖最大版本）按使用仓数加权平均",
            },
        },
    }

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print("census written: %s（status=%s samples=%d metrics=%d）" % (
        args.out, status, samples, len(metrics_out)))
    print("validation: repos=%d pass=%d fail=%d | consistency pass/mismatch/error/skipped = %d/%d/%d/%d" % (
        len(statuses), overall_counts["pass"], overall_counts["fail"],
        cons_counts["pass"], cons_counts["mismatch"], cons_counts["error"], cons_counts["skipped"]))
    if failed_repos:
        print("failed repos: %s" % ", ".join(f["repo"] for f in failed_repos))
    for mid in sorted(metrics_out):
        m = metrics_out[mid]
        print("  %s: N=%d missing=%d mean=%s" % (mid, m["N"], m["missing"], m["mean"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
