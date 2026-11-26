#!/usr/bin/env python3
# =============================================================================
# KE Index · 仓规模采集（文件数 / 行数——D3 规模画像的文件级参照）
# -----------------------------------------------------------------------------
# 用法：
#   python3 scripts/repo-scale.py --repo <clone 目录> [--out <file>|-]
# 调用点（两处，同一份度量代码）：
#   1. scan-one.sh：clone 之后、import 之前（"扫描的同时生成"——同一工作树、
#      同一 HEAD，与导入分析的输入逐字节同源）
#   2. scale-backfill workflow：存量 report 按 snapshot.sourceHead 检出同一
#      提交补采（不碰服务端 / 快照 / 投影）
# 口径（全部写入输出 method 字段——report 读者不必翻脚本）：
#   - 文件清单 = git ls-files（tracked 文件；子模块 gitlink 不是文件）
#   - files.tracked            原始 tracked 数（不过滤）
#   - files.skippedByAnalyzerDirs  位于分析器跳过目录内的 tracked 数
#     （SKIP_DIRS 与分析器 repoScanner.ts 逐项对齐：target/build/dist/node_modules
#     等——仅作用于目录；与目录同名的普通文件照常计数）
#   - files.nonRegular         符号链接等非普通文件（分析器 Dirent.isFile()
#     为假、不计数——同口径剔除；不跟随符号链接读工作树之外的内容）
#   - files.total              = tracked - skipped - nonRegular（分析器
#     Repository.fileCount 同口径——compute-metrics 以此与服务端对照）
#   - files.text / files.binary  二进制判定 = 首 8000 字节含 NUL（git 同启发式）
#   - lines.*                  文本文件物理行数：LF 计数，末行无换行符计 1 行；
#     含注释与空行——不是 SLOC（去注释需逐语言实现，不在本脚本范围）
#   - byLanguage                扩展名 → 语言（分析器 EXT_LANG + sql/html/css/c/
#     python/go/template 补充）；未命中归 "other"。规模参照以 java 为主指标：
#     总行数会被设计文档 / SVG / 生成物显著抬高（mall：.pdb+.pdm 4.1 万行）
# 输出确定性：同一提交逐字节一致（键排序、语言表固定、无墙钟）。
# 依赖：Python 3.8+ 标准库 + git（零第三方依赖）。
# =============================================================================
import argparse
import json
import os
import stat
import subprocess
import sys

SCHEMA_VERSION = "repo-scale-v1"

# 与分析器 repoScanner.ts SKIP_DIRS 逐项对齐（仅作用于目录：文件所在的目录段
# 任一命中即跳过；文件名本身等于目录名不触发——与分析器 entry.isDirectory() 分支同语义）
SKIP_DIRS = frozenset([
    ".git", "node_modules", "target", "build", ".idea", ".vscode",
    "dist", "out", ".gradle", ".mvn",
])

# 分析器 EXT_LANG 逐项对齐 + 本脚本补充项
EXT_LANG = {
    ".java": "java",
    ".xml": "xml",
    ".gradle": "gradle",
    ".kt": "kotlin",
    ".groovy": "groovy",
    ".properties": "properties",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".json": "json",
    ".md": "markdown",
    ".ts": "typescript",
    ".js": "javascript",
    ".tsx": "tsx",
    ".vue": "vue",
    ".sh": "shell",
    # ---- 以下为本脚本补充（分析器不计入 languageStats 的扩展名）----
    ".sql": "sql",
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".scss": "css",
    ".less": "css",
    ".c": "c",
    ".h": "c",
    ".py": "python",
    ".go": "go",
    ".ftl": "template",
    ".vm": "template",
}

BINARY_SNIFF_BYTES = 8000
CHUNK = 1 << 20

METHOD = (
    "文件清单 = git ls-files（tracked）；files.total 剔除分析器跳过目录"
    "（target/build/dist/node_modules 等，与分析器 SKIP_DIRS 逐项对齐）与符号链接等"
    "非普通文件，与分析器 Repository.fileCount 同口径；二进制 = 首 8000 字节含 NUL；"
    "行数 = 文本文件物理行数（LF 计数，末行无换行符计 1 行），含注释与空行，非 SLOC；"
    "语言按扩展名归类，未命中归 other；规模参照以 java 为主指标"
)


def git(repo, *args):
    p = subprocess.run(["git", "-C", repo] + list(args), capture_output=True)
    if p.returncode != 0:
        raise RuntimeError("git %s 失败（rc=%d）：%s" % (
            " ".join(args), p.returncode, p.stderr.decode("utf-8", "replace").strip()[:300]))
    return p.stdout


def lang_of(name):
    return EXT_LANG.get(os.path.splitext(name)[1].lower(), "other")


