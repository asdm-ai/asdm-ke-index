#!/usr/bin/env python3
# =============================================================================
# KE Index · L1 指标计算（5.1.4 全量指标版——A1/C1 图闭包 + D1 策略 + D4 时序）
# -----------------------------------------------------------------------------
# 用法（GitHub Actions 与本地复算同形）：
#   KE_SERVER_URL=https://... KE_API_KEY=... python3 scripts/compute-metrics.py \
#     --owner macrozheng --repo mall \
#     [--ke-cli "ke"] [--source-id mall] [--snapshot <id>] \
#     [--out reports/macrozheng/mall.json]
#
# 方法论：AOS Index Metrics Schema draft v1（四域 A-D + dq）。
#   - 明细拉取：ke query 七类核心对象（Table/Mapper/Package/Interface/Class/
#     Method/Dependency）+ 条件拉取前端类（ApiEndpoint/Module/Component 存在时）
#   - 内存聚合：双条件判定（A3/A4）、Tarjan SCC（B1）、nearest-rank 分位（C2）、
#     比率指标（B3/C3/C4）、规模画像（D3）
#   - 5.1.4（A1/C1/D1/D4 补全——P2-D16 第一优先级）：
#     * A1/C1：graph 端点 NDJSON 全量边拉取 + 本地 calls 闭包 BFS +
#       Method→Mapper FQN join（V5.1.4.3 过渡形态；图查询形态见 graph-metrics.py）
#     * D1：framework-policy.json 目标 semver 区间匹配（运营策略输入）
#     * D4：历史 report 差分（同 source 多快照时序）
#     * stats 端点单次收敛（14 次 ke count → 1 次 /api/ontology/stats）
#   - 交叉验证：分子/基数与 `ke count --where` 服务端计数逐位对账——不一致
#     即失败（记录→定位→修复，不静默吞差）；graph 边总数 vs 快照 linkCount
#     通道不一致即失败（拉取完整性硬判据）
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
import re
import shlex
import subprocess
import sys
import urllib.parse
import urllib.request
from collections import deque
from math import ceil

SCHEMA_VERSION = "draft-v1"
IMPLEMENTATION = "ke-index compute-metrics.py (5.1.4 full metrics: A1/C1 graph closure, D1 policy, D4 trend; to be superseded by ke checkup)"

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
# 5.1.4 · HTTP 直连面（stats 收敛 / graph NDJSON 拉取——Bearer 同 CLI token）
# =============================================================================

def http_json(url, token, timeout=120):
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + token})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def http_ndjson(url, token, timeout=900):
    """流式拉取 NDJSON 端点（graph 全量 dump——逐行 yield，避免大仓整载）。"""
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + token})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        for raw in resp:
            line = raw.strip()
            if line:
                try:
                    yield json.loads(line)
                except ValueError:
                    continue


def api_cmd(path):
    """可复算指令记录（HTTP 端点形态——curl 占位与 ke 命令同风格）。"""
    return 'curl -s -H "Authorization: Bearer $KE_API_KEY" "$KE_SERVER_URL%s"' % path


# =============================================================================
# 5.1.4 · framework-policy（D1 目标 semver 区间——运营策略输入，非工程事实）
# =============================================================================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_POLICY_PATH = os.path.join(SCRIPT_DIR, "framework-policy.json")


def load_framework_policy(path=None):
    with open(path or DEFAULT_POLICY_PATH, encoding="utf-8") as f:
        policy = json.load(f)
    frameworks = policy.get("frameworks") or []
    if not frameworks:
        raise KeError("framework-policy.json 无 frameworks 条目")
    return policy


def version_key(v):
    """宽松版本序键：取前导数字段（"5.3.39-RELEASE"→(5,3,39)；"1.2.23.Final"→(1,2,23)）。
    无数字段（如 "jdk18on" 起头）→ 空元组（参与比较但排序最前——不满足任何 >= 下界）。"""
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


def _key_tuple_pad(a, b):
    width = max(len(a), len(b))
    return a + (0,) * (width - len(a)), b + (0,) * (width - len(b))


