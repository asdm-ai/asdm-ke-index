#!/usr/bin/env python3
"""Validate the rendered documentation of asdm-ke-index against the repository's artifacts.

Checked:
  - every table has a constant column count; code fences are balanced
  - every relative link and anchor resolves
  - every number in the entry page and the corpus table equals census/summary.json
    (and pipeline-status for the scanned commit)
  - the metrics documents carry the published percentiles and sample sizes
  - the two language versions have the same structure (headings, table rows, badge count, links)
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
PAIRS = [("README.md", "README_zh-cn.md"), ("docs/METRICS.md", "docs/METRICS_zh-cn.md"),
         ("docs/CORPUS.md", "docs/CORPUS_zh-cn.md"), ("docs/PIPELINE.md", "docs/PIPELINE_zh-cn.md")]
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


def slug(h):
    h = h.strip().lower()
    return re.sub(r"[^\w\- ]", "", h, flags=re.U).replace(" ", "-")


def anchors(t):
    return {slug(x) for x in re.findall(r"^#{1,6}\s+(.*)$", t, flags=re.M)}


def fmt(x):
    return f"{x:,}"


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "."
    repo = os.environ.get("DOCS_REPO", out)
    census = json.load(open(os.path.join(repo, "census/summary.json"), encoding="utf-8"))
    R = {(r["owner"], r["repo"]): r for r in census["repos"]}
    n_repos = len(R)
    errs, texts = [], {}

    def resolve(base, rel):
        p = os.path.normpath(os.path.join(base, rel))
        return p if os.path.exists(p) else os.path.normpath(os.path.join(repo, os.path.relpath(p, out)))

    def norm(s):  # language-specific links that must differ are folded to one key
        return (s.replace("_zh-cn.md", ".md").replace("README.md#", "R#").replace("README.zh.md#", "R#")
                 .replace("../README.md", "../R").replace("../README_zh-cn.md", "../R"))

    for f in FILES:
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

        if "METRICS" in f:
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

    for en, zh in PAIRS:
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
