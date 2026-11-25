#!/usr/bin/env bash
# =============================================================================
# Git push · 按拒绝原因分类重试（scan.yml 产物入库步与 census 提交步共用）
# -----------------------------------------------------------------------------
# 背景（run #33 hibernate-orm，2026-11-25 15:58Z）：产品链路 overall=pass，但
# 末步 git push 被 GitHub 以 `remote: Internal Server Error` 连拒 5 次——旧循环
# 把"服务端瞬时错误"与"非快进"同等对待（一律 fetch+rebase，退避 5/10/15/20/25s，
# 总窗口仅 82s），瞬时 5xx 未恢复即宣告失败 → report/status 未落库、该仓从
# census validation 中静默消失。
#
# 分类（依据 git push 输出）：
#   nonff     非快进（fetch first / non-fast-forward / stale info）——远端有新
#             提交：fetch + rebase 后短退避重试。rebase 冲突属确定性失败，
#             立即中止（重试无意义）。
#   transient 服务端瞬时错误（5xx / 网关 / 超时 / 连接类）——与本地分支无关：
#             **不 rebase**，指数退避重试（base·2^n，封顶 cap），总预算 budget。
#   fatal     其它（鉴权失败、保护分支、hook 拒绝、文件超限等）——确定性
#             失败，仅做少量短重试兜底后快速失败。
#
# 用法（仓库工作区内，已完成 commit）：
#   bash scripts/push-with-retry.sh
# 环境变量（均可缺省；测试时调小）：
#   PUSH_BRANCH          目标分支（缺省 GITHUB_REF_NAME，再缺省 main）
#   PUSH_BUDGET_SEC      总重试预算（秒，缺省 900）
#   PUSH_MAX_ATTEMPTS    最大尝试次数（缺省 20）
#   PUSH_TRANSIENT_BASE  瞬时错误首次退避（秒，缺省 20）
#   PUSH_TRANSIENT_CAP   瞬时错误退避封顶（秒，缺省 180）
#   PUSH_FATAL_ATTEMPTS  fatal 类最大尝试次数（缺省 3）
# 退出码：0=推送成功；1=重试耗尽 / rebase 冲突 / fatal 类失败。
# =============================================================================
set -uo pipefail

BRANCH="${PUSH_BRANCH:-${GITHUB_REF_NAME:-main}}"
BUDGET_SEC="${PUSH_BUDGET_SEC:-900}"
MAX_ATTEMPTS="${PUSH_MAX_ATTEMPTS:-20}"
T_BASE="${PUSH_TRANSIENT_BASE:-20}"
T_CAP="${PUSH_TRANSIENT_CAP:-180}"
FATAL_ATTEMPTS="${PUSH_FATAL_ATTEMPTS:-3}"

NONFF_RE='fetch first|non-fast-forward|stale info|Updates were rejected'
TRANSIENT_RE='Internal Server Error|Service Unavailable|Bad Gateway|Gateway Timeout|Gateway Time-out|timed out|Timeout|Connection refused|Connection reset|Could not resolve host|temporarily unavailable|RPC failed|the remote end hung up|returned error: 5[0-9][0-9]|HTTP 5[0-9][0-9]|overloaded'

now() { date +%s; }
START=$(now)
n_transient=0
n_fatal=0

for i in $(seq 1 "$MAX_ATTEMPTS"); do
  OUT=$(git push 2>&1)
  RC=$?
  printf '%s\n' "${OUT}"
  if [ "${RC}" -eq 0 ]; then
    echo "push-with-retry: OK (attempt ${i}, elapsed $(( $(now) - START ))s)"
    exit 0
  fi

  ELAPSED=$(( $(now) - START ))
  if printf '%s\n' "${OUT}" | grep -q -E "${NONFF_RE}"; then
    KIND=nonff
  elif printf '%s\n' "${OUT}" | grep -q -E "${TRANSIENT_RE}"; then
    KIND=transient
  else
    KIND=fatal
  fi
  echo "push-with-retry: attempt ${i} rejected as ${KIND} (elapsed ${ELAPSED}s)"

  if [ "${KIND}" = "nonff" ]; then
    git fetch origin "${BRANCH}"
    if ! git rebase "origin/${BRANCH}"; then
      git rebase --abort
      echo "FAIL: rebase conflict（远端提交与本次产物冲突，需人工处理）" >&2
      exit 1
    fi
    WAIT=$(( i * 5 ))
  elif [ "${KIND}" = "transient" ]; then
    n_transient=$(( n_transient + 1 ))
    WAIT=$(( T_BASE * (1 << (n_transient - 1)) ))
    [ "${WAIT}" -gt "${T_CAP}" ] && WAIT="${T_CAP}"
    REMAINING=$(( BUDGET_SEC - ELAPSED ))
    if [ "${REMAINING}" -le 0 ]; then
      echo "FAIL: push retries exhausted（瞬时错误重试预算 ${BUDGET_SEC}s 用尽）" >&2
      exit 1
    fi
    [ "${WAIT}" -gt "${REMAINING}" ] && WAIT="${REMAINING}"
  else
    n_fatal=$(( n_fatal + 1 ))
    if [ "${n_fatal}" -ge "${FATAL_ATTEMPTS}" ]; then
      echo "FAIL: push rejected（非重试类错误——鉴权/保护分支/hook 等，需人工处理）" >&2
      exit 1
    fi
    WAIT=10
  fi

  echo "push-with-retry: sleep ${WAIT}s before retry"
  sleep "${WAIT}"
done

echo "FAIL: push retries exhausted（已达最大尝试次数 ${MAX_ATTEMPTS}）" >&2
exit 1