def satisfies_range(version, range_expr):
    """semver 区间判定："">=2.7.0 <4.0.0"" / "">=3.5"" / ""=8.0.33""——空格分隔多约束全与。"""
    if not version:
        return False
    vk = version_key(version)
    for token in str(range_expr).split():
        m = re.match(r"^(>=|<=|>|<|=)\s*(.+)$", token)
        if not m:
            return False
        op, ref = m.group(1), m.group(2)
        rvk = version_key(ref)
        a, b = _key_tuple_pad(vk, rvk)
        if op == ">=" and not a >= b:
            return False
        if op == "<=" and not a <= b:
            return False
        if op == ">" and not a > b:
            return False
        if op == "<" and not a < b:
            return False
        if op == "=" and a != b:
            return False
    return True


def is_determinable_version(v):
    """可判定版本：非空且非属性占位（"${...}"）。"""
    return bool(v) and isinstance(v, str) and "${" not in v


# =============================================================================
# 5.1.4 · A1/C1 闭包算法（calls 出边 BFS + Method→Mapper FQN join）
# =============================================================================

def strip_type_prefix(node_id):
    """对象 id 剥类型前缀取裸 FQN（"mtd:com.x.Y.m"→"com.x.Y.m"；无前缀原样）。"""
    return node_id.split(":", 1)[1] if ":" in node_id else node_id


def declaring_fqn(method_id):
    """方法 id → 声明者 FQN（去末段方法名——与 Mapper.namespace 裸 FQN 同形）。"""
    fqn = strip_type_prefix(method_id)
    return fqn.rsplit(".", 1)[0] if "." in fqn else ""


def closure_chain(start_method, calls_adj, mapper_by_ns):
    """calls 出边 BFS（本地完整闭包——无深度上限）。

    返回 (first_table_level, closure_size, mapper_method_count)：
    - first_table_level：首个"所属 Mapper 带 mappedTableIds"方法的 BFS 层
      （起点=0；边数语义——多链取最短即 BFS 首中；None=未贯通）
    - closure_size：闭包节点数（含起点）
    - mapper_method_count：闭包中命中 Mapper namespace 的方法数
    """
    q = deque([(start_method, 0)])
    visited = {start_method}
    first_table_level = None
    mapper_methods = 0
    while q:
        node, lvl = q.popleft()
        mp = mapper_by_ns.get(declaring_fqn(node))
        if mp is not None:
            mapper_methods += 1
            if first_table_level is None and (mp.get("mappedTableIds") or []):
                first_table_level = lvl
        for nxt in calls_adj.get(node, ()):
            if nxt not in visited:
                visited.add(nxt)
                q.append((nxt, lvl + 1))
    return first_table_level, len(visited), mapper_methods


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


def _bucketize(vals):
    """值→计数分布（C1 跳数直方图——离散小值域）。"""
    out = {}
    for v in vals:
        out[v] = out.get(v, 0) + 1
    return out


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


# =============================================================================
# 仓规模（文件数 / 行数——repo-scale.py 产物 → D3 规模画像 scale 子对象）
# =============================================================================

# repo-scale.py files 区原样保留的键（byLanguage 单独平铺为 filesByLanguage）
SCALE_FILE_KEYS = ("tracked", "skippedByAnalyzerDirs", "nonRegular", "total", "text", "binary")


def _is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def load_scale(path):
    """读 repo-scale.py 产物并校验形态；path 为空 → None（未采集——旧形态）。

    校验失败抛 KeError（FAIL 不静默降级）：规模数据残缺/畸形时 report 不算
    完整结论——与 count 交叉验证不一致即失败同一判据。
    """
    if not path:
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as e:
        raise KeError("--scale-json 不可读 %s：%s" % (path, e))
    files = data.get("files") if isinstance(data, dict) else None
    lines = data.get("lines") if isinstance(data, dict) else None
    if not isinstance(files, dict) or not isinstance(lines, dict) \
            or not all(_is_int(files.get(k)) for k in SCALE_FILE_KEYS) \
            or not _is_int(lines.get("total")) \
            or not isinstance(files.get("byLanguage", {}), dict) \
            or not isinstance(lines.get("byLanguage", {}), dict):
        raise KeError("--scale-json 形态不符（缺 files/lines 计数键）：%s" % path)
    return data


