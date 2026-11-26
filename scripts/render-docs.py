#!/usr/bin/env python3
"""Render the public documentation of asdm-ke-index from the repo's own artifacts.

The README is the entry page of KE (存量系统认知引擎 / Legacy System Cognition Engine):
positioning, the published reference lines, data scale and coverage (what the engine really scanned), how to use it, and how the
numbers can be checked. Everything else lives under docs/.

Outputs (two languages, same structure):
  README.md / README_zh-cn.md          entry page
  docs/METRICS.md / _zh-cn.md          definitions and raw numbers of the published reference lines only
  docs/CORPUS.md / _zh-cn.md           full per-repository table and scale analysis
  docs/PIPELINE.md / _zh-cn.md         how the data is produced and verified

Publishing rule: a reference line is published when at least PUBLISH_N systems carry a value.
Only metrics described in PUBLISHED are rendered. A metric that reaches the threshold without
an entry in PUBLISHED stops the run: publishing it needs a written definition first.

Inputs (read-only): repos.yaml, census/summary.json, reports/{owner}/{repo}.json,
pipeline-status/{owner}/{repo}.json. Standard library only.

Usage:
    python3 scripts/render-docs.py --meta meta.json --out /tmp/x        # dry run to a directory
    python3 scripts/render-docs.py --meta docs/baseline.json                 # reproduce the published pages byte for byte
    python3 scripts/render-docs.py --run-id ID --run-number N --started-at ISO --completed-at ISO   # meta built from a workflow run

meta.json keys: run_id, run_number, started_at, completed_at, duration,
baseline_date (the start date). With --run-id the meta is built instead. Whichever way it arrives,
it is written to docs/baseline.json, so the published pages can always be reproduced from the repository.

The rendered files are rewritten by every run, so edit the copy here, not the Markdown.

Stops (non-zero exit, nothing published) when a metric reaches the publish threshold without an
entry in PUBLISHED, or when the systems were measured with more than one analyzer version.
"""
import argparse
import json
import os
import re
import statistics
from collections import defaultdict
from urllib.parse import quote

PUBLISH_N = 30

# kind: "ratio" is shown as a percentage on the entry page, "num" as a plain number.
PUBLISHED = {
    "B1.backend": {
        "kind": "ratio", "en": "Circular dependency density", "zh": "循环依赖密度",
        "def_en": "Share of all packages that sit in a dependency cycle (two or more packages that can reach each other)",
        "def_zh": "处在循环依赖中的包占全部包的比例（两个及以上的包互相可达即为成环）",
        "how_en": "Tarjan strongly connected components over the repository's package dependency graph. Numerator: packages in components of two or more. Denominator: all packages.",
        "how_zh": "对单仓的包依赖图做 Tarjan 强连通分量分解。分子：大小不小于 2 的分量中的包数；分母：全部包数。",
    },
    "B2": {
        "kind": "num", "en": "Package dependency density", "zh": "包依赖密度",
        "def_en": "Dependency edges between packages divided by the number of packages",
        "def_zh": "包与包之间的依赖边数除以包数",
        "how_en": "Numerator: `dependsOn` edges between packages of the repository. Denominator: number of packages.",
        "how_zh": "分子：仓内包之间的 `dependsOn` 边数；分母：包数。",
    },
    "B3": {
        "kind": "ratio", "en": "Giant-class share", "zh": "巨型类占比",
        "def_en": "Share of all classes with more than 500 lines",
        "def_zh": "超过 500 行的类占全部类的比例",
        "how_en": "Numerator: classes with `lineCount > 500`. Denominator: all classes.",
        "how_zh": "分子：`lineCount > 500` 的类；分母：全部类。",
    },
    "C2": {
        "kind": "num", "en": "Cyclomatic complexity (P90)", "zh": "圈复杂度 P90",
        "def_en": "The cyclomatic complexity that 90% of methods stay within (90th percentile over methods that carry a complexity value)",
        "def_zh": "90% 的方法圈复杂度不超过该值（在有圈复杂度取值的方法上取第 90 百分位）",
        "how_en": "Nearest-rank 90th percentile of per-method cyclomatic complexity. Denominator: methods with a complexity value.",
        "how_zh": "对每个方法的圈复杂度取最近秩第 90 百分位；分母：有圈复杂度取值的方法。",
    },
    "C3": {
        "kind": "ratio", "en": "Test-method share", "zh": "测试方法占比",
        "def_en": "Test methods as a share of all methods",
        "def_zh": "测试方法占全部方法的比例",
        "how_en": "Numerator: methods flagged as tests. Denominator: all methods.",
        "how_zh": "分子：标记为测试的方法；分母：全部方法。",
    },
    "C4": {
        "kind": "ratio", "en": "Giant-method share", "zh": "巨型方法占比",
        "def_en": "Share of methods with more than 80 lines, among methods with a recorded line count",
        "def_zh": "超过 80 行的方法占有行数记录的方法的比例",
        "how_en": "Numerator: methods with `lineCount > 80`. Denominator: methods with a recorded line count (zero or missing line counts are excluded).",
        "how_zh": "分子：`lineCount > 80` 的方法；分母：有行数记录的方法（行数为 0 或缺失的不计）。",
    },
}

# Shape descriptions name categories only, never individual repositories, so they stay true
# when the corpus grows. The tier definitions are in the header of repos.yaml.
TIER = {
    "A": {"short_en": "Business systems", "short_zh": "业务系统",
          "shape_en": "Java admin scaffolds and business systems, plus e-commerce / office / tooling systems",
          "shape_zh": "Java 脚手架与业务系统，以及电商、办公、工具类业务系统"},
    "B": {"short_en": "Large multi-module", "short_zh": "大型多模块",
          "shape_en": "very large multi-module repositories: Apache middleware and cornerstone repos of the Spring ecosystem",
          "shape_zh": "超大型多模块仓库：Apache 系中间件与 Spring 生态基石"},
    "C": {"short_en": "JPA applications", "short_zh": "JPA 企业应用",
          "shape_en": "JPA-shaped systems: IAM / BPM / ERP applications and the JPA implementation itself",
          "shape_zh": "JPA 形态的系统：IAM / BPM / ERP 应用与 JPA 实现本体"},
    "D": {"short_en": "Frontend projects", "short_zh": "前端工程",
          "shape_en": "the official frontend repos of the business systems (Vue)",
          "shape_zh": "业务系统的官方前端仓库（Vue 系）"},
}

DIRECTION = {"lower-better": ("Lower is better", "越低越好"),
             "higher-better": ("Higher is better", "越高越好"),
             "interval": ("Range", "区间型")}


# ---------------------------------------------------------------------------- data
def n(x):
    return f"{x:,}"


def p(x, nd=4):
    s = f"{x:.{nd}f}".rstrip("0").rstrip(".")
    return "0" if s in ("", "-0") else s


def pct(x):
    v = x * 100
    return f"{v:.2f}%" if v < 1 else f"{v:.1f}%"


def parse_repos_yaml(path):
    repos, cur = [], None
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            m = re.match(r"^\s*-\s*owner:\s*(\S+)\s*$", line)
            if m:
                cur = {"owner": m.group(1)}
                repos.append(cur)
                continue
            if cur is None:
                continue
            for key in ("repo", "branch"):
                m = re.match(rf"^\s*{key}:\s*(\S+)\s*$", line)
                if m:
                    cur[key] = m.group(1)
            m = re.match(r"^\s*skip:\s*(\S+)\s*$", line)
            if m:
                cur["skip"] = m.group(1).lower() == "true"
            m = re.match(r"^\s*notes:\s*\"?(.*?)\"?\s*$", line)
            if m:
                cur["notes"] = m.group(1)
    return [r for r in repos if not r.get("skip") and r.get("repo")]


def scale_of(report):
    return ((report.get("metrics") or {}).get("D3") or {}).get("scale") if report else None


def load(repo):
    with open(os.path.join(repo, "census", "summary.json"), encoding="utf-8") as f:
        census = json.load(f)
    repos = []
    for r in parse_repos_yaml(os.path.join(repo, "repos.yaml")):
        item = dict(r)
        item["name"] = f"{r['owner']}/{r['repo']}"
        item["tier"] = (r.get("notes") or "?")[0]
        rp = os.path.join(repo, "reports", r["owner"], f"{r['repo']}.json")
        sp = os.path.join(repo, "pipeline-status", r["owner"], f"{r['repo']}.json")
        item["report"] = json.load(open(rp, encoding="utf-8")) if os.path.exists(rp) else None
        item["status"] = json.load(open(sp, encoding="utf-8")) if os.path.exists(sp) else None
        repos.append(item)
    return {"root": repo, "census": census, "repos": repos}


