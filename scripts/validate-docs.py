#!/usr/bin/env python3
"""Validate the rendered documentation of asdm-ke-index against the repository's artifacts.

Checked:
  - every table has a constant column count; code fences are balanced
  - every relative link and anchor resolves
  - every number in the entry page and the corpus table equals census/summary.json
    (and pipeline-status for the scanned commit)
  - the metrics documents carry the published percentiles and sample sizes
  - the two language versions have the same structure (headings, table rows, badge count, links)
  - docs/BUILD_LOG: one row per system with a build record, mode equal to the report's build mode
    (the file is required when at least one system has a build record, and must be absent otherwise)
  - content that must not appear in the public documentation

    python3 scripts/validate-docs.py [OUT]         # OUT defaults to the current directory

When OUT is not the repository checkout itself, links into `reports/`, `repos.yaml` etc. are
resolved against the environment variable DOCS_REPO (default: OUT).

Exit code 0 when there are no errors, 1 otherwise. Standard library only.
"""
import json
import os
import re
import sys

PUBLISH_N = 30
FILES = ["README.md", "README_zh-cn.md", "docs/METRICS.md", "docs/METRICS_zh-cn.md",
         "docs/CORPUS.md", "docs/CORPUS_zh-cn.md", "docs/PIPELINE.md", "docs/PIPELINE_zh-cn.md"]
BUILD_FILES = ["docs/BUILD_LOG.md", "docs/BUILD_LOG_zh-cn.md"]
PAIRS = [("README.md", "README_zh-cn.md"), ("docs/METRICS.md", "docs/METRICS_zh-cn.md"),
         ("docs/CORPUS.md", "docs/CORPUS_zh-cn.md"), ("docs/PIPELINE.md", "docs/PIPELINE_zh-cn.md"),
         ("docs/BUILD_LOG.md", "docs/BUILD_LOG_zh-cn.md")]
SCALE_KEYS = ("objectCount", "linkCount", "fileCount", "javaFiles", "lineCount", "javaLines")

# Content that must not appear in prose. Each rule must itself be safe to publish: no partner
# names, no internal targets or prices, not even as a pattern.
FORBIDDEN = [
    # reference lines below the publish threshold are not documented
    r"\bA[1-4]\b", r"\bB4\b", r"\bC1\b", r"B1\.frontend", r"\bD[124]\b",
    # commercial terms and roadmap commitments
    r"计价|定价|客单|续费|数字员工|ROI", r"pricing|revenue target|roadmap|路线图",
    r"扩语言|Python / Go", r"\bQ[1-4]\b",
    # unqualified multiplier claims
    r"10 ?倍|10x",
    # operations narrative of a single run is not reference material
    r"full data wipe|数据全量清空",
]
# `metrics.D3.scale` is the storage path of the scale profile and legitimately appears in the corpus document
ALLOWED_IN = {"docs/CORPUS": (r"\bD[124]\b",)}

# C3 row labels of the two denominators (must match C3_CALIBERS in render-docs.py)
C3_ROWS = {
    "allMethods": {"en": "Test-method share (all methods)", "zh": "测试方法占比（全部方法）"},
    "sourceAnchored": {"en": "Test-method share (methods with a source body)", "zh": "测试方法占比（有源码方法体）"},
}


def slug(h):
    h = h.strip().lower()
    return re.sub(r"[^\w\- ]", "", h, flags=re.U).replace(" ", "-")


def anchors(t):
    return {slug(x) for x in re.findall(r"^#{1,6}\s+(.*)$", t, flags=re.M)}