def scale_block(ke, snap_id, scale):
    """repo-scale 产物 → report D3.scale（含服务端 Repository.fileCount 对照）。

    对照口径：files.total 与分析器 Repository.fileCount 同口径（tracked 剔除
    跳过目录 + 非普通文件）——两路独立实现（CI 侧 git ls-files vs 分析器
    fs walk）读同一提交，相等即互证；不等只告警不置红（符号链接 / 子模块 /
    跳过目录差异属已知口径差——用户裁决 2026-11-26），差值原样入 report。
    服务端查询失败 fail-open（对照置 null + 注记）：规模数据本身来自 CI 侧
    clone，不依赖服务端可用性。
    """
    files = scale["files"]
    by_lang_files = files.get("byLanguage") or {}
    by_lang_lines = scale["lines"].get("byLanguage") or {}
    block = {
        "collectedBy": "scan",
        "sourceHead": scale.get("sourceHead"),
        "method": scale.get("method"),
        "fileCount": files["total"],
        "javaFiles": by_lang_files.get("java", 0),
        "lineCount": scale["lines"]["total"],
        "javaLines": by_lang_lines.get("java", 0),
        "files": {k: files[k] for k in SCALE_FILE_KEYS},
        "filesByLanguage": by_lang_files,
        "linesByLanguage": by_lang_lines,
        "bytes": (scale.get("bytes") or {}).get("total"),
        "commands": [
            "python3 scripts/repo-scale.py --repo <clone> --out <file>  # scan-one.sh clone 后 / scale-backfill.py 检出 snapshot.sourceHead 后执行",
            query_cmd("Repository", ["id", "fileCount"], snap_id),
        ],
    }
    print("scale fileCount cross-check: CI=%d" % files["total"])
    try:
        rows = ke.query("Repository", ["id", "fileCount"], snap_id)
    except KeError as e:
        block["serverFileCount"] = None
        block["fileCountMatch"] = None
        block["fileCountMatchNote"] = "服务端 Repository.fileCount 查询失败（fail-open）：%s" % e
        print("WARN: %s" % block["fileCountMatchNote"], file=sys.stderr)
        return block
    server = None
    if len(rows) == 1:
        raw = rows[0].get("fileCount")
        if _is_int(raw):
            server = raw
        elif isinstance(raw, str) and raw.isdigit():
            server = int(raw)
    if server is None:
        block["serverFileCount"] = None
        block["fileCountMatch"] = None
        block["fileCountMatchNote"] = "服务端 Repository 行数或 fileCount 字段形态异常（rows=%d）" % len(rows)
        print("WARN: %s" % block["fileCountMatchNote"], file=sys.stderr)
        return block
    match = server == files["total"]
    block["serverFileCount"] = server
    block["fileCountMatch"] = match
    print("scale fileCount cross-check: CI=%d server=%d %s" % (
        files["total"], server, "OK" if match else "MISMATCH"))
    if not match:
        block["fileCountMatchNote"] = (
            "CI 侧与分析器 Repository.fileCount 口径差（符号链接/子模块/跳过目录）——告警不置红，差值 %d" % (files["total"] - server))
        print("::warning::仓规模 fileCount 对照不一致：CI=%d server=%d（已知口径差，不置红——见 report D3.scale.fileCountMatchNote）"
              % (files["total"], server))
    return block


