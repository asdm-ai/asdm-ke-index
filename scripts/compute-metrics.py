#!/usr/bin/env python3
# =============================================================================
# KE Index · L1 指标计算（过渡实现——P2H-D5）
# -----------------------------------------------------------------------------
# 用法（GitHub Actions 与本地复算同形）：
#   KE_SERVER_URL=https://... KE_API_KEY=... python3 scripts/compute-metrics.py \
#     --owner macrozheng --repo mall \
#     [--ke-cli "node /path/bin/ke.cjs"] [--source-id mall] [--snapshot <id>] \
#     [--out reports/macrozheng/mall.json]
#
# 方法论：AOS Index Metrics Schema draft v1（四域 A-D + dq）。
#   - 明细拉取：ke query 七类核心对象（Table/Mapper/Package/Interface/Class/
#     Method/Dependency）+ 条件拉取前端类（ApiEndpoint/Module/Component 存在时）
#   - 内存聚合：双条件判定（A3/A4）、Tarjan SCC（B1）、nearest-rank 分位（C2）、
#     比率指标（B3/C3/C4）、规模画像（D3）
#   - 交叉验证：分子/基数与 `ke count --where` 服务端计数逐位对账——不一致
#     即失败（记录→定位→修复，不静默吞差）
#   - 可复算：每指标附 commands 指令清单（连接参数以 $KE_SERVER_URL /
#     $KE_API_KEY 环境变量占位——导出后可直接粘贴执行）
#   - 置空口径：分母为 0 或对象类缺失时指标置 null 并记录 reason（对齐
#     Schema 置空语义——nullMetrics 区，不进 metrics 区）
#
# 依赖：Python 3.8+ 标准库（零第三方依赖）；ke CLI 0.3.0+（server 模式）。
#
# 输出确定性：同一快照产出逐字节一致的 report（不含墙钟时间戳）——
# 月度重扫数值未变时不产生 git diff（无空提交）。
# =============================================================================
import argparse
import json
import os
import shlex
import subprocess
import sys
from math import ceil

SCHEMA_VERSION = "draft-v1"
IMPLEMENTATION = "ke-index compute-metrics.py (transitional; to be superseded by ke checkup)"

# 蓝图 14 对象类型（D3 typeCounts 口径——逐类型 count）
OBJECT_TYPES = [
    "Repository", "Package", "Class", "Interface", "Method", "Dependency",
    "Table", "Mapper", "Module", "Component", "Function", "Store", "Route",
    "ApiEndpoint",
]

# 交叉验证硬判据（分子/基数 vs 服务端 count——不一致即失败）
CROSS_CHECKS = [
    ("B3", "Class", "lineCount>500"),
    ("C3", "Method", "isTest=true"),
    ("C4", "Method", "lineCount>80"),
    ("C2", "Method", "complexity"),
]


class KeError(RuntimeError):
    pass


def parse_json_block(text):
    """解析 CLI stdout（outputJSON 契约为美化多行 JSON；容错前导日志行）。"""
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
    raise KeError("ke 输出中未找到可解析的 JSON 块：%.200s" % text)


class KeCli:
    """ke CLI 封装（server 模式全局旗标 + 子命令）。"""

    def __init__(self, ke_cli, url, token):
        self.argv = shlex.split(ke_cli) if ke_cli else ["ke"]
        self.conn = ["--mode", "server", "--url", url, "--token", token]

    def run(self, args, timeout=900):
        argv = self.argv + self.conn + args
        try:
            p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        except FileNotFoundError:
            raise KeError("ke CLI 不可执行：%s" % argv[0])
        if p.returncode != 0:
            raise KeError("ke %s 失败（rc=%s）：%s" % (" ".join(args), p.returncode, p.stderr.strip()[:400]))
        return p.stdout

    def run_json(self, args):
        return parse_json_block(self.run(args))

    def version(self):
        p = subprocess.run(self.argv + ["--version"], capture_output=True, text=True, timeout=60)
        return p.stdout.strip() or "unknown"

    # ---- 高层命令 ----

    def snapshot_list(self, source_id):
        out = self.run_json(["snapshot", "list", "--repo", source_id])
        return out.get("snapshots", [])

    def count(self, obj_type, snapshot_id, where=None):
        args = ["count", obj_type]
        if where:
            args += ["--where", where]
        args += ["--snapshot", snapshot_id]
        out = self.run_json(args)
        return int(out["count"])

    def query(self, obj_type, fields, snapshot_id):
        args = ["query", obj_type, "--all", "--field", ",".join(fields), "--snapshot", snapshot_id]
        out = self.run_json(args)
        if not isinstance(out, list):
            raise KeError("ke query %s 输出非数组" % obj_type)
        return out