def compute(d):
    c, repos, s = d["census"], d["repos"], {}
    d["stats"] = s
    s["n"] = len(repos)
    s["n_reports"] = sum(1 for r in repos if r["report"])
    s["n_status"] = sum(1 for r in repos if r["status"])
    for step in ("scan", "projection", "metrics", "consistency"):
        s["ok_" + step] = sum(1 for r in repos if r["status"] and r["status"]["steps"].get(step) == "ok")
    s["cons_pass"] = sum(1 for r in repos if r["status"] and r["status"].get("consistencyResult") == "pass")
    s["failed"] = [r["name"] for r in repos if not r["status"] or r["status"].get("overall") != "pass"]
    s["overall_pass"] = len(repos) - len(s["failed"])
    s["cli"] = sorted({r["report"]["cliVersion"] for r in repos if r["report"] and r["report"].get("cliVersion")})
    if len(s["cli"]) > 1:
        raise SystemExit(f"not publishing: the systems were measured with more than one analyzer version {s['cli']}; "
                         "rescan the stale repositories first")
    s["samples"], s["census_status"], s["schema"] = c["samples"], c["status"], c["schemaVersion"]
    s["gate"], s["validation"] = c["gate"], c["validation"]

    # publishing rule
    ready = sorted(k for k, m in c["metrics"].items() if (m or {}).get("N", 0) >= PUBLISH_N)
    undescribed = [k for k in ready if k not in PUBLISHED]
    if undescribed:
        raise SystemExit("reached the publish threshold but has no entry in PUBLISHED (write a definition first): "
                         + ", ".join(undescribed))
    s["published"] = [k for k in PUBLISHED if k in ready]
    s["N"] = {k: c["metrics"][k]["N"] for k in s["published"]}

    # which repos carry no value for the first published line, split by frontend tier
    first = s["published"][0]
    nov = [r for r in repos if not ((r["report"] or {}).get("metrics") or {}).get(first)]
    s["no_val"] = len(nov)
    s["no_val_frontend"] = sum(1 for r in nov if r["tier"] == "D")

    # cross-checks of the published metrics, read from the per-repo reports
    xc = {}
    for mid in s["published"]:
        match = mismatch = 0
        for r in repos:
            ck = ((r["report"] or {}).get("metrics") or {}).get(mid, {}).get("crossCheck")
            if ck is None:
                continue
            if ck.get("match"):
                match += 1
            else:
                mismatch += 1
        xc[mid] = {"match": match, "mismatch": mismatch, "checked": match + mismatch > 0}
    s["xcheck"] = xc

    # scale
    sc = [r for r in repos if scale_of(r["report"])]
    s["n_scale"] = len(sc)
    s["fm"] = c["cohort"]["scale"]["fileCountMatch"]
    for key in ("fileCount", "javaFiles", "lineCount", "javaLines"):
        vals = [scale_of(r["report"])[key] for r in sc]
        s[key] = {"sum": sum(vals), "min": min(vals), "median": int(statistics.median(vals)), "max": max(vals)}
    s["d3_scale"] = c["cohort"]["scale"]["metrics"]
    s["tier_counts"] = {t: sum(1 for r in repos if r["tier"] == t) for t in "ABCD"}
    s["tier_scale"] = {}
    for t in "ABCD":
        rs = [r for r in sc if r["tier"] == t]
        if rs:
            s["tier_scale"][t] = {
                "n": len(rs),
                "fileCount": int(statistics.median(scale_of(r["report"])["fileCount"] for r in rs)),
                "lineCount": int(statistics.median(scale_of(r["report"])["lineCount"] for r in rs)),
                "javaLines": int(statistics.median(scale_of(r["report"])["javaLines"] for r in rs)),
                "sumJavaLines": sum(scale_of(r["report"])["javaLines"] for r in rs),
            }
    lang_lines, lang_files = defaultdict(int), defaultdict(int)
    tracked = text = binary = 0
    for r in sc:
        scl = scale_of(r["report"])
        for k, v in (scl.get("linesByLanguage") or {}).items():
            lang_lines[k] += v
        for k, v in (scl.get("filesByLanguage") or {}).items():
            lang_files[k] += v
        f = scl.get("files") or {}
        tracked += f.get("tracked") or 0
        text += f.get("text") or 0
        binary += f.get("binary") or 0
    s["lang_lines"] = sorted(lang_lines.items(), key=lambda kv: -kv[1])
    s["lang_files"] = dict(lang_files)
    s["tracked"], s["text"], s["binary"] = tracked, text, binary
    s["top_java"] = sorted(sc, key=lambda r: -scale_of(r["report"])["javaLines"])[:5]
    s["top_lines"] = sorted(sc, key=lambda r: -scale_of(r["report"])["lineCount"])[:5]
    s["java_share_lines"] = lang_lines["java"] / s["lineCount"]["sum"] * 100
    s["java_share_files"] = lang_files["java"] / s["fileCount"]["sum"] * 100

    # tier drift: tier-A repos whose largest named file group at the scanned HEAD is not `.java`
    drift = []
    for r in sc:
        if r["tier"] != "A":
            continue
        scl = scale_of(r["report"])
        fbl = {k: v for k, v in (scl.get("filesByLanguage") or {}).items() if k != "other"}
        top_lang, top_n = max(fbl.items(), key=lambda kv: kv[1]) if fbl else ("java", 0)
        if top_lang != "java" and top_n > scl["javaFiles"]:
            drift.append({"name": r["name"], "java": scl["javaFiles"], "lang": top_lang, "n": top_n})
    s["drift"] = drift
    # the system whose "other" bucket (unrecognised extensions) carries the most lines
    with_other = [(r, (scale_of(r["report"]).get("linesByLanguage") or {}).get("other", 0)) for r in sc]
    other_top = max(with_other, key=lambda x: x[1]) if with_other else (None, 0)
    # shown only when it is a real distortion: at least a tenth of that system's own lines
    s["other_top"] = (other_top[0]["name"], other_top[1]) if other_top[0] and other_top[1] >= 0.1 * scale_of(other_top[0]["report"])["lineCount"] else None
    ratios = sorted(((r["report"]["snapshot"]["linkCount"] / r["report"]["snapshot"]["objectCount"], r["name"],
                      r["report"]["snapshot"]["objectCount"], r["report"]["snapshot"]["linkCount"])
                     for r in repos if r["report"] and r["report"]["snapshot"]["objectCount"]), reverse=True)
    s["ratio_top"] = ratios[0] if ratios else None

    # knowledge-graph size per repo (objects = nodes, links = edges), for the entry page
    objs = [o for o, _l in map(graph_counts, repos) if o is not None]
    links = [l for _o, l in map(graph_counts, repos) if l is not None]
    for key, vals in (("objects", objs), ("links", links)):
        s[key] = {"sum": sum(vals), "min": min(vals), "median": int(statistics.median(vals)), "max": max(vals)} if vals else None
    s["link_top_share"] = s["ratio_top"][3] / s["links"]["sum"] * 100 if s["ratio_top"] and s["links"] else 0.0


# ----------------------------------------------------------------- shared pieces
def mname(mid, en):
    return PUBLISHED[mid]["en" if en else "zh"]


def count_word(k, en):
    """1 -> One in English (as in a sentence), otherwise the digit; Chinese always uses the digit."""
    words = ("One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine")
    return words[k - 1] if en and 1 <= k <= len(words) else str(k)


def names(d, ids, en):
    """Metric names as listed in running text (lower-cased in English)."""
    out = []
    for i in ids:
        nm = mname(i, en)
        out.append(nm[0].lower() + nm[1:] if en else nm)
    return (", " if en else "、").join(out)


def direction(d, mid, en):
    return DIRECTION[d["census"]["metrics"][mid]["direction"]][0 if en else 1]


def ref_rows(d, en, raw=False):
    """Rows of the reference-line table. raw=False is the entry page (ratios as percentages, no N column)."""
    s, c, out = d["stats"], d["census"], []
    for mid in s["published"]:
        m, q = c["metrics"][mid], c["metrics"][mid]["percentiles"]
        fmt = (lambda x: p(x)) if raw or PUBLISHED[mid]["kind"] == "num" else pct
        cells = [mname(mid, en), PUBLISHED[mid]["def_en" if en else "def_zh"], direction(d, mid, en)]
        if raw:
            cells.append(str(m["N"]))
        cells += [fmt(q[k]) for k in ("p25", "p50", "p75")]
        if raw:
            cells += [p(q["p90"]), p(m["mean"])]
        out.append("| " + " | ".join(cells) + " |")
    return out


def graph_counts(r):
    """(objects, links) of a repo's snapshot, same sources as the full table; (None, None) when absent."""
    rp, st = r["report"], r["status"]
    obj = st.get("objectCount") if st else None
    link = (rp or {}).get("snapshot", {}).get("linkCount") if rp else None
    return obj, link


def scale_cells(r):
    scl = scale_of(r["report"])
    return [n(scl[k]) if scl else "—" for k in ("fileCount", "javaFiles", "lineCount", "javaLines")]


def entry_rows(d, en):
    out = []
    for i, r in enumerate(d["repos"], 1):
        typ = TIER.get(r["tier"], {}).get("short_en" if en else "short_zh", r["tier"])
        obj, link = graph_counts(r)
        cells = [n(obj) if obj is not None else "—", n(link) if link is not None else "—"] + scale_cells(r)
        out.append(f"| {i} | [{r['name']}](https://github.com/{r['name']}) | {typ} | " + " | ".join(cells) + " |")
    return out


def full_rows(d):
    out = []
    drift_names = {x["name"] for x in d["stats"]["drift"]}
    for i, r in enumerate(d["repos"], 1):
        rp, st = r["report"], r["status"]
        snap = (st or {}).get("snapshotId") or ((rp or {}).get("snapshot") or {}).get("snapshotId") or ""
        head = (st or {}).get("sourceHead") or ((rp or {}).get("snapshot") or {}).get("sourceHead") or ""
        out.append("| " + " | ".join([
            str(i), f"[{r['name']}](https://github.com/{r['name']})",
            r["tier"] + (" ⚠️" if r["name"] in drift_names else ""),
            f"`{snap[:8]}`" if snap else "—",
            f"`{head[:8]}`" if head else "—",
            f"[report]({'../reports/' + r['owner'] + '/' + r['repo'] + '.json'})",
            n(st["objectCount"]) if st and st.get("objectCount") is not None else "—",
            n(rp["snapshot"]["linkCount"]) if rp else "—",
        ] + scale_cells(r) + ["✅" if st and st.get("overall") == "pass" else "❌"]) + " |")
    return out


