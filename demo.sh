#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"

if [[ -x .venv/bin/python ]]; then
  python=.venv/bin/python
elif [[ -f .venv/Scripts/python.exe ]]; then
  python=.venv/Scripts/python.exe
else
  if command -v python3 >/dev/null 2>&1; then
    python3 -m venv .venv
  else
    python -m venv .venv
  fi
  if [[ -x .venv/bin/python ]]; then
    python=.venv/bin/python
  else
    python=.venv/Scripts/python.exe
  fi
fi

"$python" -m pip --disable-pip-version-check install -q -r requirements-dev.txt
checks=(
  test_api.APITests.test_public_demo_links_to_recorded_evidence
  test_bounties.BountyTests.test_full_merge_flow_pays_only_once
  test_bounties.BountyTests.test_sensitive_workflow_change_requires_review
  test_bounties.BountyTests.test_changed_head_invalidates_passing_review
  test_bounties.BountyTests.test_refund_waits_for_deadline
  test_github.GitHubTests.test_old_pr_head_cannot_reuse_green_run
  test_github.GitHubTests.test_old_base_cannot_reuse_green_run
  test_github.GitHubTests.test_same_name_wrong_app_is_rejected
)
PYTHONPATH=tests "$python" -m unittest -v "${checks[@]}"
printf '\n%s/%s verification checks as expected.\n' "${#checks[@]}" "${#checks[@]}"
