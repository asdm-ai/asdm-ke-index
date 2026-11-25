#!/usr/bin/env python3
# =============================================================================
# KE Index · 5.1.4.4 图查询形态指标（expand 闭包 + 图查询优先遥测闭环）
# -----------------------------------------------------------------------------
# 用法（与 compute-metrics.py 同形——GitHub Actions 与本地复算一致）：
#   KE_SERVER_URL=https://... KE_API_KEY=... python3 scripts/graph-metrics.py \
#     --owner lenve --repo vhr \
#     [--source-id vhr] [--snapshot <id>] [--ke-cli "ke"] \
#     [--out reports/lenve/vhr.graph.json] \
#     [--compare reports/lenve/vhr.json]     # 双路径等价性比对（V5.1.4.4 判据）
#
# 与 compute-metrics.py（V5.1.4.3 本地 BFS 形态）的关系：
#   - 本脚本 = 图查询形态：逐 ApiEndpoint 的 backendMethod 走 expand 端点
#     （direction=out × linkTypes=calls × depth≤10），A1/C1 口径完全一致；
#   - 使命（P2-D16）：每轮指标计算 = 一次图查询引擎真实压测——route 分布 /
#     p50 / p95 / truncated 计数 / 投影就绪延迟全部落 evidence（遥测闭环）；
#   - --compare：与本地形态结果逐位比对（graph-accelerated vs MySQL 直查的
#     双路径功能等价性验证——引擎稳定性日常验证）。
#
# 口径（V5.1.4.1 定案——与 compute-metrics.py 同源）：
#   - A1 分母 = 全部 ApiEndpoint（含无 backendMethodId——与 A2 互补）
#   - C1 跳数 = calls 边数（BFS 层；多链取最短）；expand depth 上限 10
#   - truncated 单独计数不判 FAIL（深度截断链如实计入 evidence）
#   - canary 超时（缺省 300s）走兜底仍出指标且 route 如实记录
#
# 依赖：Python 3.8+ 标准库；ke CLI 0.3.0+（server 模式——快照解析与明细拉取）。
# =============================================================================
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from math import ceil

SCHEMA_VERSION = "draft-v1"
IMPLEMENTATION = "ke-index graph-metrics.py (5.1.4.4: expand closure + graph-first telemetry loop)"

DEPTH_MAX = 10            # V5.1.4.1：expand depth 上限（契约硬顶同值）
LIMIT_MAX = 50000         # 契约 limit 硬顶
CANARY_INTERVAL_S = 10


def parse_json_block(text):
    text = text.strip()
    try:
        return json.loads(text)
    except ValueError:
        pass
    for i, ch in enumerate(text):
        if ch in "[{":
            try:
                obj, _ = json.JSONDecoder().raw_decode(text[i:])
                return obj
            except ValueError:
                continue
    raise RuntimeError("ke 输出中未找到可解析的 JSON 块：%.200s" % text)


class KeCli:
    def __init__(self, ke_cli, url, token):
        argv = []
        for piece in (ke_cli or "ke").split():
            argv.append(piece)
        self.argv = argv
        self.conn = ["--mode", "server", "--url", url, "--token", token]

    def run_json(self, args):
        argv = self.argv + self.conn + args
        p = subprocess.run(argv, capture_output=True, text=True, timeout=900)
        if p.returncode != 0:
            raise RuntimeError("ke %s 失败（rc=%s）：%s" % (
                " ".join(args), p.returncode, p.stderr.strip()[:300]))
        return parse_json_block(p.stdout)

    def query(self, obj_type, fields, snapshot_id):
        out = self.run_json(["query", obj_type, "--all", "--field", ",".join(fields),
                             "--snapshot", snapshot_id])
        if not isinstance(out, list):
            raise RuntimeError("ke query %s 输出非数组" % obj_type)
        return out

    def snapshot_list(self, source_id):
        out = self.run_json(["snapshot", "list", "--repo", source_id])
        return out.get("snapshots", [])


def http_json(url, token, timeout=120):
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + token})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def strip_type_prefix(node_id):
    return node_id.split(":", 1)[1] if ":" in node_id else node_id


def declaring_fqn(method_id):
    fqn = strip_type_prefix(method_id)
    return fqn.rsplit(".", 1)[0] if "." in fqn else ""