# ------------------------------------------------------------------- entry page
def badge(label, message, color="blue"):
    """shields.io static badge; '-' is escaped as '--' per shields' syntax."""
    enc = lambda x: quote(str(x).replace("-", "--"), safe="")
    return f"![{label}: {message}](https://img.shields.io/badge/{enc(label)}-{enc(message)}-{color}?style=flat-square)"


def badges(d, meta, en):
    """Badge row under the title. Static, and taken from the same numbers as the page."""
    s, out = d["stats"], []
    out.append(badge("License" if en else "许可证", "Apache 2.0", "blue"))
    out.append(badge("Baseline" if en else "基线", meta["baseline_date"], "green"))
    out.append(badge("Systems" if en else "系统", s["n"]))
    if en:
        out.append(badge("Lines of code", f"{s['lineCount']['sum'] / 1e6:.1f}M"))
        out.append(badge("Objects", f"{s['objects']['sum'] / 1e6:.2f}M"))
    else:
        out.append(badge("代码行数", f"{s['lineCount']['sum'] / 1e4:,.0f} 万"))
        out.append(badge("对象", f"{s['objects']['sum'] / 1e4:,.0f} 万"))
    out.append(badge("Reference lines", len(s["published"])) if en else badge("参考线", f"{len(s['published'])} 条"))
    return " ".join(out)