def cmd_str(args, snapshot_id):
    """可复算指令记录（$KE_SERVER_URL/$KE_API_KEY 占位——导出后可直接执行）。"""
    quoted = []
    for a in args:
        quoted.append("'" + a + "'" if (" " in a or ">" in a or "=" in a) else a)
    return (
        'ke --mode server --url "$KE_SERVER_URL" --token "$KE_API_KEY" '
        + " ".join(quoted)
        + " --snapshot " + snapshot_id
    )


def count_cmd(obj_type, where, snapshot_id):
    args = ["count", obj_type] + (["--where", where] if where else [])
    return cmd_str(args, snapshot_id)


def query_cmd(obj_type, fields, snapshot_id):
    return cmd_str(["query", obj_type, "--all", "--field", ",".join(fields)], snapshot_id)


# =============================================================================
# 内存聚合算法
# =============================================================================

def tarjan_scc(nodes, adj):
    """迭代 Tarjan 强连通分量（避免深图递归栈溢出）。adj 值仅含 nodes 内目标。"""
    index_counter = [0]
    index, lowlink = {}, {}
    stack, on_stack = [], set()
    sccs = []
    for root in nodes:
        if root in index:
            continue
        work = [(root, iter(adj.get(root, ())))]
        index[root] = lowlink[root] = index_counter[0]
        index_counter[0] += 1
        stack.append(root)
        on_stack.add(root)
        while work:
            v, it = work[-1]
            pushed = False
            for w in it:
                if w not in index:
                    index[w] = lowlink[w] = index_counter[0]
                    index_counter[0] += 1
                    stack.append(w)
                    on_stack.add(w)
                    work.append((w, iter(adj.get(w, ()))))
                    pushed = True
                    break
                elif w in on_stack:
                    if index[w] < lowlink[v]:
                        lowlink[v] = index[w]
            if pushed:
                continue
            work.pop()
            if lowlink[v] == index[v]:
                comp = []
                while True:
                    w = stack.pop()
                    on_stack.discard(w)
                    comp.append(w)
                    if w == v:
                        break
                sccs.append(comp)
            if work:
                parent = work[-1][0]
                if lowlink[v] < lowlink[parent]:
                    lowlink[parent] = lowlink[v]
    return sccs


def nearest_rank(sorted_vals, p):
    """nearest-rank 分位：升序第 ceil(p*N) 个值（Schema §4.2 口径）。"""
    n = len(sorted_vals)
    if n == 0:
        return None
    idx = max(1, ceil(p * n))
    return sorted_vals[min(idx, n) - 1]


def num_or_zero(v):
    """属性数值化（与 CLI where 数字比较糖同口径：null→0、非数值→不可比）。"""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return v
    if v is None:
        return 0
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def is_true(v):
    """与 CLI 等值匹配同口径：String(v) === 'true'。"""
    return str(v).lower() == "true"


# =============================================================================
# report 组装
# =============================================================================

def metric(metric_id, name, label, domain, direction, value, commands, numerator=None,
           denominator=None, **extra):
    entry = {
        "id": metric_id,
        "name": name,
        "label": label,
        "domain": domain,
        "direction": direction,
        "value": value,
    }
    if numerator is not None:
        entry["numerator"] = numerator
    if denominator is not None:
        entry["denominator"] = denominator
    entry["commands"] = commands
    entry.update(extra)
    return entry


def null_metric(metric_id, name, label, domain, direction, reason, commands=None, evidence=None):
    entry = {
        "id": metric_id,
        "name": name,
        "label": label,
        "domain": domain,
        "direction": direction,
        "value": None,
        "reason": reason,
    }
    if commands:
        entry["commands"] = commands
    if evidence:
        entry["evidence"] = evidence
    return entry


def ratio(num, den, digits=6):
    return round(num / den, digits) if den else None