def main():
    ap = argparse.ArgumentParser(description="KE Index L1 指标计算（过渡实现）")
    ap.add_argument("--owner", required=True, help="GitHub owner（如 macrozheng）")
    ap.add_argument("--repo", required=True, help="仓库名（如 mall；亦为导入 sourceId）")
    ap.add_argument("--source-id", default=None, help="导入 sourceId（缺省 = repo 名）")
    ap.add_argument("--snapshot", default=None, help="目标快照 ID（缺省取该 source 最新 complete 快照）")
    ap.add_argument("--source-head", default=None, help="源仓 git HEAD sha（scan-one clone 后提取——跳过判据锚；缺省省略该字段）")
    ap.add_argument("--ke-cli", default="ke", help='ke CLI 命令（缺省 "ke"——PATH 指令形态，需 bin 已注入 PATH）')
    ap.add_argument("--url", default=os.environ.get("KE_SERVER_URL"), help="aos-server 基址（缺省读 KE_SERVER_URL）")
    ap.add_argument("--token", default=os.environ.get("KE_API_KEY"), help="API key（缺省读 KE_API_KEY）")
    ap.add_argument("--out", default=None, help="输出文件（缺省 reports/{owner}/{repo}.json）")
    ap.add_argument("--framework-policy", default=None,
                    help="framework-policy.json 路径（缺省 scripts/ 同目录）")
    ap.add_argument("--skip-cross-check", action="store_true", help="跳过 count 交叉验证（仅调试用）")
    ap.add_argument("--scale-json", default=None,
                    help="repo-scale.py 产物（scan-one.sh clone 后生成的仓规模采集——文件数/行数）；"
                         "传入即并入 report D3 规模画像 scale 子对象；缺省省略该子对象（本地复算旧形态）")
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

    # ---- 仓规模采集产物（文件数 / 行数——scan-one.sh clone 后生成）----
    # 采集对象必须就是本快照分析的提交：scale.sourceHead 与快照 sourceVersion
    # （import start --commit 落锚）不等即采集对象错位——规模数据会挂到错误的
    # 提交上，FAIL 不静默降级（存量 sourceVersion="head" 无锚可比 → 跳过本判据）
    scale = load_scale(args.scale_json)
    if scale is not None:
        sv = target.get("sourceVersion")
        if isinstance(sv, str) and re.fullmatch(r"[0-9a-f]{40}", sv) and scale.get("sourceHead") != sv:
            raise KeError("scale sourceHead %s != 快照 sourceVersion %s（规模采集对象与快照提交不一致）"
                          % (scale.get("sourceHead"), sv))
        print("scale: files=%d（tracked=%d）lines=%d java=%d files / %d lines" % (
            scale["files"]["total"], scale["files"]["tracked"], scale["lines"]["total"],
            scale["files"]["byLanguage"].get("java", 0), scale["lines"]["byLanguage"].get("java", 0)))

    # ---- 14 类型 count（5.1.4：stats 端点单次收敛——14 次 ke count → 1 次 HTTP）----
    # objectCounts 源自 manifest 键控 GROUP BY（与 legacy ke count 异源）——
    # 收敛后双通道对账价值保持：下方明细拉取数 vs stats objectCounts 逐位对照。
    base = args.url.rstrip("/")
    stats = http_json("%s/api/ontology/stats?snapshotId=%s" % (base, urllib.parse.quote(snap_id)), args.token)
    if not stats.get("ok"):
        print("FAIL: /api/ontology/stats 返回 ok!=true", file=sys.stderr)
        return 1
    counts = {t: int((stats.get("objectCounts") or {}).get(t, 0)) for t in OBJECT_TYPES}
    stats_link_total = sum(int(v) for v in (stats.get("linkCounts") or {}).values())
    snap_link_count = int(target.get("linkCount") or 0)
    print("typeCounts: " + json.dumps(counts, ensure_ascii=False))
    if stats_link_total != snap_link_count:
        print("FAIL: stats linkCounts 合计 %d != 快照 linkCount %d（通道不一致）" % (
            stats_link_total, snap_link_count), file=sys.stderr)
        return 1

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

    # ---- 5.1.4 图数据拉取（A1/C1 数据源 + 拉取完整性硬判据）----
    # graph 端点 NDJSON 全量 dump（meta + node + edge 行）；A1/C1 仅消费 calls
    # 出边。完整性断言：实拉边行数 == meta.edgeCount == 快照 linkCount——通道
    # 不一致即 FAIL（服务端 SQL 直查与 Neo4j 投影均满足——route 无关数据等价）。
    # ⚠️ snapshotId 必须显式键控：端点缺省解析租户最新快照——多快照并存时
    # 显式 --snapshot（非最新）会拉错图（litemall canary 404 实证）。
    graph_meta = None
    graph_edge_rows = 0
    calls_adj = {}
    for line in http_ndjson(
            "%s/api/ontology/graph?snapshotId=%s" % (base, urllib.parse.quote(snap_id)),
            args.token):
        kind = line.get("kind")
        if kind == "meta":
            graph_meta = line
        elif kind == "edge":
            graph_edge_rows += 1
            if line.get("linkType") == "calls":
                calls_adj.setdefault(line["source"], []).append(line["target"])
    if graph_meta is None:
        print("FAIL: graph 端点无 meta 行", file=sys.stderr)
        return 1
    meta_edge_count = int(graph_meta.get("edgeCount") or 0)
    if meta_edge_count != snap_link_count or graph_edge_rows != snap_link_count:
        print("FAIL: graph 边总数不一致（meta=%d 实拉=%d 快照 linkCount=%d）" % (
            meta_edge_count, graph_edge_rows, snap_link_count), file=sys.stderr)
        return 1
    print("graph pull: edges=%d calls=%d（完整性断言过）" % (graph_edge_rows, sum(len(v) for v in calls_adj.values())))

    metrics = {}
    null_metrics = {}

    # ================= 域 A · 跨层映射 =================

    # A1 全链路贯通率（5.1.4.3）：calls 出边 BFS 闭包 + Method→Mapper FQN join
    # 口径（V5.1.4.1 定案）：分母 = 全部 ApiEndpoint（含无 backendMethodId——与
    # A2 互补：A2 量化断链面，A1 量化贯通面）；贯通 = 闭包含"所属 Mapper 带
    # mappedTableIds"的方法（端到端 = ApiEndpoint→Method→calls*→Mapper→Table）。
    if counts["ApiEndpoint"] == 0:
        null_metrics["A1"] = null_metric(
            "A1", "full-chain-coverage", "全链路贯通率", "A", "higher-better",
            "无 ApiEndpoint 对象（分母为 0，按口径降级）",
            commands=[count_cmd("ApiEndpoint", None, snap_id)],
            evidence={"apiEndpointCount": 0},
        )
    else:
        mapper_by_ns = {}
        for m in mappers:
            ns = m.get("namespace")
            if ns:
                mapper_by_ns[ns] = m
        method_id_set = {m["id"] for m in methods}
        a1_hops = []           # 贯通链跳数（C1 消费）
        a1_closure_spans = []
        a1_complete = 0
        a1_with_backend = 0
        a1_join_hits = 0
        for a in apis:
            bm = a.get("backendMethodId")
            if not bm:
                continue
            a1_with_backend += 1
            # backendMethodId 归一化（裸 FQN / 带前缀两种形态→命中方法 id 集）
            seed = bm if bm in method_id_set else ("mtd:" + bm if ("mtd:" + bm) in method_id_set else None)
            if seed is None:
                continue
            level, span, mm_count = closure_chain(seed, calls_adj, mapper_by_ns)
            a1_closure_spans.append(span)
            a1_join_hits += 1 if mm_count > 0 else 0
            if level is not None:
                a1_complete += 1
                a1_hops.append(level)
        span_sorted = sorted(a1_closure_spans)
        metrics["A1"] = metric(
            "A1", "full-chain-coverage", "全链路贯通率", "A", "higher-better",
            ratio(a1_complete, len(apis)),
            [query_cmd("ApiEndpoint", ["id", "backendMethodId", "matchedVia"], snap_id),
             query_cmd("Mapper", ["id", "namespace", "mappedTableIds"], snap_id),
             api_cmd("/api/ontology/graph")],
            numerator=a1_complete, denominator=len(apis),
            evidence={
                "apiCount": len(apis),
                "withBackendMethod": a1_with_backend,
                "chainComplete": a1_complete,
                "joinHitClosures": a1_join_hits,
                "closureSpanMedian": nearest_rank(span_sorted, 0.5) if span_sorted else 0,
                "closureSpanMax": span_sorted[-1] if span_sorted else 0,
                "algorithm": "local BFS over calls edges (graph NDJSON full pull)",
            },
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

    # C1 端到端跳数（5.1.4.3）：A1 贯通链的 calls 边数（口径 V5.1.4.1——跳数 =
    # BFS 边数语义：backendMethod→首个"所属 Mapper 带表映射"方法的最短路径；
    # api↔method 与 mapper↔table 两段为结构映射不计入调用跳数；多链取最短）
    if counts["ApiEndpoint"] == 0:
        null_metrics["C1"] = null_metric(
            "C1", "endpoint-table-hops", "端到端跳数", "C", "interval",
            "无 ApiEndpoint 对象（贯通链分母为 0）",
            evidence={"apiEndpointCount": 0},
        )
    elif not a1_hops:
        null_metrics["C1"] = null_metric(
            "C1", "endpoint-table-hops", "端到端跳数", "C", "interval",
            "无贯通链（全部 API 闭包未到达带表映射的 Mapper——跳数分布分母为 0）",
            evidence={"apiEndpointCount": counts["ApiEndpoint"],
                      "chainComplete": a1_complete},
        )
    else:
        hops_sorted = sorted(a1_hops)
        metrics["C1"] = metric(
            "C1", "endpoint-table-hops", "端到端跳数", "C", "interval",
            nearest_rank(hops_sorted, 0.50),
            [query_cmd("ApiEndpoint", ["id", "backendMethodId"], snap_id),
             api_cmd("/api/ontology/graph")],
            denominator=len(hops_sorted),
            percentiles={
                "p25": nearest_rank(hops_sorted, 0.25),
                "p50": nearest_rank(hops_sorted, 0.50),
                "p75": nearest_rank(hops_sorted, 0.75),
                "p90": nearest_rank(hops_sorted, 0.90),
            },
            min=hops_sorted[0],
            max=hops_sorted[-1],
            mean=round(sum(hops_sorted) / len(hops_sorted), 4),
            hopsBasis="calls edges, shortest BFS path (V5.1.4.1 定案)",
            distribution={str(k): v for k, v in sorted(
                _bucketize(hops_sorted).items())},
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

    # D1 版本覆盖率（5.1.4.5）：framework-policy.json 目标区间匹配——
    # 分母 = 匹配策略框架且版本可判定的依赖；分子 = 落在目标区间的。
    # 非框架依赖不入 D1 分母（策略表之外的栈不构成覆盖率判定面）。
    empty_ver = sum(1 for d in deps if not d.get("version"))
    placeholder_ver = sum(1 for d in deps if isinstance(d.get("version"), str) and "${" in d["version"])
    try:
        policy = load_framework_policy(args.framework_policy)
    except (OSError, ValueError) as e:
        print("FAIL: framework-policy.json 不可读：%s" % e, file=sys.stderr)
        return 1
    d1_frameworks = []
    d1_framework_deps = []   # 逐框架命中依赖清单（census D2 cohort 聚合消费面）
    d1_in_range = 0
    d1_determinable = 0
    for fw in policy.get("frameworks", []):
        fw_name = fw.get("framework") or "?"
        matches_list = fw.get("match") or []
        target_range = fw.get("targetRange") or ""
        matched = [d for d in deps
                   if isinstance(d.get("name"), str)
                   and any(d["name"].startswith(pfx) for pfx in matches_list)]
        det = [d for d in matched if is_determinable_version(d.get("version"))]
        in_range = [d for d in det if satisfies_range(d.get("version"), target_range)]
        d1_determinable += len(det)
        d1_in_range += len(in_range)
        d1_frameworks.append({
            "framework": fw_name,
            "targetRange": target_range,
            "matched": len(matched),
            "determinable": len(det),
            "inRange": len(in_range),
            "outOfRange": sorted([
                {"name": d["name"], "version": d["version"]}
                for d in det if d not in in_range], key=lambda x: x["name"]),
        })
        d1_framework_deps.extend(
            {"framework": fw_name, "name": d["name"], "version": d.get("version") or ""}
            for d in sorted(matched, key=lambda x: x["name"]))
    if d1_determinable == 0:
        d1_reason = "无可判定版本（策略框架命中 0 或全部空串/占位——分母为 0，按口径置空）"
        determinable_all = len(deps) - empty_ver - placeholder_ver
        if len(deps) and determinable_all:
            d1_reason = "策略框架命中依赖无可判定版本（全仓可判定版本 %d 个均不匹配策略表）" % determinable_all
        null_metrics["D1"] = null_metric(
            "D1", "framework-version-coverage", "技术栈版本覆盖率", "D", "higher-better",
            d1_reason,
            commands=[query_cmd("Dependency", ["id", "name", "version", "scope"], snap_id)],
            evidence={"total": len(deps), "emptyVersion": empty_ver,
                      "placeholder": placeholder_ver,
                      "determinableAll": len(deps) - empty_ver - placeholder_ver,
                      "policyMatched": sum(f["matched"] for f in d1_frameworks),
                      "frameworks": d1_frameworks},
        )
    else:
        metrics["D1"] = metric(
            "D1", "framework-version-coverage", "技术栈版本覆盖率", "D", "higher-better",
            ratio(d1_in_range, d1_determinable),
            [query_cmd("Dependency", ["id", "name", "version", "scope"], snap_id)],
            numerator=d1_in_range, denominator=d1_determinable,
            evidence={
                "total": len(deps), "emptyVersion": empty_ver,
                "placeholder": placeholder_ver,
                "policy": os.path.basename(args.framework_policy or DEFAULT_POLICY_PATH),
                "frameworks": d1_frameworks,
            },
            frameworkDeps=d1_framework_deps,
        )

    # D2 依赖同质度：cohort 级指标（单体层不产出）
    null_metrics["D2"] = null_metric(
        "D2", "dependency-homogeneity", "依赖同质度", "D", "none",
        "cohort 级指标（依赖 cohort 众数集合——单体层不产出）",
        evidence={"dependencyCount": len(deps)},
    )

    # D3 规模画像（描述型：objectCount / linkCount / typeCounts；有仓规模采集
    # 产物时并入 scale 子对象——文件数 / 行数，仓规模的文件级参照）
    metrics["D3"] = metric(
        "D3", "scale-profile", "规模画像", "D", "none",
        int(target.get("objectCount") or 0),
        ["ke --mode server --url \"$KE_SERVER_URL\" --token \"$KE_API_KEY\" snapshot list --repo " + source_id]
        + [count_cmd(t, None, snap_id) for t in OBJECT_TYPES],
        typeCounts={t: counts[t] for t in OBJECT_TYPES},
        linkCount=int(target.get("linkCount") or 0),
    )
    if scale is not None:
        metrics["D3"]["scale"] = scale_block(ke, snap_id, scale)

    # D4 年度演进趋势（5.1.4.5）：历史 report 差分（同 source 多快照时序）——
    # 磁盘上的既有 report（上轮 scan 提交产物）与本次快照不同时，输出逐指标
    # delta + 规模增速。单快照/同快照重算/无历史文件 → null（口径性合法）。
    snap_count = len(complete)
    prev_report = None
    if out_path and os.path.exists(out_path):
        try:
            with open(out_path, encoding="utf-8") as f:
                prev_report = json.load(f)
        except (OSError, ValueError):
            prev_report = None
    prev_snap = (prev_report or {}).get("snapshot", {})
    prev_snap_id = prev_snap.get("snapshotId")
    d4_snapshot_cmd = ("ke --mode server --url \"$KE_SERVER_URL\" --token \"$KE_API_KEY\" "
                       "snapshot list --repo " + source_id)
    if prev_report is None or prev_snap_id == snap_id or snap_count <= 1:
        d4_reason = "单快照（首次导入——无时序）" if snap_count <= 1 else (
            "无历史 report 或为同快照重算（时序分母为 0）")
        null_metrics["D4"] = null_metric(
            "D4", "evolution-trend", "年度演进趋势", "D", "none",
            d4_reason,
            commands=[d4_snapshot_cmd],
            evidence={"completeSnapshotCount": snap_count,
                      "previousReportSnapshot": prev_snap_id},
        )
    else:
        prev_metrics = prev_report.get("metrics", {})
        d4_deltas = {}
        for mid, m in sorted(metrics.items()):
            pv = (prev_metrics.get(mid) or {}).get("value")
            cv = m.get("value")
            if (isinstance(pv, (int, float)) and not isinstance(pv, bool)
                    and isinstance(cv, (int, float)) and not isinstance(cv, bool)):
                d4_deltas[mid] = {"prev": pv, "curr": cv,
                                  "delta": round(cv - pv, 6)}
        prev_obj = int(prev_snap.get("objectCount") or 0)
        curr_obj = int(target.get("objectCount") or 0)
        growth = round((curr_obj - prev_obj) / prev_obj, 6) if prev_obj else None
        metrics["D4"] = metric(
            "D4", "evolution-trend", "年度演进趋势", "D", "none",
            growth,
            [d4_snapshot_cmd],
            evidence={
                "completeSnapshotCount": snap_count,
                "previousSnapshot": {
                    "snapshotId": prev_snap_id,
                    "objectCount": prev_obj,
                    "linkCount": int(prev_snap.get("linkCount") or 0),
                    "completedAt": prev_snap.get("completedAt"),
                },
                "metricDeltas": d4_deltas,
                "valueBasis": "objectCount 环比增速（prev→curr）",
            },
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
            "sourceHead": args.source_head or None,  # 源仓 git HEAD（preflight 跳过判据锚；空值归一为 null）
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