def readme(d, meta, en):
    s, t = d["stats"], (lambda a, b: a) if en else (lambda a, b: b)
    k, first = s["N"][s["published"][0]], s["published"][0]
    lines = s["lineCount"]["sum"]
    other = "README_zh-cn.md" if en else "README.md"
    M = "docs/METRICS.md" if en else "docs/METRICS_zh-cn.md"
    C = "docs/CORPUS.md" if en else "docs/CORPUS_zh-cn.md"
    P = "docs/PIPELINE.md" if en else "docs/PIPELINE_zh-cn.md"
    run_url = f"https://github.com/asdm-ai/asdm-ke-index/actions/runs/{meta['run_id']}"
    checked = [m for m in s["published"] if s["xcheck"][m]["checked"]]
    unchecked = [m for m in s["published"] if not s["xcheck"][m]["checked"]]
    # cross-check result, stated per line: every checked line matched in the same number of systems
    xx = sum(s["xcheck"][m]["mismatch"] for m in checked)
    xm = min((s["xcheck"][m]["match"] for m in checked), default=0)
    if xx == 0:
        xc_en = f"{xm} of {k} match on every line"
        xc_zh = f"每条都是 {xm}/{k} 一致"
    else:
        xc_en = f"{xm} of {k} match on every line, {xx} comparisons differ in total"
        xc_zh = f"每条至少 {xm}/{k} 一致，合计有 {xx} 处不一致"
    if en:
        window = f"{meta['started_at'][:10]}, {meta['started_at'][11:16]}–{meta['completed_at'][11:16]} UTC, {meta['duration']}"
    else:
        window = f"{meta['started_at'][:10]} {meta['started_at'][11:16]}–{meta['completed_at'][11:16]} UTC，用时 {meta['duration']}"
    drift_names = (", " if en else "、").join(x["name"] for x in s["drift"])
    # pipeline bullet: the wording follows the data, so a partial result can never read as "all passed"
    n_missing = len((s["validation"] or {}).get("missingRepos") or [])
    passed_label = ("**Every system passed the pipeline.**" if not s["failed"] else "**Pipeline status.**") if en else \
                   ("**全部通过管线。**" if not s["failed"] else "**管线状态。**")
    missing_en = " and none missing" if not n_missing else f", {n_missing} without a recorded conclusion"
    missing_zh = "，无缺失" if not n_missing else f"，{n_missing} 个没有结论记录"

    # centred hero block: title, slogan, one-line positioning, language switch, badges
    L = ["<div align=\"center\">", "", "# ASDM KE Index", "",
         f"**{'Let AI understand the systems a company has run for ten years, and take over every iteration of them' if en else '让 AI 读懂企业十年旧系统，接手它的每一次迭代'}**", "",
         "The public benchmark of KE, the Legacy System Cognition Engine" if en else "KE（存量系统认知引擎）的公开基准", "",
         f"English | [简体中文]({other})" if en else f"[English]({other}) | 简体中文", "",
         badges(d, meta, en), "", "</div>", "", "---", ""]
    if en:
        L += [
            "[Reference lines](#reference-lines) · [Data scale and coverage](#data-scale-and-coverage) · [How to use it](#how-to-use-it) · "
            "[Where the data comes from](#where-the-data-comes-from) · [Scope and limits](#scope-and-limits)", "",
            "| Systems | Lines of code | Reference lines | Baseline |", "|---|---|---|---|",
            f"| **{s['n']} open-source systems** | **{lines / 1e6:.1f}M lines** | **{len(s['published'])}** | **{meta['baseline_date']}** |", "",
            "## The problem", "",
            "AI writes code quickly now, but understanding a system that has been maintained for ten years is still slow. "
            "Before AI can safely take over changes to such a system, three questions need answers: how tangled is its structure, "
            "what does one change touch, and how healthy is the code?", "",
            f"KE answers the first two with a knowledge graph and impact analysis. KE Index answers the third: it runs {s['n']} well-known "
            "open-source Java systems through the same engine and turns the results into a public, checkable yardstick. "
            "Once your own system is on board, its measurements have something to be compared against.", "",
            "It is written for architecture teams modernising a core system, engineering organisations adopting AI coding tools at scale, "
            "and technical leads who need to report on system health.", "",
            "## What KE measures", "",
            "| Capability | Question it answers | Reference lines |", "|---|---|---|",
            f"| Read the structure | How tangled are the dependencies between modules | {names(d, ['B1.backend', 'B2'], True)} |",
            f"| See code quality | How hard is the code to change, and how much of it is tested | {names(d, ['B3', 'C2', 'C3', 'C4'], True)} |", "",
            f"All {len(s['published'])} published reference lines cover back-end Java code. Definitions and raw numbers: [{M}]({M}).", "",
            "## Reference lines", "",
            f"> Sample: {k} of the {s['n']} systems (the other {s['no_val']} are {s['no_val_frontend']} frontend projects and "
            f"{s['no_val'] - s['no_val_frontend']} without a Java package structure). Baseline: {meta['baseline_date']}. "
            "How the numbers are checked: [Where the data comes from](#where-the-data-comes-from).", "",
            "| Reference line | What it measures | Direction | P25 | Median (P50) | P75 |", "|---|---|---|---|---|---|",
        ] + ref_rows(d, True) + [
            "",
            "The median splits the sample in half; P25 to P75 covers the middle half of the systems. On a \"lower is better\" line, a value above "
            "P75 means the system is worse than three quarters of the sample. A range-type line has no good or bad direction: "
            "a value between P25 and P75 is common.", "",
            "## Data scale and coverage", "",
            f"Every system below was scanned by the KE engine itself; nothing is copied from a third-party statistic. "
            "Objects and links are the nodes and relationships of the knowledge graph KE built from the system. "
            "Files and lines are counted on the source tree of the scanned commit (physical lines, comments and blank lines included).", "",
            f"All {s['n']} systems in the order of [repos.yaml](repos.yaml).", "",
            "| # | Repository | Type | Objects | Links | Files | Java files | Lines | Java lines |", "|---|---|---|---|---|---|---|---|---|",
        ] + entry_rows(d, True) + [
            f"| | **Total ({s['n']})** | | **{n(s['objects']['sum'])}** | **{n(s['links']['sum'])}** | **{n(s['fileCount']['sum'])}** | "
            f"**{n(s['javaFiles']['sum'])}** | **{n(s['lineCount']['sum'])}** | **{n(s['javaLines']['sum'])}** |", "",
        ] + [f"- **{TIER[x]['short_en']} ({s['tier_counts'][x]})**: {TIER[x]['shape_en']}" for x in "ABCD"] + [
            "",
            f"**Spread.** The systems run from {n(s['lineCount']['min'])} to {n(s['lineCount']['max'])} lines of code "
            f"(median {n(s['lineCount']['median'])}) and from {n(s['objects']['min'])} to {n(s['objects']['max'])} objects.", "",
            f"**What this covers, and what it does not yet.** {s['n']} systems are not enough to stand for the open-source community as a whole. "
            "The corpus is being extended step by step, with the goal of reaching a sample proportion that is statistically meaningful. "
            "Until then, the reference lines describe this corpus.", "",
        ]
        if s["ratio_top"] and s["link_top_share"] >= 10:
            ratio, name, objs_, links_ = s["ratio_top"]
            L += [f"**One link count still to be explained.** {name} alone accounts for about {s['link_top_share']:.0f}% of all links "
                  f"({n(links_)} links for {n(objs_)} objects, about {ratio:.0f} links per object, far above the other systems). "
                  f"The cause has not been attributed yet; see [{C}]({C}).", ""]
        L += [
            f"Source version, snapshot and per-repository detail: [{C}]({C}).", "",
            "## How to use it", "",
            "1. Connect your system's repository on [kengine.ai](https://kengine.ai).",
            "2. The engine builds its knowledge graph and computes the measurements.",
            "3. Compare your values with the reference lines above to see where the system sits.", "",
            "Reference lines move with each rescan, so compare against the baseline date shown here.", "",
            "## Where the data comes from", "",
            f"- **One analyzer version.** All {s['n']} systems are measured with the same analyzer version.",
            f"- {passed_label} Scan, graph build, metric computation and the consistency step completed for "
            f"{s['overall_pass']} of {s['n']} repositories, with {len(s['failed'])} failed{missing_en}.",
        ]
        if checked:
            L += [f"- **Cross-checked lines.** For {names(d, checked, True)}, one of the two counts behind the line was compared, system by system, "
                  f"with a separate filtered count from the server: {xc_en}."]
        if unchecked:
            L += [f"- **Lines without a cross-check yet.** {names(d, unchecked, True)} are computed in one pass from the package dependency list; "
                  "there is no second check for these lines yet."]
        L += [
            f"- **File counts.** Compared with the server's own count for each repository: {s['fm']['match']} of {s['n_scale']} match.",
            f"- **Check it yourself.** Per-repository reports, pipeline conclusions and aggregates are all in this repository (`reports/`, "
            f"`pipeline-status/`, `census/`); the method is in [{P}]({P}).",
            f"- **Refreshed monthly.** On the first day of each month the baseline is refreshed: a system is rescanned when its upstream HEAD "
            f"has moved, otherwise it keeps its previous measurement. [This baseline's run]({run_url}): {window}.", "",
            "## Scope and limits", ""]
        limits = [
            "**A curated selection, not a random sample.** The corpus is a tiered pick of well-known Java repositories and carries "
            "self-selection bias. The reference lines are not an industry survey or an industry benchmark.",
            f"**Whole-corpus only.** Each reference line covers all {k} systems together. No single type has {PUBLISH_N} or more systems yet, "
            "so there are no per-type reference lines.",
            "**Back-end Java only.** Frontend projects take part in the scale statistics only.",
        ]
        if s["drift"]:
            limits.append(
                f"**{count_word(len(s['drift']), True)} systems carr{'ies' if len(s['drift']) == 1 else 'y'} little Java at their current version** "
                f"({drift_names}), which limits how representative {'it is' if len(s['drift']) == 1 else 'they are'} for the reference lines.")
        limits += [
            f"**Lines are physical lines**, comments and blank lines included, not SLOC. The definition is in [{C}]({C}).",
            "**A single point in time.** The baseline is a cross-section that is refreshed with each rescan."]
        L += [f"{i}. {x}" for i, x in enumerate(limits, 1)] + [
            "",
            "## License and citation", "",
            "- License: [Apache License 2.0](LICENSE).",
            f"- Cite as: ASDM KE Index, baseline run #{meta['run_number']} (`{meta['run_id']}`), {meta['baseline_date']}.",
            "- Corpus: every system is an open-source project owned by its respective authors. This repository publishes counts and metric "
            "values only and contains no source code of the corpus.",
            "- Feedback: [Issues](https://github.com/asdm-ai/asdm-ke-index/issues).", ""]
    else:
        L += [
            "[参考线](#参考线) · [数据规模与覆盖](#数据规模与覆盖) · [怎么用](#怎么用) · [复核方式](#数据怎么来的怎么复核) · [适用范围](#适用范围)", "",
            "| 系统 | 代码行数 | 参考线 | 基线 |", "|---|---|---|---|",
            f"| **{s['n']} 个开源系统** | **{lines / 1e4:,.0f} 万行** | **{len(s['published'])} 条** | **{meta['baseline_date']}** |", "",
            "## 它解决什么问题", "",
            "AI 写代码已经很快，读懂一个维护了十年的系统却依然很慢。要让 AI 安全地接手旧系统的迭代，需要先回答三个问题："
            "这个系统的结构有多纠缠？一处改动会波及哪里？它的质量处在什么水平？", "",
            f"KE 用知识图谱和影响面分析回答前两个问题。KE Index 回答第三个：它让 {s['n']} 个知名开源 Java 系统跑过同一套引擎，"
            "把结果做成一把公开、可复核的尺子。你的系统接入之后，量出来的位置就有了参照。", "",
            "读者是负责核心系统现代化的架构团队、正在大规模引入 AI 编码工具的研发组织，以及需要向管理层说明系统健康度的技术负责人。", "",
            "## KE 能测什么", "",
            "| 能力 | 回答的问题 | 参考线 |", "|---|---|---|",
            f"| 读懂结构 | 模块之间的依赖有多纠缠 | {names(d, ['B1.backend', 'B2'], False)} |",
            f"| 看清质量 | 代码有多难改、测试有多少 | {names(d, ['B3', 'C2', 'C3', 'C4'], False)} |", "",
            f"当前发布的 {len(s['published'])} 条参考线全部针对后端 Java 代码。口径与原始数值见 [{M}]({M})。", "",
            "## 参考线", "",
            f"> 样本：{s['n']} 个系统中的 {k} 个（其余 {s['no_val']} 个为 {s['no_val_frontend']} 个前端工程和 "
            f"{s['no_val'] - s['no_val_frontend']} 个没有 Java 包结构的仓）。基线：{meta['baseline_date']}。"
            "复核方式见[数据怎么来的](#数据怎么来的怎么复核)。", "",
            "| 指标 | 衡量什么 | 方向 | P25 | 中位数（P50） | P75 |", "|---|---|---|---|---|---|",
        ] + ref_rows(d, False) + [
            "",
            "中位数把样本分成两半，P25 到 P75 覆盖中间一半的系统。\"越低越好\"的指标，你的值高于 P75，说明比四分之三的样本更严重。"
            "区间型指标不设优劣方向，落在 P25 到 P75 之间属于常见范围。", "",
            "## 数据规模与覆盖", "",
            "下表每个系统都由 KE 引擎实际扫描，没有任何数字取自第三方统计。对象与链接是 KE 为该系统构建的知识图谱中的节点与关系；"
            "文件数与行数取自所扫描提交上的源码树（行数为物理行，含注释与空行）。", "",
            f"{s['n']} 个系统按 [repos.yaml](repos.yaml) 的顺序列出。", "",
            "| # | 仓库 | 类型 | 对象 | 链接 | 文件数 | Java 文件 | 行数 | Java 行数 |", "|---|---|---|---|---|---|---|---|---|",
        ] + entry_rows(d, False) + [
            f"| | **合计（{s['n']} 个）** | | **{n(s['objects']['sum'])}** | **{n(s['links']['sum'])}** | **{n(s['fileCount']['sum'])}** | "
            f"**{n(s['javaFiles']['sum'])}** | **{n(s['lineCount']['sum'])}** | **{n(s['javaLines']['sum'])}** |", "",
        ] + [f"- **{TIER[x]['short_zh']}（{s['tier_counts'][x]}）**：{TIER[x]['shape_zh']}" for x in "ABCD"] + [
            "",
            f"**跨度。** 这些系统的代码规模从 {n(s['lineCount']['min'])} 行到 {n(s['lineCount']['max'])} 行（中位数 {n(s['lineCount']['median'])} 行），"
            f"图谱对象从 {n(s['objects']['min'])} 个到 {n(s['objects']['max'])} 个。", "",
            f"**现在的覆盖范围与目标。** {s['n']} 个系统的规模还不足以代表整个开源社区的状态。语料在逐步扩展，目标是达到具备统计学价值的样本比例。"
            "在此之前，参考线反映的是这批语料的状况。", "",
        ]
        if s["ratio_top"] and s["link_top_share"] >= 10:
            ratio, name, objs_, links_ = s["ratio_top"]
            L += [f"**有一处链接数尚未查明原因。**{name} 一个系统就占全部链接的约 {s['link_top_share']:.0f}%"
                  f"（对象 {n(objs_)} 个、链接 {n(links_)} 条，约每个对象 {ratio:.0f} 条，远高于其它系统）。原因尚未查明，见 [{C}]({C})。", ""]
        L += [
            f"源码版本、快照与逐仓明细见 [{C}]({C})。", "",
            "## 怎么用", "",
            "1. 在 [kengine.ai](https://kengine.ai) 接入你的系统仓库。",
            "2. 引擎构建知识图谱并计算指标。",
            "3. 把你的数值对照上面的参考线，看它处在什么位置。", "",
            "参考线随每次重扫更新，对照时请以本页标注的基线日期为准。", "",
            "## 数据怎么来的、怎么复核", "",
            f"- **同一版本的分析器。** {s['n']} 个系统全部由同一版本的分析器度量。",
            f"- {passed_label} 扫描、图谱构建、指标计算、一致性比对四个环节 {s['overall_pass']}/{s['n']} 通过，"
            f"失败 {len(s['failed'])} 个{missing_zh}。",
        ]
        if checked:
            L += [f"- **已复核的参考线。**{names(d, checked, False)}：分子或分母逐仓与服务端按条件另查一次的结果比对，{xc_zh}。"]
        if unchecked:
            L += [f"- **尚无独立复核的参考线。**{names(d, unchecked, False)}由包依赖清单一次算出，目前没有第二道核对。"]
        L += [
            f"- **文件数。** 逐仓与服务端的文件数比对，{s['fm']['match']}/{s['n_scale']} 一致。",
            f"- **可以自己核对。** 逐仓报告、管线结论和聚合数据都在本仓库（`reports/`、`pipeline-status/`、`census/`），"
            f"方法见 [{P}]({P})。",
            f"- **每月刷新。** 每月 1 日刷新基线：上游有新提交的系统重新扫描，其余保持上一次的测量结果。"
            f"[本次基线的运行记录]({run_url})：{window}。", "",
            "## 适用范围", ""]
        limits = [
            "**是精选样本，不是随机抽样。** 语料是知名 Java 仓库的分层选取，存在自选择偏差。参考线不是行业普查，也不是行业基准。",
            f"**只覆盖全库整体。** 每条参考线覆盖全部 {k} 个系统；目前没有任何一个类型达到 {PUBLISH_N} 个系统，所以没有分类型的参考线。",
            "**只覆盖后端 Java。** 前端工程只参与规模统计。",
        ]
        if s["drift"]:
            limits.append(f"**有 {len(s['drift'])} 个系统在当前版本上 Java 代码很少**（{drift_names}），对参考线的代表性有限。")
        limits += [
            f"**行数是物理行**，含注释与空行，不是 SLOC。口径见 [{C}]({C})。",
            "**单一时间点。** 基线是一个横截面，随每次刷新更新。"]
        L += [f"{i}. {x}" for i, x in enumerate(limits, 1)] + [
            "",
            "## 许可与引用", "",
            "- 许可证：[Apache License 2.0](LICENSE)。",
            f"- 引用格式：ASDM KE Index，基线 run #{meta['run_number']}（`{meta['run_id']}`），{meta['baseline_date']}。",
            "- 语料：全部系统都是开源项目，版权归各自作者。本仓库只发布计数与指标数值，不含语料的源代码。",
            "- 反馈：[Issues](https://github.com/asdm-ai/asdm-ke-index/issues)。", ""]
    return "\n".join(L)