def in_skipped_dir(rel):
    """文件是否位于分析器跳过目录内（只看所在目录段，不看文件名本身）。

    分析器 SKIP_DIRS 只作用于目录项（entry.isDirectory() 分支）——仓根下名为
    build / target 等的普通文件照常计数（apache/dubbo 根目录有 tracked 可执行
    脚本 `build`：首版按"任一路径段"匹配把它漏掉，CI 4860 != server 4861，
    由 fileCount 对照抓出）。
    """
    parts = rel.split("/")
    return any(part in SKIP_DIRS for part in parts[:-1])


def scan_file(path):
    """→ (is_binary, line_count, byte_count)。二进制文件 line_count=0。"""
    is_binary = False
    nl = 0
    nbytes = 0
    last = b""
    with open(path, "rb") as fh:
        first = fh.read(BINARY_SNIFF_BYTES)
        nbytes = len(first)
        if b"\0" in first:
            return True, 0, nbytes + sum(len(c) for c in iter(lambda: fh.read(CHUNK), b""))
        nl = first.count(b"\n")
        if first:
            last = first[-1:]
        for chunk in iter(lambda: fh.read(CHUNK), b""):
            nbytes += len(chunk)
            nl += chunk.count(b"\n")
            last = chunk[-1:]
    if nbytes and last != b"\n":
        nl += 1
    return is_binary, nl, nbytes


def measure(repo_dir):
    """度量 clone 目录当前 HEAD → 规模字典（确定性）。"""
    repo_dir = os.path.abspath(repo_dir)
    if not os.path.isdir(os.path.join(repo_dir, ".git")):
        raise RuntimeError("不是 git 工作树：%s" % repo_dir)
    head = git(repo_dir, "rev-parse", "HEAD").decode("ascii").strip()
    names = [n for n in git(repo_dir, "ls-files", "-z").split(b"\0") if n]

    files = {
        "tracked": len(names),
        "skippedByAnalyzerDirs": 0,
        "nonRegular": 0,
        "total": 0,
        "text": 0,
        "binary": 0,
        "byLanguage": {},
    }
    lines = {"total": 0, "byLanguage": {}}
    total_bytes = 0

    for raw in names:
        rel = raw.decode("utf-8", "surrogateescape")
        if in_skipped_dir(rel):
            files["skippedByAnalyzerDirs"] += 1
            continue
        path = os.path.join(repo_dir, rel)
        try:
            st = os.lstat(path)
        except OSError:
            # tracked 但工作树缺失（浅克隆 / 稀疏检出形态）——与"非普通文件"同归一类，
            # 不计入 total（分析器 walk 同样见不到）
            files["nonRegular"] += 1
            continue
        if not stat.S_ISREG(st.st_mode):
            files["nonRegular"] += 1
            continue
        files["total"] += 1
        lang = lang_of(rel)
        is_binary, nlines, nbytes = scan_file(path)
        total_bytes += nbytes
        if is_binary:
            files["binary"] += 1
        else:
            files["text"] += 1
            lines["total"] += nlines
            lines["byLanguage"][lang] = lines["byLanguage"].get(lang, 0) + nlines
        files["byLanguage"][lang] = files["byLanguage"].get(lang, 0) + 1

    return {
        "schemaVersion": SCHEMA_VERSION,
        "sourceHead": head,
        "method": METHOD,
        "files": files,
        "lines": lines,
        "bytes": {"total": total_bytes},
    }


def main():
    ap = argparse.ArgumentParser(description="KE Index 仓规模采集（文件数 / 行数）")
    ap.add_argument("--repo", required=True, help="clone 目录（git 工作树）")
    ap.add_argument("--out", default="-", help="输出文件（缺省 - = stdout）")
    args = ap.parse_args()
    try:
        result = measure(args.repo)
    except (RuntimeError, OSError) as e:
        print("FAIL: repo-scale：%s" % e, file=sys.stderr)
        return 1
    text = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.out == "-":
        sys.stdout.write(text)
        return 0
    try:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text)
    except OSError as e:
        print("FAIL: repo-scale：输出不可写 %s：%s" % (args.out, e), file=sys.stderr)
        return 1
    print("repo-scale: files=%d（tracked=%d skipped=%d nonRegular=%d text=%d binary=%d）"
          " lines=%d java=%d/%d" % (
              result["files"]["total"], result["files"]["tracked"],
              result["files"]["skippedByAnalyzerDirs"], result["files"]["nonRegular"],
              result["files"]["text"], result["files"]["binary"],
              result["lines"]["total"],
              result["files"]["byLanguage"].get("java", 0),
              result["lines"]["byLanguage"].get("java", 0)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