def nearest_rank(sorted_vals, p):
    n = len(sorted_vals)
    if n == 0:
        return None
    idx = max(1, ceil(p * n))
    return sorted_vals[min(idx, n) - 1]


def expand_call(base, token, seed, snapshot_id, depth=DEPTH_MAX, limit=LIMIT_MAX):
    """单次 expand 查询（direction=out × linkTypes=calls；snapshotId 显式键控）。
    返回 (response|None, elapsed_ms, http_status)——404 种子不存在返回 None。"""
    qs = urllib.parse.urlencode({
        "seed": seed, "direction": "out", "linkTypes": "calls",
        "depth": depth, "limit": limit, "snapshotId": snapshot_id,
    })
    url = "%s/api/ontology/expand?%s" % (base, qs)
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + token})
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        return body, int((time.monotonic() - t0) * 1000), 200
    except urllib.error.HTTPError as e:
        return None, int((time.monotonic() - t0) * 1000), e.code


def closure_from_expand(resp, mapper_by_ns):
    """expand 响应 → (first_table_level, mapper_methods)。
    levels 升序扫描（响应构造序保证）；种子自身（level 0）先行判 join。
    first_table_level = 首个'所属 Mapper 带 mappedTableIds'方法的层；None=未贯通。"""
    first = None
    mapper_methods = 0
    seed_check = mapper_by_ns.get(declaring_fqn(resp.get("seed") or ""))
    if seed_check is not None:
        mapper_methods += 1
        if first is None and (seed_check.get("mappedTableIds") or []):
            first = 0
    levels = resp.get("levels") or []
    for bucket in sorted(levels, key=lambda b: b.get("depth") or 0):
        for nid in bucket.get("nodeIds") or []:
            mp = mapper_by_ns.get(declaring_fqn(nid))
            if mp is None:
                continue
            mapper_methods += 1
            if first is None and (mp.get("mappedTableIds") or []):
                first = bucket.get("depth")
    return first, mapper_methods