# ------------------------------------------------------------------- docs/METRICS
def metrics_doc(d, meta, en):
    s, c = d["stats"], d["census"]
    other = "METRICS_zh-cn.md" if en else "METRICS.md"
    run_url = f"https://github.com/asdm-ai/asdm-ke-index/actions/runs/{meta['run_id']}"
    L = [
        "# Reference lines: definitions and raw numbers" if en else "# 参考线：口径与原始数值", "",
        f"English | [简体中文]({other})" if en else f"[English]({other}) | 简体中文", ""]
    if en:
        L += [f"This page documents the reference lines published on the [README](../README.md), and only those. "
              f"Baseline {meta['baseline_date']}, run #{meta['run_number']} (`{meta['run_id']}`).", "",
              "## Overview", "",
              "| Reference line | Definition | Direction | Systems (N) | P25 | P50 | P75 | P90 | Mean |",
              "|---|---|---|---|---|---|---|---|---|"]
    else:
        L += [f"本页只收录 [README](../README_zh-cn.md) 上发布的参考线。基线 {meta['baseline_date']}，run #{meta['run_number']}（`{meta['run_id']}`）。", "",
              "## 总览", "",
              "| 指标 | 定义 | 方向 | 系统数（N） | P25 | P50 | P75 | P90 | 均值 |",
              "|---|---|---|---|---|---|---|---|---|"]
    L += ref_rows(d, en, raw=True) + ["", "## How each line is computed" if en else "## 逐项口径", ""]
    for mid in s["published"]:
        m, x = c["metrics"][mid], s["xcheck"][mid]
        if en:
            L += [f"### {mname(mid, True)} (`{mid}`)", "",
                  f"- **Definition.** {PUBLISHED[mid]['def_en']}.",
                  f"- **Computation.** {PUBLISHED[mid]['how_en']}",
                  f"- **Direction.** {direction(d, mid, True)}. Systems with a value: {m['N']}; without: {m['missing']}."]
            L += ([f"- **Cross-check.** One of the two counts behind the line was compared, per repository, with a separate filtered "
                   f"count from the server: {x['match']} of {x['match'] + x['mismatch']} match."]
                  if x["checked"] else ["- **Cross-check.** None yet: the line is computed in one pass from the package dependency list."])
        else:
            L += [f"### {mname(mid, False)}（`{mid}`）", "",
                  f"- **定义。**{PUBLISHED[mid]['def_zh']}。",
                  f"- **计算。**{PUBLISHED[mid]['how_zh']}",
                  f"- **方向。**{direction(d, mid, False)}。有值的系统 {m['N']} 个，无值 {m['missing']} 个。"]
            L += ([f"- **复核。**分子或分母逐仓与服务端按条件另查一次的结果比对：{x['match']}/{x['match'] + x['mismatch']} 一致。"]
                  if x["checked"] else ["- **复核。**暂无：该指标由包依赖清单一次算出。"])
        L.append("")
    if en:
        L += ["## Rules", "",
              f"- **Publishing.** A reference line is published when at least {PUBLISH_N} systems carry a value.",
              "- **Percentiles.** Nearest-rank, computed over the systems that carry a value for the line.",
              "- **Scope.** All lines are computed over the whole corpus; per-type reference lines come once a type reaches the threshold.",
              f"- **Source.** `census/summary.json` in this repository; per-repository values in `reports/`. [Baseline scan run]({run_url}).", ""]
    else:
        L += ["## 规则", "",
              f"- **发布。**一条参考线在有值的系统不少于 {PUBLISH_N} 个时发布。",
              "- **分位。**最近秩取值，在有值的系统上计算。",
              "- **范围。**全部参考线按全库整体计算；某个类型系统数达到门槛后再出分类型参考线。",
              f"- **来源。**本仓库的 `census/summary.json`，逐仓数值在 `reports/`。[基线扫描记录]({run_url})。", ""]
    return "\n".join(L)