def fmt(x):
    return f"{x:,}"


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "."
    # the repository checkout (census/, reports/, pipeline-status/): DOCS_REPO, else the output directory,
    # else the working directory (the output directory holds documents only when --out is used)
    repo = os.environ.get("DOCS_REPO") or (out if os.path.exists(os.path.join(out, "census", "summary.json")) else ".")
    census = json.load(open(os.path.join(repo, "census/summary.json"), encoding="utf-8"))
    errs, texts = [], {}
    R = {(r["owner"], r["repo"]): r for r in census["repos"]}
    n_repos = len(R)
    # the build log exists exactly when at least one system carries a build record
    n_build = sum(1 for r in R.values() if r.get("buildRecorded"))
    files = FILES + (BUILD_FILES if n_build else [])
    pairs = PAIRS if n_build else PAIRS[:-1]
    for f in (BUILD_FILES if not n_build else []):
        if os.path.exists(os.path.join(out, f)):
            errs.append((f, "build log present but no system has a build record"))

    def p4(x):
        return f"{x:.4f}".rstrip("0").rstrip(".")

    def pct(x):
        v = x * 100
        return f"{v:.2f}%" if v < 1 else f"{v:.1f}%"

    def close(a, b):
        return a is not None and b is not None and abs(a - b) <= 1e-6

    # C3 two denominators: the report contract, the census roll-up and the rendered rows must agree
    for (owner, repo_), r in sorted(R.items()):
        rp_path = os.path.join(repo, "reports", owner, repo_ + ".json")
        if not os.path.exists(rp_path):
            continue
        c3 = ((json.load(open(rp_path, encoding="utf-8")).get("metrics") or {}).get("C3"))
        cal = (c3 or {}).get("calibers")
        if not isinstance(cal, dict):
            continue
        a, b, mc = cal.get("allMethods") or {}, cal.get("sourceAnchored") or {}, c3.get("methodComposition") or {}
        name = owner + "/" + repo_
        if not (close(a.get("value"), c3.get("value")) and a.get("numerator") == c3.get("numerator")
                and a.get("denominator") == c3.get("denominator")):
            errs.append(("reports", "C3 allMethods caliber differs from the published value", name))
        if a.get("denominator") and not close(a.get("value"), a["numerator"] / a["denominator"]):
            errs.append(("reports", "C3 allMethods value is not numerator / denominator", name))
        if b.get("denominator") is not None and a.get("denominator") is not None and not (
                b["denominator"] <= a["denominator"] and (b.get("numerator") or 0) <= (a.get("numerator") or 0)):
            errs.append(("reports", "C3 sourceAnchored numerator or denominator exceeds allMethods", name))
        if b.get("denominator"):
            if not close(b.get("value"), b["numerator"] / b["denominator"]):
                errs.append(("reports", "C3 sourceAnchored value is not numerator / denominator", name))
        if mc and not (0 <= mc.get("testsNotAnchored", -1) <= mc.get("tests", -1)
                       and mc.get("all") == mc.get("sourceAnchored", -1) + mc.get("noSourceBody", -1)
                       and mc.get("all") == a.get("denominator") and mc.get("tests") == a.get("numerator")
                       and mc.get("sourceAnchored") == b.get("denominator")
                       and mc.get("tests") - mc.get("testsNotAnchored") == b.get("numerator")):
            errs.append(("reports", "C3 methodComposition inconsistent", name))
        if c3.get("scanMode") not in ("source", "bytecode"):
            errs.append(("reports", "C3 scanMode invalid", name))
    c3c = census["metrics"].get("C3") or {}
    calc = c3c.get("calibers")
    if c3c.get("N", 0) >= PUBLISH_N and isinstance(calc, dict):
        ca = calc.get("allMethods") or {}
        if ca.get("N") != c3c.get("N") or ca.get("mean") != c3c.get("mean") or ca.get("missing") != c3c.get("missing"):
            errs.append(("census", "C3 allMethods caliber differs from the published line"))
        cb = calc.get("sourceAnchored") or {}
        # published = the corpus is past the sample gate, this caliber is past the line threshold and was not privacy-blocked
        want = bool(census.get("status") == "published" and cb.get("N", 0) >= PUBLISH_N and cb.get("percentiles") is not None)
        if bool(cb.get("published")) != want:
            errs.append(("census", "C3 sourceAnchored published flag disagrees with its N"))

    def c3_rows(f, t, raw):
        if not isinstance(calc, dict) or c3c.get("N", 0) < PUBLISH_N:
            return
        zh = f.endswith("_zh-cn.md")
        cb = calc.get("sourceAnchored") or {}
        want_b = bool(cb.get("published") and cb.get("N", 0) >= PUBLISH_N)
        for key, m in (("allMethods", c3c), ("sourceAnchored", cb)):
            label = C3_ROWS[key]["zh" if zh else "en"]
            if key == "sourceAnchored" and not want_b:
                if label in t:
                    errs.append((f, "C3 companion row present but the caliber is not published"))
                continue
            q, cells = m["percentiles"], []
            if raw:
                cells.append(str(m["N"]))
            cells += [p4(q[k]) if raw else pct(q[k]) for k in ("p25", "p50", "p75")]
            if raw:
                cells += [p4(q["p90"]), p4(m["mean"])]
            pat = r"^\| " + re.escape(label) + r" \| [^|]+ \| [^|]+ \| " + " ".join(r"([^|]+) \|" for _ in cells) + r"$"
            found = re.findall(pat, t, flags=re.M)
            if len(found) != 1:
                errs.append((f, "C3 caliber rows", key, len(found)))
            elif [c.strip() for c in found[0]] != cells:
                errs.append((f, "C3 caliber row mismatch", key))

    def resolve(base, rel):
        p = os.path.normpath(os.path.join(base, rel))
        return p if os.path.exists(p) else os.path.normpath(os.path.join(repo, os.path.relpath(p, out)))

    def norm(s):  # language-specific links that must differ are folded to one key
        return (s.replace("_zh-cn.md", ".md").replace("README.md#", "R#").replace("README.zh.md#", "R#")
                 .replace("../README.md", "../R").replace("../README_zh-cn.md", "../R"))

    for f in files:
        try:
            t = open(os.path.join(out, f), encoding="utf-8").read()
        except OSError as e:
            errs.append((f, "cannot read", str(e)))
            continue
        texts[f] = t
        base = os.path.dirname(os.path.join(out, f))
        cols = []
        for ln in t.split("\n"):
            if ln.startswith("|"):
                cols.append(ln.count("|") - 1)
            else:
                if cols and len(set(cols)) > 1:
                    errs.append((f, "ragged table cols", cols[:4]))
                cols = []
        if t.count("\n```") % 2:
            errs.append((f, "unbalanced fences"))
        for l in re.findall(r"\]\(([^)]+)\)", t):
            if l.startswith("http"):
                continue
            path, _, frag = l.partition("#")
            if path:
                rp = resolve(base, path)
                if not os.path.exists(rp):
                    errs.append((f, "missing target", l))
                    continue
                if frag and frag not in anchors(open(rp, encoding="utf-8").read()):
                    errs.append((f, "missing anchor in target", l))
            elif frag and frag not in anchors(t):
                errs.append((f, "missing anchor", l))

        if f.startswith("README"):
            rows = re.findall(r"^\| (\d+) \| \[([^\]]+)\]\(https://github.com/[^)]+\) \| [^|]+ \| "
                              + " ".join(r"([\d,]+) \|" for _ in SCALE_KEYS) + r"$", t, flags=re.M)
            if len(rows) != n_repos:
                errs.append((f, "entry rows", len(rows)))
            for _num, name, *vals in rows:
                r = R.get(tuple(name.split("/")))
                if not r:
                    errs.append((f, "unknown system", name))
                    continue
                if vals != [fmt(r[k]) for k in SCALE_KEYS]:
                    errs.append((f, "entry row mismatch", name))
            for k in ("objectCount", "linkCount"):
                if f"| **{fmt(sum(r[k] for r in R.values()))}**" not in t:
                    errs.append((f, "graph total missing", k))
            h, old = ("Data scale and coverage", "Per-repository scale") if f == "README.md" else ("数据规模与覆盖", "逐仓规模")
            if f"## {h}" not in t:
                errs.append((f, "section heading missing", h))
            if old in t:
                errs.append((f, "old section name left"))
            c3_rows(f, t, raw=False)

        if "CORPUS" in f:
            rows = re.findall(r"^\| (\d+) \| \[([^\]]+)\]\(https://github.com/[^)]+\) \| ([A-D](?: ⚠️)?) \| `([0-9a-f]{8})` \| `([0-9a-f]{8})` \| "
                              r"\[report\]\(([^)]+)\) \| " + " ".join(r"([\d,]+) \|" for _ in SCALE_KEYS), t, flags=re.M)
            if len(rows) != n_repos:
                errs.append((f, "full rows", len(rows)))
            for _num, name, _tier, snap, head, link, *vals in rows:
                r = R.get(tuple(name.split("/")))
                if not r:
                    errs.append((f, "unknown system", name))
                    continue
                if not r["snapshotId"].startswith(snap):
                    errs.append((f, "snapshot", name))
                if vals != [fmt(r[k]) for k in SCALE_KEYS]:
                    errs.append((f, "row mismatch", name))
                if not os.path.exists(resolve(base, link)):
                    errs.append((f, "report link", link))
                o, rp = name.split("/")
                if not json.load(open(os.path.join(repo, f"pipeline-status/{o}/{rp}.json"), encoding="utf-8"))["sourceHead"].startswith(head):
                    errs.append((f, "scanned commit", name))

        if "BUILD_LOG" in f:
            # one row per system with a build record; mode cell agrees with the report's scan mode
            rows = re.findall(r"^\| \[([^\]]+)\]\(https://github.com/[^)]+\) \| [^|]+ \| [^|]+ \| ([^|]+) \| "
                              r"[^|]+ \| [\d,]+ / [\d,]+ \| [\d,]+ \| [^|]+ \|$", t, flags=re.M)
            if len(rows) != n_build:
                errs.append((f, "build rows", len(rows), n_build))
            for name, mode in rows:
                r = R.get(tuple(name.split("/")))
                if not r or not r.get("buildRecorded"):
                    errs.append((f, "unknown build system", name))
                    continue
                want = "bytecode" if r["buildMode"] == "bytecode" else ("source (fell back)" if f.endswith("LOG.md") else "source（已回退）")
                if mode.strip() != want:
                    errs.append((f, "build mode mismatch", name, mode.strip(), want))

        if "METRICS" in f:
            c3_rows(f, t, raw=True)
            for mid, m in census["metrics"].items():
                if not m or m["N"] < PUBLISH_N:
                    continue
                for k in ("p25", "p50", "p75", "p90"):
                    v = f"{m['percentiles'][k]:.4f}".rstrip("0").rstrip(".")
                    if v not in t:
                        errs.append((f, "percentile missing", mid, k, v))
                if str(m["N"]) not in t:
                    errs.append((f, "N missing", mid))

    for f, t in texts.items():
        hits = []
        prose = re.sub(r"\]\(http[^)]+\)", "](url)", t)  # URLs are not prose: %-encoded bytes trip the metric-id rules
        for rule in FORBIDDEN:
            for m in re.finditer(rule, prose):
                ctx = prose[max(0, m.start() - 30):m.end() + 30].replace("\n", " ")
                if rule in ALLOWED_IN.get(os.path.dirname(f), ()) and "metrics.D3.scale" in ctx:
                    continue
                hits.append(ctx)
        if hits:
            errs.append((f, "forbidden", hits[:3]))

    for en, zh in pairs:
        a, b = texts.get(en, ""), texts.get(zh, "")
        if len(anchors(a)) != len(anchors(b)):
            errs.append((en, "heading parity", len(anchors(a)), len(anchors(b))))
        ra, rb = (sum(1 for x in x_.split("\n") if x_.startswith("|")) for x_ in (a, b))
        if ra != rb:
            errs.append((en, "table row parity", ra, rb))
        imgs = lambda x_: len(re.findall(r"!\[[^\]]*\]\(", x_))
        if imgs(a) != imgs(b):
            errs.append((en, "badge count parity", imgs(a), imgs(b)))
        links = lambda x_: {norm(x) for x in re.findall(r"(?<!!)\[[^\]]*\]\(([^)]+)\)", x_) if not x.startswith("#")}
        if links(a) != links(b):
            errs.append((en, "link set parity", sorted(links(a) ^ links(b))[:8]))

    print("ERRORS (%d):" % len(errs))
    for e in errs[:40]:
        print("  ", e)
    print("lines", {f: len(texts[f].splitlines()) for f in texts})
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