def main():
    ap = argparse.ArgumentParser(description="KE Index 图查询形态指标（5.1.4.4）")
    ap.add_argument("--owner", required=True)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--source-id", default=None)
    ap.add_argument("--snapshot", default=None)
    ap.add_argument("--ke-cli", default="ke")
    ap.add_argument("--url", default=os.environ.get("KE_SERVER_URL"))
    ap.add_argument("--token", default=os.environ.get("KE_API_KEY"))
    ap.add_argument("--out", default=None, help="输出文件（缺省 reports/{owner}/{repo}.graph.json）")
    ap.add_argument("--compare", default=None, help="本地形态 report JSON（双路径等价性比对）")
    ap.add_argument("--canary-timeout", type=int, default=300,
                    help="投影就绪 canary 超时秒数（V5.1.4.1：超时走兜底仍出指标）")
    args = ap.parse_args()

    if not args.url or not args.token:
        print("FAIL: 需要 --url/--token（或导出 KE_SERVER_URL / KE_API_KEY）", file=sys.stderr)
        return 1
    base = args.url.rstrip("/")
    source_id = args.source_id or args.repo
    out_path = args.out or os.path.join("reports", args.owner, "%s.graph.json" % args.repo)

    ke = KeCli(args.ke_cli, args.url, args.token)

    # ---- 快照解析（与 compute-metrics.py 同形）----
    snaps = ke.snapshot_list(source_id)
    complete = [s for s in snaps if s.get("status") == "complete"]
    if args.snapshot:
        target = next((s for s in complete if s.get("snapshotId") == args.snapshot), None)
    else:
        target = max(complete, key=lambda s: (s.get("completedAt") or s.get("createdAt") or "")) if complete else None
    if target is None:
        print("FAIL: source %s 无可用 complete 快照" % source_id, file=sys.stderr)
        return 1
    snap_id = target["snapshotId"]
    print("target snapshot: %s" % snap_id)

    apis = ke.query("ApiEndpoint", ["id", "backendMethodId"], snap_id)
    mappers = ke.query("Mapper", ["id", "namespace", "mappedTableIds"], snap_id)
    mapper_by_ns = {m["namespace"]: m for m in mappers if m.get("namespace")}
    if not apis:
        result = {
            "schemaVersion": SCHEMA_VERSION, "implementation": IMPLEMENTATION,
            "owner": args.owner, "repo": args.repo, "sourceId": source_id,
            "snapshotId": snap_id,
            "skipped": "无 ApiEndpoint 对象（A1/C1 分母为 0——图查询形态无对象面）",
        }
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print("graph-metrics: skipped（无 ApiEndpoint）")
        return 0

    # ---- canary：投影就绪探测（expand 单发看 route；graph-accelerated = 就绪）----
    # 404 = 种子不存在（永久错误——不轮询，换下一候选）；sql-iterative = 投影
    # 未就绪（可等待——轮询至上限，超时走兜底仍出指标且 route 如实记录）。
    canary = {"timeoutS": args.canary_timeout, "ready": False, "route": None, "waitedS": 0}
    canary_candidates = [a.get("backendMethodId") for a in apis if a.get("backendMethodId")]
    canary_candidates += [m["id"] for m in mappers]
    for cand in canary_candidates[:3]:
        if not cand:
            continue
        t_deadline = time.monotonic() + args.canary_timeout
        while True:
            resp, _ms, status = expand_call(base, args.token, cand, snap_id, depth=1, limit=10)
            route = (resp or {}).get("route")
            if status == 200 and route == "graph-accelerated":
                canary.update({"ready": True, "route": route})
                break
            if status == 404:
                canary["route"] = "http_404（候选种子不存在——换下一候选）"
                break
            canary["route"] = route or ("http_%s" % status)
            if time.monotonic() >= t_deadline:
                break
            time.sleep(CANARY_INTERVAL_S)
            canary["waitedS"] = int(args.canary_timeout - (t_deadline - time.monotonic()))
        if canary["ready"] or status != 404:
            break
    print("canary: ready=%s route=%s waited=%ss（超时走兜底——route 如实记录）" % (
        canary["ready"], canary["route"], canary["waitedS"]))

    # ---- 遥测基线（run 尾部差分对照——snapshotId 键控本快照计数）----
    telemetry_before = http_json(
        "%s/api/ontology/telemetry?snapshotId=%s" % (base, urllib.parse.quote(snap_id)), args.token)

    # ---- 逐 ApiEndpoint expand 闭包（核心图压测面）----
    route_counter = {}
    latencies = []
    truncated_by = {"depth": 0, "limit": 0, "timeout": 0}
    seed_unresolved = 0
    hops = []
    complete_chains = 0
    join_hits = 0
    for a in apis:
        bm = a.get("backendMethodId")
        if not bm:
            continue
        resp, ms, status = expand_call(base, args.token, bm, snap_id)
        if resp is None and status == 404:
            resp, ms, status = expand_call(base, args.token, "mtd:" + bm, snap_id)
        if resp is None:
            if status == 404:
                seed_unresolved += 1
                continue
            print("FAIL: expand HTTP %s（seed=%s）" % (status, bm[:80]), file=sys.stderr)
            return 1
        route = resp.get("route") or "?"
        route_counter[route] = route_counter.get(route, 0) + 1
        latencies.append(ms)
        if resp.get("truncated"):
            tb = resp.get("truncatedBy") or "?"
            truncated_by[tb] = truncated_by.get(tb, 0) + 1
        first_level, mm = closure_from_expand(resp, mapper_by_ns)
        if mm > 0:
            join_hits += 1
        if first_level is not None:
            complete_chains += 1
            hops.append(first_level)

    # ---- 遥测差分 ----
    time.sleep(1)
    telemetry_after = http_json(
        "%s/api/ontology/telemetry?snapshotId=%s" % (base, urllib.parse.quote(snap_id)), args.token)

    def _tel_delta(key):
        b = (telemetry_before.get(key) or {})
        a_ = (telemetry_after.get(key) or {})
        if isinstance(b, dict) and isinstance(a_, dict):
            return {k: a_.get(k, 0) - b.get(k, 0) for k in sorted(set(b) | set(a_))}
        return None

    lat_sorted = sorted(latencies)
    hops_sorted = sorted(hops)
    a1_value = round(complete_chains / len(apis), 6) if len(apis) else None
    result = {
        "schemaVersion": SCHEMA_VERSION,
        "implementation": IMPLEMENTATION,
        "owner": args.owner,
        "repo": args.repo,
        "sourceId": source_id,
        "snapshotId": snap_id,
        "metrics": {
            "A1": {
                "id": "A1", "name": "full-chain-coverage", "label": "全链路贯通率",
                "domain": "A", "direction": "higher-better",
                "value": a1_value,
                "numerator": complete_chains, "denominator": len(apis),
                "algorithm": "expand closure (direction=out, linkTypes=calls, depth<=%d)" % DEPTH_MAX,
            },
            "C1": {
                "id": "C1", "name": "endpoint-table-hops", "label": "端到端跳数",
                "domain": "C", "direction": "interval",
                "value": nearest_rank(hops_sorted, 0.50),
                "percentiles": {
                    "p25": nearest_rank(hops_sorted, 0.25),
                    "p50": nearest_rank(hops_sorted, 0.50),
                    "p75": nearest_rank(hops_sorted, 0.75),
                    "p90": nearest_rank(hops_sorted, 0.90),
                },
                "min": hops_sorted[0] if hops_sorted else None,
                "max": hops_sorted[-1] if hops_sorted else None,
                "hopsBasis": "calls edges, first hit level from expand levels",
            },
        },
        "evidence": {
            "canary": canary,
            "queries": {
                "count": len(latencies),
                "routeDistribution": route_counter,
                "latencyMs": {
                    "p50": nearest_rank(lat_sorted, 0.50),
                    "p90": nearest_rank(lat_sorted, 0.90),
                    "p95": nearest_rank(lat_sorted, 0.95),
                    "max": lat_sorted[-1] if lat_sorted else None,
                },
                "truncatedBy": truncated_by,
                "seedUnresolved": seed_unresolved,
                "joinHitClosures": join_hits,
            },
            "telemetryDelta": {
                "queriesTotal": (telemetry_after.get("queries", {}).get("total", 0)
                                 - telemetry_before.get("queries", {}).get("total", 0)),
                "byRoute": _tel_delta("byRoute") if isinstance(telemetry_before.get("queries"), dict) else None,
                "byEndpoint": _tel_delta("byEndpoint") if isinstance(telemetry_before.get("queries"), dict) else None,
            },
        },
    }
    if truncated_by.get("depth"):
        result["evidence"]["queries"]["note"] = (
            "depth 截断链 %d 条——该等链 C1 取截断内首中层（如实计数不判 FAIL，V5.1.4.1）"
            % truncated_by["depth"])

    # ---- 双路径等价性比对（V5.1.4.4 判据：与本地形态逐位相等）----
    equivalence = None
    if args.compare:
        try:
            with open(args.compare, encoding="utf-8") as f:
                local = json.load(f)
        except (OSError, ValueError) as e:
            print("FAIL: --compare 文件不可读：%s" % e, file=sys.stderr)
            return 1
        lm = local.get("metrics", {})
        la1 = (lm.get("A1") or {}).get("value")
        lc1 = (lm.get("C1") or {})
        ga1 = a1_value
        gc1p50 = nearest_rank(hops_sorted, 0.50)
        checks = {
            "A1.value": {"local": la1, "graph": ga1, "match": la1 == ga1},
            "C1.p50": {"local": lc1.get("value"), "graph": gc1p50,
                       "match": lc1.get("value") == gc1p50},
        }
        ld = lc1.get("distribution") or {}
        gd = {}
        for h in hops:
            gd[str(h)] = gd.get(str(h), 0) + 1
        checks["C1.distribution"] = {"local": ld, "graph": gd, "match": ld == gd}
        all_match = all(c["match"] for c in checks.values())
        equivalence = {"allMatch": all_match, "checks": checks}
        print("equivalence: %s" % ("PASS（双路径逐位一致）" if all_match else "MISMATCH——见 checks"))
    result["equivalence"] = equivalence

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print("graph-metrics written: %s（A1=%s C1.p50=%s queries=%d routes=%s truncated=%s）" % (
        out_path, a1_value, nearest_rank(hops_sorted, 0.50), len(latencies),
        json.dumps(route_counter), json.dumps(truncated_by)))
    if equivalence is not None and not equivalence["allMatch"]:
        return 2
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RuntimeError as e:
        print("FAIL: %s" % e, file=sys.stderr)
        sys.exit(1)