# -------------------------------------------------------------------- docs/CORPUS
def scale_section(d, en):
    s = d["stats"]
    L = ["## Repository scale (files / lines)" if en else "## 仓规模（文件数 / 行数）", ""]
    if en:
        L += ["Scale is collected during the scan (`scan-one.sh`, right after the clone and before the import: same working tree, same HEAD) "
              "by `scripts/repo-scale.py`. It is stored under `report.metrics.D3.scale` in each report and summarised per repo (`repos[]`) "
              "and across repos (`cohort.scale`) in `census/summary.json`. It is a size reference for the other metrics and is not scored.", "",
              "### Definitions", "", "| Field | Definition |", "|---|---|",
              "| Files `fileCount` | Tracked files, excluding directories the analyzer skips (`target` / `build` / `dist` / `node_modules`, …) "
              "and non-regular files such as symlinks. Same definition as the analyzer's `Repository.fileCount`; compared per repo during the "
              "scan (a mismatch only warns). |",
              "| Java files `javaFiles` | The `.java` files among them |",
              "| Lines `lineCount` | Physical lines of text files, comments and blank lines included: **not SLOC**. Binary files (NUL in the "
              "first 8000 bytes) are not counted. |",
              "| Java lines `javaLines` | Physical lines of `.java` files |", "",
              "### Totals across the corpus", "", "| Measure | Sum over all repos | Smallest repo | Largest repo |", "|---|---|---|---|"]
    else:
        L += ["仓规模在扫描的同时采集（`scan-one.sh` clone 之后、import 之前，同一工作树同一 HEAD），由 `scripts/repo-scale.py` 完成。"
              "它落在各 report 的 `report.metrics.D3.scale`，并在 `census/summary.json` 给出逐仓字段（`repos[]`）与跨仓分布（`cohort.scale`）。"
              "作为各指标的规模参照，不参与评分。", "",
              "### 口径", "", "| 字段 | 口径 |", "|---|---|",
              "| 文件数 `fileCount` | tracked 文件数，剔除分析器跳过目录（`target` / `build` / `dist` / `node_modules` 等）与符号链接等"
              "非普通文件；与分析器 `Repository.fileCount` 同口径，扫描时逐仓对照（不一致只告警不置红） |",
              "| Java 文件 `javaFiles` | 其中 `.java` 文件数 |",
              "| 总行数 `lineCount` | 文本文件的物理行数，含注释与空行，**不是 SLOC**；二进制文件（首 8000 字节含 NUL）不计 |",
              "| Java 行数 `javaLines` | 其中 `.java` 文件的物理行数 |", "",
              "### 全库合计", "", "| 指标 | 全部仓合计 | 最小仓 | 最大仓 |", "|---|---|---|---|"]
    for key, a, b in (("fileCount", "Files", "文件数"), ("javaFiles", "Java files", "Java 文件数"),
                      ("lineCount", "Lines", "总行数"), ("javaLines", "Java lines", "Java 行数")):
        v = s[key]
        L.append(f"| {a if en else b} | {n(v['sum'])} | {n(v['min'])} | {n(v['max'])} |")
    if en:
        L += ["", f"Java accounts for {s['java_share_lines']:.1f}% of all counted lines and {s['java_share_files']:.1f}% of counted files. "
              f"The {s['n']} repos hold {n(s['tracked'])} tracked files in git ({n(s['text'])} counted as text, "
              f"{n(s['binary'])} detected as binary and skipped).", "",
              "### Distribution across repos", "",
              "| Measure | N | Missing | Min | P25 | P50 | P75 | P90 | Max | Sum | Mean |",
              "|---|---|---|---|---|---|---|---|---|---|---|"]
    else:
        L += ["", f"Java 占全部计入行数的 {s['java_share_lines']:.1f}%、计入文件数的 {s['java_share_files']:.1f}%。"
              f"{s['n']} 个仓在 git 中共有 {n(s['tracked'])} 个 tracked 文件（计入文本 {n(s['text'])} 个，判定为二进制并跳过 "
              f"{n(s['binary'])} 个）。", "",
              "### 跨仓分布", "",
              "| 指标 | N | 缺失 | Min | P25 | P50 | P75 | P90 | Max | 合计 | 均值 |",
              "|---|---|---|---|---|---|---|---|---|---|---|"]
    for key, a, b in (("fileCount", "Files", "文件数"), ("javaFiles", "Java files", "Java 文件数"),
                      ("lineCount", "Lines", "总行数"), ("javaLines", "Java lines", "Java 行数")):
        m, q = s["d3_scale"][key], s["d3_scale"][key]["percentiles"]
        L.append(f"| {a if en else b} `{key}` | {m['N']} | {m['missing']} | {n(m['min'])} | {n(q['p25'])} | {n(q['p50'])} | "
                 f"{n(q['p75'])} | {n(q['p90'])} | {n(m['max'])} | {n(s[key]['sum'])} | {n(round(m['mean']))} |")
    if en:
        L += ["", "Percentiles are nearest-rank values from `census/summary.json`.", "",
              "### By tier", "", "| Tier | Repos | Median files | Median lines | Median Java lines | Sum of Java lines |", "|---|---|---|---|---|---|"]
    else:
        L += ["", "分位数为 `census/summary.json` 中的最近秩取值。", "",
              "### 分层对照", "", "| 分层 | 仓数 | 文件数中位 | 行数中位 | Java 行数中位 | Java 行数合计 |", "|---|---|---|---|---|---|"]
    for t in "ABCD":
        v = s["tier_scale"].get(t)
        if v:
            L.append(f"| {TIER[t]['short_en' if en else 'short_zh']} | {v['n']} | {n(v['fileCount'])} | {n(v['lineCount'])} | "
                     f"{n(v['javaLines'])} | {n(v['sumJavaLines'])} |")
    L += ["", "### Largest repositories" if en else "### 规模最大的仓", ""]
    for key, a, b in (("javaLines", "By Java lines:", "按 Java 行数："), ("lineCount", "By total lines:", "按总行数：")):
        L += [a if en else b, "",
              "| Repository | Java lines | Lines | Java files | Files |" if en else "| 仓库 | Java 行数 | 行数 | Java 文件 | 文件数 |",
              "|---|---|---|---|---|"]
        for r in s["top_java" if key == "javaLines" else "top_lines"]:
            scl = scale_of(r["report"])
            L.append(f"| [{r['name']}](https://github.com/{r['name']}) | {n(scl['javaLines'])} | {n(scl['lineCount'])} | "
                     f"{n(scl['javaFiles'])} | {n(scl['fileCount'])} |")
        L.append("")
    L += ["### Lines by language" if en else "### 分语言行数", "",
          "| Language (by extension) | Lines | Share | Files |" if en else "| 语言（按扩展名） | 行数 | 占比 | 文件数 |", "|---|---|---|---|"]
    total = s["lineCount"]["sum"]
    for i, (k, v) in enumerate(s["lang_lines"][:10]):
        L.append(f"| `{k}` | {n(v)} | {v / total * 100:.1f}% | {n(s['lang_files'].get(k, 0))} |")
    rest = s["lang_lines"][10:]
    if rest:
        rl, rf = sum(v for _, v in rest), sum(s["lang_files"].get(k, 0) for k, _ in rest)
        L.append(f"| other ({len(rest)} more) | {n(rl)} | {rl / total * 100:.1f}% | {n(rf)} |" if en
                 else f"| 其余（{len(rest)} 种） | {n(rl)} | {rl / total * 100:.1f}% | {n(rf)} |")
    if en:
        L += ["", "- **Java lines are the primary size reference.** Total lines are inflated by non-code files"
              + (f": in {s['other_top'][0]} the `other` bucket (unrecognised extensions) alone contributes "
                 f"{n(s['other_top'][1])} lines" if s["other_top"] else "") + ".",
              "- Per-language detail (`linesByLanguage` / `filesByLanguage`) is part of each report.", ""]
    else:
        L += ["", "- **Java 行数是首要的规模参照。** 总行数会被非代码文件抬高"
              + (f"：{s['other_top'][0]} 的 `other` 桶（未识别扩展名）单项就有 {n(s['other_top'][1])} 行" if s["other_top"] else "") + "。",
              "- 分语言明细（`linesByLanguage` / `filesByLanguage`）见各 report。", ""]
    return L