def main():
    ap = argparse.ArgumentParser(description="KE Index L1 指标计算（过渡实现）")
    ap.add_argument("--owner", required=True, help="GitHub owner（如 macrozheng）")
    ap.add_argument("--repo", required=True, help="仓库名（如 mall；亦为导入 sourceId）")
    ap.add_argument("--source-id", default=None, help="导入 sourceId（缺省 = repo 名）")
    ap.add_argument("--snapshot", default=None, help="目标快照 ID（缺省取该 source 最新 complete 快照）")
    ap.add_argument("--ke-cli", default="ke", help='ke CLI 命令（如 "node /path/bin/ke.cjs"）')
    ap.add_argument("--url", default=os.environ.get("KE_SERVER_URL"), help="aos-server 基址（缺省读 KE_SERVER_URL）")
    ap.add_argument("--token", default=os.environ.get("KE_API_KEY"), help="API key（缺省读 KE_API_KEY）")
    ap.add_argument("--out", default=None, help="输出文件（缺省 reports/{owner}/{repo}.json）")
    ap.add_argument("--skip-cross-check", action="store_true", help="跳过 count 交叉验证（仅调试用）")
    args = ap.parse_args()

    if not args.url or not args.token:
        print("FAIL: 需要 --url/--token（或导出 KE_SERVER_URL / KE_API_KEY）", file=sys.stderr)
        return 1
    source_id = args.source_id or args.repo
    out_path = args.out or os.path.join("reports", args.owner, "%s.json" % args.repo)

    ke = KeCli(args.ke_cli, args.url, args.token)
    cli_version = ke.version()

    # ---- 快照解析（显式 --snapshot 校验；缺省取该 source 最新 complete）----
    snaps = ke.snapshot_list(source_id)
    complete = [s for s in snaps if s.get("status") == "complete"]
    if args.snapshot:
        target = next((s for s in complete if s.get("snapshotId") == args.snapshot), None)
        if target is None:
            print("FAIL: 快照 %s 不是 source %s 的 complete 快照" % (args.snapshot, source_id), file=sys.stderr)
            return 1
    else:
        if not complete:
            print("FAIL: source %s 无 complete 快照（先执行导入）" % source_id, file=sys.stderr)
            return 1
        target = max(
            complete,
            key=lambda s: (s.get("completedAt") or s.get("createdAt") or ""),
        )
    snap_id = target["snapshotId"]
    print("target snapshot: %s (%s, objectCount=%s)" % (
        snap_id, target.get("status"), target.get("objectCount")))

    # ---- 14 类型 count（D3 typeCounts + 前端类存在性判定）----
    counts = {t: ke.count(t, snap_id) for t in OBJECT_TYPES}
    print("typeCounts: " + json.dumps(counts, ensure_ascii=False))

    # ---- 明细拉取（七类核心 + 条件前端类）----
    tables = ke.query("Table", ["id", "name", "matchedEntityClass"], snap_id)
    mappers = ke.query("Mapper", ["id", "namespace", "mappedTableIds"], snap_id)
    packages = ke.query("Package", ["id", "dependsOnPackageIds"], snap_id)
    interfaces = ke.query("Interface", ["id"], snap_id)
    classes = ke.query("Class", ["id", "lineCount"], snap_id)
    methods = ke.query("Method", ["id", "lineCount", "complexity", "isTest", "testType"], snap_id)
    deps = ke.query("Dependency", ["id", "name", "version", "scope"], snap_id)
    apis = ke.query("ApiEndpoint", ["id", "backendMethodId", "matchedVia"], snap_id) \
        if counts["ApiEndpoint"] > 0 else []
    modules = ke.query("Module", ["id", "importedModuleIds"], snap_id) \
        if counts["Module"] > 0 else []
    components = ke.query("Component", ["id", "referencedComponentIds", "isGlobal"], snap_id) \
        if counts["Component"] > 0 else []

    # 拉取完整性断言（query --all 与 count 必然同数——通道不一致即数据异常）
    for label, pulled, cnt in [
        ("Table", tables, counts["Table"]), ("Mapper", mappers, counts["Mapper"]),
        ("Package", packages, counts["Package"]), ("Interface", interfaces, counts["Interface"]),
        ("Class", classes, counts["Class"]), ("Method", methods, counts["Method"]),
        ("Dependency", deps, counts["Dependency"]),
        ("ApiEndpoint", apis, counts["ApiEndpoint"]), ("Module", modules, counts["Module"]),
        ("Component", components, counts["Component"]),
    ]:
        if len(pulled) != cnt:
            print("FAIL: %s 拉取数 %d != count %d（查询通道不一致）" % (label, len(pulled), cnt), file=sys.stderr)
            return 1

    metrics = {}
    null_metrics = {}

    # ================= 域 A · 跨层映射 =================

    # A1 全链路贯通率：calls 传递闭包 + Method→Mapper 名字 join 未实现（过渡实现）
    null_metrics["A1"] = null_metric(
        "A1", "full-chain-coverage", "全链路贯通率", "A", "higher-better",
        "无 ApiEndpoint 对象（分母为 0，按口径降级）" if counts["ApiEndpoint"] == 0
        else "calls 传递闭包与 Method→Mapper 名字 join 未实现（过渡实现——待 ke checkup）",
        commands=[count_cmd("ApiEndpoint", None, snap_id)] if counts["ApiEndpoint"] == 0 else None,
        evidence={"apiEndpointCount": counts["ApiEndpoint"]},
    )

    # A2 前后端断链率：backendMethodId 为空的 ApiEndpoint 占比
    if counts["ApiEndpoint"] == 0:
        null_metrics["A2"] = null_metric(
            "A2", "api-backend-breakrate", "前后端断链率", "A", "lower-better",
            "无 ApiEndpoint 对象（纯后端仓库——按口径置空）",
            commands=[count_cmd("ApiEndpoint", None, snap_id)],
            evidence={"apiEndpointCount": 0},
        )
    else:
        broken = sum(1 for a in apis if not a.get("backendMethodId"))
        metrics["A2"] = metric(
            "A2", "api-backend-breakrate", "前后端断链率", "A", "lower-better",
            ratio(broken, len(apis)), [query_cmd("ApiEndpoint", ["id", "backendMethodId", "matchedVia"], snap_id),
                                       count_cmd("ApiEndpoint", None, snap_id)],
            numerator=broken, denominator=len(apis),
        )

    # A3/A4 双条件判定（口径一致：A3 分子 + A4 分子 = 分母）
    mapper_mapped_tables = set()
    for m in mappers:
        for tid in (m.get("mappedTableIds") or []):
            mapper_mapped_tables.add(tid)
    entity_matched = set()
    for t in tables:
        if t.get("matchedEntityClass"):
            entity_matched.add(t["id"])
    table_ids = {t["id"] for t in tables}
    mapped = table_ids & (mapper_mapped_tables | entity_matched)
    orphan_num = len(table_ids) - len(mapped)
    if len(table_ids) == 0:
        null_metrics["A3"] = null_metric(
            "A3", "orphan-table-rate", "孤儿表率", "A", "lower-better",
            "无 Table 对象（分母为 0）", commands=[count_cmd("Table", None, snap_id)])
        null_metrics["A4"] = null_metric(
            "A4", "table-entity-mapping-rate", "表↔实体映射率", "A", "higher-better",
            "无 Table 对象（分母为 0）", commands=[count_cmd("Table", None, snap_id)])
    else:
        a34_cmds = [
            query_cmd("Table", ["id", "name", "matchedEntityClass"], snap_id),
            query_cmd("Mapper", ["id", "namespace", "mappedTableIds"], snap_id),
            count_cmd("Table", None, snap_id),
        ]
        metrics["A3"] = metric(
            "A3", "orphan-table-rate", "孤儿表率", "A", "lower-better",
            ratio(orphan_num, len(table_ids)), a34_cmds,
            numerator=orphan_num, denominator=len(table_ids),
        )
        metrics["A4"] = metric(
            "A4", "table-entity-mapping-rate", "表↔实体映射率", "A", "higher-better",
            ratio(len(mapped), len(table_ids)), a34_cmds,
            numerator=len(mapped), denominator=len(table_ids),
            evidence={"mapperEdgeOnly": len(mapper_mapped_tables - entity_matched),
                      "entityClassOnly": len(entity_matched - mapper_mapped_tables),
                      "both": len(mapper_mapped_tables & entity_matched)},
        )

    # ================= 域 B · 模块耦合 =================

    # B1.backend 循环依赖密度（Tarjan SCC，大小 >= 2 的分量）
    if counts["Package"] == 0:
        null_metrics["B1.backend"] = null_metric(
            "B1.backend", "circular-dependency-density", "循环依赖密度（后端）", "B", "lower-better",
            "无 Package 对象（分母为 0）", commands=[count_cmd("Package", None, snap_id)])
    else:
        pkg_ids = [p["id"] for p in packages]
        pkg_set = set(pkg_ids)
        pkg_adj = {}
        edge_count = 0
        for p in packages:
            targets = [d for d in (p.get("dependsOnPackageIds") or []) if d in pkg_set]
            pkg_adj[p["id"]] = targets
            edge_count += len(targets)
        sccs = [c for c in tarjan_scc(pkg_ids, pkg_adj) if len(c) >= 2]
        in_cycle = sum(len(c) for c in sccs)
        b1_cmds = [
            query_cmd("Package", ["id", "dependsOnPackageIds"], snap_id),
            count_cmd("Package", None, snap_id),
        ]
        metrics["B1.backend"] = metric(
            "B1.backend", "circular-dependency-density", "循环依赖密度（后端）", "B", "lower-better",
            ratio(in_cycle, len(pkg_ids)), b1_cmds,
            numerator=in_cycle, denominator=len(pkg_ids),
            sccCount=len(sccs),
            sccs=sorted([{"size": len(c), "members": sorted(c)} for c in sccs],
                        key=lambda s: (-s["size"], s["members"])),
        )
        # B2 包依赖密度（dependsOn 边 / Package 数——区间型）
        metrics["B2"] = metric(
            "B2", "package-dependency-density", "包依赖密度", "B", "interval",
            round(edge_count / len(pkg_ids), 4) if pkg_ids else None, b1_cmds,
            numerator=edge_count, denominator=len(pkg_ids),
        )
    if "B2" not in metrics and counts["Package"] == 0:
        null_metrics["B2"] = null_metric(
            "B2", "package-dependency-density", "包依赖密度", "B", "interval",
            "无 Package 对象（分母为 0）", commands=[count_cmd("Package", None, snap_id)])

    # B1.frontend（Module + imports——存在前端工程时计算）
    if counts["Module"] == 0:
        null_metrics["B1.frontend"] = null_metric(
            "B1.frontend", "circular-dependency-density", "循环依赖密度（前端）", "B", "lower-better",
            "无 Module 对象（纯后端仓库——按口径置空）",
            commands=[count_cmd("Module", None, snap_id)],
            evidence={"moduleCount": 0},
        )
    else:
        mod_ids = [m["id"] for m in modules]
        mod_set = set(mod_ids)
        mod_adj = {m["id"]: [d for d in (m.get("importedModuleIds") or []) if d in mod_set] for m in modules}
        sccs = [c for c in tarjan_scc(mod_ids, mod_adj) if len(c) >= 2]
        in_cycle = sum(len(c) for c in sccs)
        metrics["B1.frontend"] = metric(
            "B1.frontend", "circular-dependency-density", "循环依赖密度（前端）", "B", "lower-better",
            ratio(in_cycle, len(mod_ids)),
            [query_cmd("Module", ["id", "importedModuleIds"], snap_id), count_cmd("Module", None, snap_id)],
            numerator=in_cycle, denominator=len(mod_ids), sccCount=len(sccs),
        )

    # B3 巨型类占比（lineCount > 500）
    if counts["Class"] == 0:
        null_metrics["B3"] = null_metric(
            "B3", "giant-class-ratio", "巨型类占比", "B", "lower-better",
            "无 Class 对象（分母为 0）", commands=[count_cmd("Class", None, snap_id)])
    else:
        giant_classes = [c for c in classes if (num_or_zero(c.get("lineCount")) or 0) > 500]
        top_classes = sorted(classes, key=lambda c: -(num_or_zero(c.get("lineCount")) or 0))[:5]
        metrics["B3"] = metric(
            "B3", "giant-class-ratio", "巨型类占比", "B", "lower-better",
            ratio(len(giant_classes), len(classes)),
            [query_cmd("Class", ["id", "lineCount"], snap_id),
             count_cmd("Class", "lineCount>500", snap_id),
             count_cmd("Class", None, snap_id)],
            numerator=len(giant_classes), denominator=len(classes),
            threshold="lineCount > 500",
            top=[{"lineCount": c.get("lineCount"), "id": c["id"]} for c in top_classes],
        )

    # B4 组件耦合度（references 边 / Component 数 + isGlobal 辅助占比）
    if counts["Component"] == 0:
        null_metrics["B4"] = null_metric(
            "B4", "component-coupling-degree", "组件耦合度", "B", "lower-better",
            "无 Component 对象（纯后端仓库——按口径置空）",
            commands=[count_cmd("Component", None, snap_id)],
            evidence={"componentCount": 0},
        )
    else:
        ref_edges = sum(len(c.get("referencedComponentIds") or []) for c in components)
        global_cnt = sum(1 for c in components if is_true(c.get("isGlobal")))
        metrics["B4"] = metric(
            "B4", "component-coupling-degree", "组件耦合度", "B", "lower-better",
            round(ref_edges / len(components), 4),
            [query_cmd("Component", ["id", "referencedComponentIds", "isGlobal"], snap_id),
             count_cmd("Component", None, snap_id)],
            numerator=ref_edges, denominator=len(components),
            globalRegistrationRatio=ratio(global_cnt, len(components)),
        )

    # ================= 域 C · 纵深复杂度 =================

    # C1 端到端跳数：依赖 A1 贯通链算法（过渡实现未含）
    null_metrics["C1"] = null_metric(
        "C1", "endpoint-table-hops", "端到端跳数", "C", "interval",
        "依赖 A1 贯通链算法（过渡实现未含——待 ke checkup）"
        if counts["ApiEndpoint"] > 0 else "无 ApiEndpoint 对象（贯通链分母为 0）",
        evidence={"apiEndpointCount": counts["ApiEndpoint"]},
    )

    # C2 圈复杂度 P90（complexity 非 null 的 Method，nearest-rank）
    method_cc = []
    for m in methods:
        c = m.get("complexity")
        if isinstance(c, dict) and isinstance(c.get("cyclomaticComplexity"), (int, float)):
            method_cc.append((m["id"], c["cyclomaticComplexity"]))
    cc_vals = sorted(v for _, v in method_cc)
    if not cc_vals:
        null_metrics["C2"] = null_metric(
            "C2", "cyclomatic-complexity-p90", "圈复杂度 P90", "C", "lower-better",
            "无 complexity 非 null 的 Method（分母为 0）",
            commands=[count_cmd("Method", "complexity", snap_id)])
    else:
        p25 = nearest_rank(cc_vals, 0.25)
        p50 = nearest_rank(cc_vals, 0.50)
        p75 = nearest_rank(cc_vals, 0.75)
        p90 = nearest_rank(cc_vals, 0.90)
        top_cc = sorted(method_cc, key=lambda x: -x[1])[:5]
        metrics["C2"] = metric(
            "C2", "cyclomatic-complexity-p90", "圈复杂度 P90", "C", "lower-better",
            p90,
            [count_cmd("Method", "complexity", snap_id),
             query_cmd("Method", ["id", "lineCount", "complexity"], snap_id)],
            denominator=len(cc_vals),
            percentiles={"p25": p25, "p50": p50, "p75": p75, "p90": p90},
            mean=round(sum(cc_vals) / len(cc_vals), 4),
            max=cc_vals[-1],
            top=[{"cyclomaticComplexity": v, "id": i} for i, v in top_cc],
        )

    # C3 测试方法占比（isTest = true）
    if counts["Method"] == 0:
        null_metrics["C3"] = null_metric(
            "C3", "test-method-ratio", "测试方法占比", "C", "higher-better",
            "无 Method 对象（分母为 0）", commands=[count_cmd("Method", None, snap_id)])
    else:
        test_methods = [m for m in methods if is_true(m.get("isTest"))]
        test_types = {}
        for m in test_methods:
            tt = m.get("testType") or "unknown"
            test_types[tt] = test_types.get(tt, 0) + 1
        metrics["C3"] = metric(
            "C3", "test-method-ratio", "测试方法占比", "C", "higher-better",
            ratio(len(test_methods), len(methods)),
            [count_cmd("Method", "isTest=true", snap_id), count_cmd("Method", None, snap_id),
             query_cmd("Method", ["id", "isTest", "testType"], snap_id)],
            numerator=len(test_methods), denominator=len(methods),
            testTypes=test_types,
        )

    # C4 巨型方法占比（分母排除 lineCount = 0 / null——接口与字节码补全方法）
    if counts["Method"] == 0:
        null_metrics["C4"] = null_metric(
            "C4", "giant-method-ratio", "巨型方法占比", "C", "lower-better",
            "无 Method 对象（分母为 0）", commands=[count_cmd("Method", None, snap_id)])
    else:
        denom_c4 = [m for m in methods if (num_or_zero(m.get("lineCount")) or 0) > 0]
        giant_methods = [m for m in denom_c4 if (num_or_zero(m.get("lineCount")) or 0) > 80]
        top_methods = sorted(denom_c4, key=lambda m: -(num_or_zero(m.get("lineCount")) or 0))[:5]
        zero_lc = sum(1 for m in methods if num_or_zero(m.get("lineCount")) == 0 and m.get("lineCount") is not None)
        null_lc = sum(1 for m in methods if m.get("lineCount") is None)
        metrics["C4"] = metric(
            "C4", "giant-method-ratio", "巨型方法占比", "C", "lower-better",
            ratio(len(giant_methods), len(denom_c4)),
            [count_cmd("Method", "lineCount>80", snap_id),
             count_cmd("Method", "lineCount=0", snap_id),
             count_cmd("Method", None, snap_id),
             query_cmd("Method", ["id", "lineCount"], snap_id)],
            numerator=len(giant_methods), denominator=len(denom_c4),
            threshold="lineCount > 80",
            excludedFromDenominator={"lineCountIsZero": zero_lc, "lineCountIsNull": null_lc},
            top=[{"lineCount": m.get("lineCount"), "id": m["id"]} for m in top_methods],
        )

    # ================= 域 D · 技术栈演进 =================

    # D1 版本覆盖率：目标 semver range 为 cohort 级策略输入——单体层不出值
    empty_ver = sum(1 for d in deps if not d.get("version"))
    placeholder_ver = sum(1 for d in deps if isinstance(d.get("version"), str) and "${" in d["version"])
    determinable = len(deps) - empty_ver - placeholder_ver
    if determinable == 0:
        d1_reason = "无可判定版本（空串 %d / 属性占位 %d / 合计 %d——分母为 0，按口径置空）" % (
            empty_ver, placeholder_ver, len(deps))
    else:
        d1_reason = "目标 semver range 为 cohort 级策略输入（过渡实现单体层不出值）"
    null_metrics["D1"] = null_metric(
        "D1", "framework-version-coverage", "技术栈版本覆盖率", "D", "higher-better",
        d1_reason,
        commands=[query_cmd("Dependency", ["id", "name", "version", "scope"], snap_id)],
        evidence={"total": len(deps), "emptyVersion": empty_ver,
                  "placeholder": placeholder_ver, "determinable": determinable},
    )

    # D2 依赖同质度：cohort 级指标（单体层不产出）
    null_metrics["D2"] = null_metric(
        "D2", "dependency-homogeneity", "依赖同质度", "D", "none",
        "cohort 级指标（依赖 cohort 众数集合——单体层不产出）",
        evidence={"dependencyCount": len(deps)},
    )

    # D3 规模画像（描述型：objectCount / linkCount / typeCounts）
    metrics["D3"] = metric(
        "D3", "scale-profile", "规模画像", "D", "none",
        int(target.get("objectCount") or 0),
        ["ke --mode server --url \"$KE_SERVER_URL\" --token \"$KE_API_KEY\" snapshot list --repo " + source_id]
        + [count_cmd(t, None, snap_id) for t in OBJECT_TYPES],
        typeCounts={t: counts[t] for t in OBJECT_TYPES},
        linkCount=int(target.get("linkCount") or 0),
    )

    # D4 年度演进趋势：时序聚合未实现（过渡实现）
    snap_count = len(complete)
    null_metrics["D4"] = null_metric(
        "D4", "evolution-trend", "年度演进趋势", "D", "none",
        "单快照（首次导入——无时序）" if snap_count <= 1
        else "时序聚合未实现（过渡实现——该 source 已有 %d 个 complete 快照）" % snap_count,
        commands=["ke --mode server --url \"$KE_SERVER_URL\" --token \"$KE_API_KEY\" snapshot list --repo " + source_id],
        evidence={"completeSnapshotCount": snap_count},
    )

    # ================= 数据质量（dq——不评分）=================

    data_quality = {}
    if counts["Method"] > 0:
        null_cc = len(methods) - len(method_cc)
        data_quality["dq.null-complexity-ratio"] = metric(
            "dq.null-complexity-ratio", "null-complexity-ratio", "complexity 为 null 的方法占比", "dq", "none",
            ratio(null_cc, len(methods)),
            [count_cmd("Method", None, snap_id), count_cmd("Method", "complexity", snap_id)],
            numerator=null_cc, denominator=len(methods),
        )
    if len(deps) > 0:
        data_quality["dq.missing-version-ratio"] = metric(
            "dq.missing-version-ratio", "missing-version-ratio", "version 为空串的依赖占比", "dq", "none",
            ratio(empty_ver, len(deps)),
            [query_cmd("Dependency", ["id", "name", "version", "scope"], snap_id)],
            numerator=empty_ver, denominator=len(deps),
            placeholderVersionCount=placeholder_ver,
        )
    if len(mappers) > 0:
        # 对象 id 带类型前缀（如 "intf:com.macro..."）——join 前剥离前缀取裸 FQN，
        # 与 Mapper.namespace（裸 FQN）同形对齐
        interface_fqns = {
            i["id"].split(":", 1)[1] if ":" in i["id"] else i["id"] for i in interfaces
        }
        join_miss = sum(1 for m in mappers if m.get("namespace") not in interface_fqns)
        data_quality["dq.mapper-join-miss-ratio"] = metric(
            "dq.mapper-join-miss-ratio", "mapper-join-miss-ratio", "Mapper namespace 与接口 FQN join 未命中占比",
            "dq", "none", ratio(join_miss, len(mappers)),
            [query_cmd("Mapper", ["id", "namespace"], snap_id), query_cmd("Interface", ["id"], snap_id)],
            numerator=join_miss, denominator=len(mappers),
        )
    data_quality["dq.ext-call-ratio"] = null_metric(
        "dq.ext-call-ratio", "ext-call-ratio", "ext: 虚拟调用过滤占比", "dq", "none",
        "不可观测（ext: 虚拟边在导入物化时已过滤——查询面天然免疫）",
    )

    # ================= 交叉验证（硬判据——不一致即失败）=================

    if not args.skip_cross_check:
        checks = {
            "B3": len([c for c in classes if (num_or_zero(c.get("lineCount")) or 0) > 500]) if classes else None,
            "C3": len([m for m in methods if is_true(m.get("isTest"))]) if methods else None,
            "C4": len([m for m in methods if (num_or_zero(m.get("lineCount")) or 0) > 80]) if methods else None,
            "C2": len(method_cc) if methods else None,
        }
        for metric_id, obj_type, where in CROSS_CHECKS:
            local = checks[metric_id]
            if local is None:
                continue
            server = ke.count(obj_type, snap_id, where)
            ok = server == local
            print("cross-check %s: local=%s server=%s %s" % (metric_id, local, server, "OK" if ok else "MISMATCH"))
            if not ok:
                print("FAIL: %s 交叉验证不一致（本地聚合 %s != 服务端 count %s）——记录→定位→修复，不静默吞差"
                      % (metric_id, local, server), file=sys.stderr)
                return 1
            if metric_id in metrics:
                metrics[metric_id]["crossCheck"] = {
                    "command": count_cmd(obj_type, where, snap_id),
                    "serverCount": server,
                    "match": True,
                }

    # ================= 输出 =================

    report = {
        "schemaVersion": SCHEMA_VERSION,
        "implementation": IMPLEMENTATION,
        "owner": args.owner,
        "repo": args.repo,
        "sourceId": source_id,
        "snapshot": {
            "snapshotId": snap_id,
            "status": target.get("status"),
            "sourceVersion": target.get("sourceVersion"),
            "objectCount": int(target.get("objectCount") or 0),
            "linkCount": int(target.get("linkCount") or 0),
            "completedAt": target.get("completedAt") or target.get("createdAt"),
        },
        "cliVersion": cli_version,
        "metrics": metrics,
        "nullMetrics": null_metrics,
        "dataQuality": data_quality,
    }
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print("report written: %s（metrics=%d nullMetrics=%d dq=%d）" % (
        out_path, len(metrics), len(null_metrics), len(data_quality)))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeError as e:
        print("FAIL: %s" % e, file=sys.stderr)
        sys.exit(1)