def corpus_doc(d, meta, en):
    s = d["stats"]
    other = "CORPUS_zh-cn.md" if en else "CORPUS.md"
    home = "../README.md" if en else "../README_zh-cn.md"
    if en:
        L = ["# Corpus: the repositories in detail", "", f"English | [简体中文]({other})", "",
             f"Every repository behind the [reference lines]({home}), with its snapshot, size and pipeline result. "
             f"Baseline {meta['baseline_date']}, run #{meta['run_number']} (`{meta['run_id']}`).", "",
             "## Tiers", "", "| Tier | Repos | Shape |", "|---|---|---|"]
        for t in "ABCD":
            L.append(f"| {t} · {TIER[t]['short_en']} | {s['tier_counts'][t]} | {TIER[t]['shape_en']} |")
        L += ["", "> The full list is in [repos.yaml](../repos.yaml). Snapshot IDs are truncated to 8 characters "
              "(full values in the `repos` block of `census/summary.json`).", "",
              "## All repositories", "",
              "| # | owner/repo | Tier | Snapshot | Commit | Report | Objects | Links | Files | Java files | Lines | Java lines | Pipeline |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        L += full_rows(d)
        L += ["", "## Corpus notes", "",
              f"> ⚠️ **Tier drift**: `.java` is not the largest file group in {len(s['drift'])} tier-A repos ("
              + "; ".join(f"{x['name']}: {n(x['java'])} `.java` files against {n(x['n'])} `.{x['lang']}` files" for x in s["drift"])
              + "). They still count toward tier A but carry little Java."]
        L += [""]
        if s["ratio_top"]:
            ratio, name, objs, links = s["ratio_top"]
            L += [f"- **A link count awaiting attribution**: {name} has {n(links)} links for {n(objs)} objects "
                  f"(about {ratio:.0f} links per object, far above the other repos)."]
        L += [""]
    else:
        L = ["# 语料：逐仓明细", "", f"[English]({other}) | 简体中文", "",
             f"[参考线]({home})背后的全部仓库，含快照、规模与管线结论。基线 {meta['baseline_date']}，run #{meta['run_number']}"
             f"（`{meta['run_id']}`）。", "",
             "## 分层", "", "| 分层 | 仓数 | 形态 |", "|---|---|---|"]
        for t in "ABCD":
            L.append(f"| {t} · {TIER[t]['short_zh']} | {s['tier_counts'][t]} | {TIER[t]['shape_zh']} |")
        L += ["", "> 全量清单见 [repos.yaml](../repos.yaml)。快照 ID 截取前 8 位（完整值见 `census/summary.json` 的 repos 区）。", "",
              "## 全部仓库", "",
              "| # | owner/repo | 分层 | 快照 | 源码版本 | 报告 | 对象数 | 链接数 | 文件数 | Java 文件 | 行数 | Java 行数 | 管线 |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        L += full_rows(d)
        L += ["", "## 语料说明", "",
              f"> ⚠️ **分层漂移**：{len(s['drift'])} 个 A 层仓在当前 HEAD 上 `.java` 已不是最大的文件类别（"
              + "；".join(f"{x['name']}：{n(x['java'])} 个 `.java` 对 {n(x['n'])} 个 `.{x['lang']}`" for x in s["drift"])
              + "）。这些仓仍计入 A 层，但 Java 代码很少。"]
        L += [""]
        if s["ratio_top"]:
            ratio, name, objs, links = s["ratio_top"]
            L += [f"- **一处待归因的链接数**：{name} 的对象 {n(objs)} 个、链接 {n(links)} 条（约每个对象 {ratio:.0f} 条，远高于其它仓）。"]
        L += [""]
    L += scale_section(d, en)
    return "\n".join(L)


# ------------------------------------------------------------------ docs/PIPELINE
def pipeline_doc(d, meta, en):
    s = d["stats"]
    v = s["validation"]
    other = "PIPELINE_zh-cn.md" if en else "PIPELINE.md"
    home = "../README.md" if en else "../README_zh-cn.md"
    cli = "`, `".join(s["cli"])
    run_url = f"https://github.com/asdm-ai/asdm-ke-index/actions/runs/{meta['run_id']}"
    if en:
        L = ["# How the data is produced", "", f"English | [简体中文]({other})", "",
             f"How the {s['n']} systems behind the [reference lines]({home}) are scanned, measured and checked. "
             f"Current baseline: run #{meta['run_number']} (`{meta['run_id']}'), {meta['started_at']} to {meta['completed_at']} UTC "
             f"({meta['duration']}).", "",
             "## Directory layout", "", "| Path | Content |", "|---|---|",
             "| `repos.yaml` | Scan list (owner / repo / branch / skip / notes; the first character of `notes` is the tier letter) |",
             "| `.github/workflows/scan.yml` | Batch scan workflow (matrix, one repo at a time, `max-parallel: 1`) |",
             f"| `scripts/install-cli.sh` | Downloads the KE CLI (manifest latest + sha256 check + version assertion, currently `{cli}`) |",
             "| `scripts/preflight-skip.sh` | Zero-drift short circuit (skips the whole repo when the remote HEAD and the report freshness both match) |",
             "| `scripts/scan-one.sh` | Single-repo scan: clone, then `ke import start` (default `--defer-projection`) |",
             "| `scripts/repo-scale.py` | Repository scale collection (file count / lines, by language), run right after the clone |",
             "| `scripts/compute-metrics.py` | Per-repository metrics to `reports/{owner}/{repo}.json` (numerators, denominators, provenance) |",
             "| `scripts/graph-metrics.py` | Graph-form recomputation of the chain metrics and the dual-path equivalence check (`--compare`, exit 2 on MISMATCH) |",
             "| `scripts/pipeline-status.sh` | Writes the four step conclusions to `pipeline-status/{owner}/{repo}.json` |",
             "| `scripts/census.py` | Aggregated percentiles, per-repository pipeline validation, matrix reconciliation and scale distribution to `census/summary.json` |",
             "| `scripts/render-docs.py` | Renders `README.md` and `docs/` from the artifacts; refuses to write unless every system passed |",
             "| `scripts/validate-docs.py` | Checks the rendered pages against the artifacts (numbers, links, structure, prohibited content) |",
             "| `scripts/push-with-retry.sh` | Bot commit/push retry (rebase only on non-FF, backoff on transient 5xx) |",
             "| `scripts/scale-backfill.py`, `.github/workflows/scale-backfill.yml` | Backfills scale for legacy reports at the pinned commit (idempotent, manual dispatch) |",
             "| `reports/{owner}/{repo}.json` | Per-repository report |",
             "| `pipeline-status/{owner}/{repo}.json` | Per-repository pipeline conclusion |",
             "| `census/summary.json` | Aggregate output: sample list, per-metric percentiles, validation, cohorts, scale distribution |", "",
             "## Scan pipeline", "",
             "One job per repo. The chain runs serially inside the job and any failing step fails that repo's job (`fail-fast: false` + "
             "`max-parallel: 1`: one repo's failure neither cancels the others nor blocks the trailing census).", "",
             "```",
             "preflight (zero-drift short circuit)",
             "  1. scan         clone, then import --defer-projection (MySQL only)",
             "  2. projection   ke project <snapshotId> (Neo4j projection)",
             "  3. metrics      compute-metrics.py (direct MySQL queries)",
             "  4. consistency   graph-metrics.py --compare (chain metrics only: graph-form recomputation + dual-path equivalence)",
             "  5. annotate     pipeline-status written + report committed",
             "census           aggregates the artifacts, rolls up every repo's step conclusions, reconciles with the scan matrix",
             "```", "",
             "- **Triggers**: a push touching `repos.yaml`, a manual dispatch from the Actions tab (optional `scan_force`), or the monthly "
             "schedule `0 2 1 * *`. A run-level `concurrency` group keeps the three trigger surfaces mutually exclusive.",
             "- **Default-track dedup**: when both the repo HEAD and the CLI version are unchanged, preflight skips the whole job.",
             "- **Concurrency guard**: `max-parallel: 1` keeps repos serial, so projection has an exclusive window.",
            "- **Documentation**: after the census is committed, `render-docs.py` rebuilds `README.md` and `docs/`, `validate-docs.py` checks them "
            "and both are committed. Nothing is written unless every system passed the pipeline.", "",
             "## What is checked, and what is not", "",
             f"- **Pipeline steps.** All four steps completed for {s['overall_pass']} of {s['n']} repositories; failed: {len(s['failed'])}.",
             "- **Chain metrics.** The consistency step (step 4) covers the chain metrics only. It is not evidence for the reference lines "
             "published on the README; their cross-checks are listed in [docs/METRICS.md](METRICS.md).",
             f"- **File counts.** The scale collector's file count matches the server's `Repository.fileCount` for {s['fm']['match']} of "
             f"{s['n_scale']} repositories (mismatch {s['fm']['mismatch']}, unknown {s['fm']['unknown']}).",
             f"- **Reconciliation.** The `objectCount` on the last line of each scan step matches the platform's snapshot list, and "
             "snapshotId / objectCount / sourceHead agree across the report and pipeline-status of each repo.", "",
             "## Census gating", "", "| Item | Value |", "|---|---|",
             f"| Samples included | **{s['samples']}** |",
             f"| Publish threshold (statistical sufficiency) | total N ≥ {s['gate']['publishThreshold']} gives status `{s['census_status']}` |",
             f"| Privacy guard (k-anonymity) | slices with N < {s['gate']['privacyFloor']} get no percentiles |",
             f"| validation | {v['steps']['scan']['ok']}/{v['expectedRepos']} four steps ok; consistency pass {v['consistencyResult']['pass']} / "
             f"mismatch {v['consistencyResult']['mismatch']}; reconciled with the scan matrix, missing {len(v['missingRepos'])} |", "",
             "> The threshold applies to the total sample. Which individual lines are published on the README is decided by the per-line rule "
             "in [docs/METRICS.md](METRICS.md), which this documentation enforces at generation time.", ""]
        title_repro, title_rescan = "## Reproducing", "### Rescan track (metric corrections after an analyzer upgrade)"
    else:
        L = ["# 数据怎么来的", "", f"[English]({other}) | 简体中文", "",
             f"[参考线]({home})背后的 {s['n']} 个系统是如何被扫描、度量和复核的。当前基线：run #{meta['run_number']}"
             f"（`{meta['run_id']}`），{meta['started_at']} 至 {meta['completed_at']} UTC（{meta['duration']}）。", "",
             "## 目录结构", "", "| 路径 | 内容 |", "|---|---|",
             "| `repos.yaml` | 扫描清单（owner/repo/branch/skip/notes，notes 首字符为分层字母） |",
             "| `.github/workflows/scan.yml` | 批量扫描 workflow（matrix，按仓穿行，`max-parallel: 1`） |",
             f"| `scripts/install-cli.sh` | 下载 KE CLI（manifest latest + sha256 对账 + 版本断言，当前锚 `{cli}`） |",
             "| `scripts/preflight-skip.sh` | 零漂移短路（远端 HEAD 与 report 新鲜度命中即整仓跳过） |",
             "| `scripts/scan-one.sh` | 单仓扫描：clone 后 `ke import start`（默认 `--defer-projection`） |",
             "| `scripts/repo-scale.py` | 仓规模采集（文件数 / 行数，分语言），clone 之后立即执行 |",
             "| `scripts/compute-metrics.py` | 单仓指标计算，产出 `reports/{owner}/{repo}.json`（分子分母与溯源信息，可复算） |",
             "| `scripts/graph-metrics.py` | 链路类指标的图形态重算与双路径等价比对（`--compare`，MISMATCH exit 2） |",
             "| `scripts/pipeline-status.sh` | 四个子步的结论落盘到 `pipeline-status/{owner}/{repo}.json` |",
             "| `scripts/census.py` | 聚合分位、逐仓管线校验、矩阵对账与规模分布，产出 `census/summary.json` |",
             "| `scripts/render-docs.py` | 由产物渲染 `README.md` 与 `docs/`；不是全部仓通过就拒绝写出 |",
             "| `scripts/validate-docs.py` | 把渲染出的页面与产物逐项核对（数字、链接、结构、不应出现的内容） |",
             "| `scripts/push-with-retry.sh` | bot 提交推送重试（仅在 non-FF 时 rebase，瞬时 5xx 退避重试） |",
             "| `scripts/scale-backfill.py`、`.github/workflows/scale-backfill.yml` | 存量 report 按定锚提交补采仓规模（幂等，手动 dispatch） |",
             "| `reports/{owner}/{repo}.json` | 单仓报告 |",
             "| `pipeline-status/{owner}/{repo}.json` | 单仓管线结论 |",
             "| `census/summary.json` | 聚合产物：样本清单、各指标分位、validation、cohort、规模分布 |", "",
             "## 扫描管线", "",
             "每仓一个 job，job 内串行执行完整链路；任一子步不通过即该仓任务失败（`fail-fast: false` + `max-parallel: 1`："
             "单仓失败不级联，也不阻断尾部 census）。", "",
             "```",
             "preflight（零漂移短路）",
             "  1. scan         clone 后 import --defer-projection（仅 MySQL 落库）",
             "  2. projection   ke project <snapshotId>（Neo4j 投影）",
             "  3. metrics      compute-metrics.py（MySQL 直查）",
             "  4. consistency   graph-metrics.py --compare（仅链路类指标：图形态重算 + 双路径等价比对）",
             "  5. annotate     pipeline-status 落盘 + 报告入库",
             "census           聚合成功产物，汇总全部仓子步结论，并与扫描矩阵对账",
             "```", "",
             "- **触发**：push 修改 `repos.yaml`、Actions 页手动触发（可选 `scan_force`）、月度 schedule `0 2 1 * *`。"
             "run 级 `concurrency` 让三触发面互斥。",
             "- **默认轨去重**：仓 HEAD 与 CLI 版本均未变时，preflight 直接跳过整个 job。",
             "- **并发护栏**：`max-parallel: 1` 单仓串行，投影天然独占窗口。",
            "- **文档**：census 提交后，`render-docs.py` 重建 `README.md` 与 `docs/`，`validate-docs.py` 核对后一并提交。"
            "不是全部仓通过管线就不写。", "",
             "## 核对了什么、没核对什么", "",
             f"- **管线子步。**四个子步 {s['overall_pass']}/{s['n']} 全部完成，失败 {len(s['failed'])} 个。",
             "- **链路类指标。**第 4 步只覆盖链路类指标，不能作为 README 上已发布参考线的证据；后者的复核情况见 "
             "[docs/METRICS_zh-cn.md](METRICS_zh-cn.md)。",
             f"- **文件数。**规模采集的文件数与服务端 `Repository.fileCount` 在 {s['fm']['match']}/{s['n_scale']} 个仓上一致"
             f"（不一致 {s['fm']['mismatch']}，未知 {s['fm']['unknown']}）。",
             "- **对账。**每个扫描步骤末行的 `objectCount` 与平台快照列表一致，各仓 report 与 pipeline-status 的 "
             "snapshotId / objectCount / sourceHead 三者一致。", "",
             "## census 守门", "", "| 项 | 值 |", "|---|---|",
             f"| 已收录样本 | **{s['samples']}** |",
             f"| 发布门槛（统计充分性） | 总样本 N ≥ {s['gate']['publishThreshold']} 即状态 `{s['census_status']}` |",
             f"| 隐私护栏（k-匿名单指标级） | 切片 N < {s['gate']['privacyFloor']} 不出分位 |",
             f"| validation | 四子步 ok {v['steps']['scan']['ok']}/{v['expectedRepos']}；consistency pass "
             f"{v['consistencyResult']['pass']} / mismatch {v['consistencyResult']['mismatch']}；与扫描矩阵对账，缺失 "
             f"{len(v['missingRepos'])} |", "",
             "> 该门槛作用在总样本上。具体哪些参考线在 README 上发布，由 [docs/METRICS_zh-cn.md](METRICS_zh-cn.md) 的逐条规则决定，"
             "并在生成本文档时强制检查。", ""]
        title_repro, title_rescan = "## 复现说明", "### 重扫轨说明（分析器版本升级后的口径修正重扫）"
    # Reproducing and rescan track: identical commands in both languages, prose per language
    cmds = ["", "```bash", "# 1. Install the KE CLI (manifest latest + sha256 check + version assertion)" if en
            else "# 1. 安装 KE CLI（manifest latest + sha256 对账 + 版本断言）",
            "KE_API_KEY=<member key> bash scripts/install-cli.sh /tmp/ke-cli", "",
            "# 2. Scan one repo (clone --depth 1, then ke import start)" if en
            else "# 2. 单仓扫描（clone --depth 1 后 ke import start 三段上传直连）",
            "OWNER=macrozheng REPO=mall CLI_DIR=/tmp/ke-cli \\",
            "KE_API_KEY=<member key> KE_SERVER_URL=https://console.kengine.ai \\",
            "bash scripts/scan-one.sh",
            ("# The last line is the import summary JSON (ok / status / snapshotId / objectCount); exit 1 on failure" if en
             else "# 步骤末行为导入 summary JSON（ok / status / snapshotId / objectCount），失败 exit 1"), "```"]
    force = ["```bash", "SCAN_FORCE=true OWNER=dromara REPO=RuoYi-Vue-Plus CLI_DIR=/tmp/ke-cli \\",
             "KE_API_KEY=<member key> KE_SERVER_URL=https://console.kengine.ai \\", "bash scripts/scan-one.sh", "```"]
    if en:
        L += [title_repro] + cmds + [
            "- Reconciliation: the `objectCount` on the last line of the Action step must match the platform's snapshot list; "
            "snapshotId / objectCount / sourceHead must agree across the repo report and pipeline-status.", "",
            title_rescan, "",
            "When the repo HEAD is unchanged, `ke import start` hits the already-complete snapshot and is **dedup skipped**: the right "
            "behaviour for monthly rescans, but it swallows the metric corrections an analyzer upgrade brings. Rescans after an analyzer "
            "upgrade must therefore use the force track (tick `scan_force` when dispatching from the Actions tab, or set `SCAN_FORCE=true` locally):", ""
        ] + force + [
            "- Telling them apart: the force track's summary has `status == \"completed\"` (rebuilt); the default track with the same HEAD "
            "has `\"skipped\"` (values unchanged).",
            "- Boundary: the force rescan commit is the natural boundary between the old and new metric definitions (traceable in git history).", ""]
    else:
        L += [title_repro] + cmds + [
            "- 对账：Action 步骤末行 `objectCount` 与平台快照列表逐位对照；仓级 report 与 pipeline-status 的 "
            "snapshotId / objectCount / sourceHead 三者一致。", "",
            title_rescan, "",
            "仓 HEAD 不变时，`ke import start` 撞已 complete 的快照会 **dedup skipped**（静默跳过）。这是月度重扫的正确去重行为，"
            "但会吞掉分析器升级带来的口径修正。因此**分析器版本升级后的重扫必须走 force 轨**（Actions 页手动触发时勾选 "
            "`scan_force`，或本地 `SCAN_FORCE=true`）：", ""
        ] + force + [
            "- 判别：force 轨 summary `status == \"completed\"`（重建）；默认轨同 HEAD 为 `\"skipped\"`（数值不变）。",
            "- 口径分界：force 重扫 commit 即口径前后的自然分界（git 历史可追溯）。", ""]
    L += [f"[Baseline scan run]({run_url})" if en else f"[基线扫描记录]({run_url})", ""]
    return "\n".join(L)


# ------------------------------------------------------------------------- main
def run_meta(run_id, run_number, started_at, completed_at=None):
    """Meta built from a workflow run.

    completed_at should be the end of the last scan job (the workflow reads it from the Actions API);
    when omitted it is now, which is right only when the docs are the immediate last step of the run.
    """
    from datetime import datetime, timezone
    st = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
    end = datetime.fromisoformat(completed_at.replace("Z", "+00:00")) if completed_at else datetime.now(timezone.utc)
    h, r = divmod(int((end - st).total_seconds()), 3600)
    m, sec = divmod(r, 60)
    return {"run_id": str(run_id), "run_number": int(run_number), "started_at": st.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "completed_at": end.strftime("%Y-%m-%dT%H:%M:%SZ"), "duration": f"{h}h {m:02d}m {sec:02d}s",
            "baseline_date": st.strftime("%Y-%m-%d")}


def main():
    ap = argparse.ArgumentParser(description="Render README.md and docs/ from the repository's artifacts.")
    ap.add_argument("--repo", default=".", help="repository checkout (default: the current directory)")
    ap.add_argument("--meta", help="JSON with run_id, run_number, started_at, completed_at, duration, baseline_date")
    ap.add_argument("--run-id", help="build the meta from a workflow run instead (needs --run-number and --started-at)")
    ap.add_argument("--run-number")
    ap.add_argument("--started-at", help="run start, ISO 8601 (the workflow's github.run_started_at)")
    ap.add_argument("--completed-at", help="end of the last scan job, ISO 8601 (default: now)")
    ap.add_argument("--out", help="output directory (default: write into --repo)")
    ap.add_argument("--allow-failed", action="store_true",
                    help="render even when systems failed the pipeline (for diagnosis only; never used when publishing)")
    args = ap.parse_args()
    if args.run_id:
        if not (args.run_number and args.started_at):
            ap.error("--run-id needs --run-number and --started-at")
        meta = run_meta(args.run_id, args.run_number, args.started_at, args.completed_at)
    elif args.meta:
        with open(args.meta, encoding="utf-8") as f:
            meta = json.load(f)
    else:
        ap.error("give --meta or --run-id")
    # the same six keys in the same order, whichever way the meta arrived
    meta = {k: meta[k] for k in ("run_id", "run_number", "started_at", "completed_at", "duration", "baseline_date")}
    d = load(args.repo)
    compute(d)
    # publish gate: a page is only written from a complete, clean run. Without this the entry page would go out
    # stating that systems failed, or silently built on a stale report of a repo that was not rescanned.
    s = d["stats"]
    if not args.allow_failed and (s["failed"] or not (s["validation"] or {}).get("ok")):
        raise SystemExit(f"not publishing: failed systems {s['failed']}, matrix reconciled = "
                         f"{(s['validation'] or {}).get('ok')}; rerun them first, or pass --allow-failed to inspect")
    assert meta["started_at"][:10] == meta["baseline_date"], "baseline_date must be the start date"
    out = args.out or args.repo
    docs = {
        "README.md": readme(d, meta, True), "README_zh-cn.md": readme(d, meta, False),
        "docs/METRICS.md": metrics_doc(d, meta, True), "docs/METRICS_zh-cn.md": metrics_doc(d, meta, False),
        "docs/CORPUS.md": corpus_doc(d, meta, True), "docs/CORPUS_zh-cn.md": corpus_doc(d, meta, False),
        "docs/PIPELINE.md": pipeline_doc(d, meta, True), "docs/PIPELINE_zh-cn.md": pipeline_doc(d, meta, False),
        # which run produced the baseline; re-rendering with --meta docs/baseline.json reproduces the pages byte for byte
        "docs/baseline.json": json.dumps(meta, ensure_ascii=False, indent=1) + "\n",
    }
    os.makedirs(os.path.join(out, "docs"), exist_ok=True)
    for name, text in docs.items():
        with open(os.path.join(out, name), "w", encoding="utf-8") as f:
            f.write(text)
        print(f"wrote {name} ({len(text.splitlines())} lines)")
    print("SUMMARY", json.dumps({
        "baseline": meta, "repos": s["n"], "overall_pass": s["overall_pass"], "failed": s["failed"], "cli": s["cli"],
        "published": s["published"], "N": s["N"], "no_val": [s["no_val"], s["no_val_frontend"]],
        "xcheck": s["xcheck"], "scale": {k: s[k]["sum"] for k in ("fileCount", "javaFiles", "lineCount", "javaLines")},
        "graph": {k: s[k]["sum"] for k in ("objects", "links")},
        "fm": s["fm"], "drift": [x["name"] for x in s["drift"]], "other_top": s["other_top"], "link_top_share": s["link_top_share"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
