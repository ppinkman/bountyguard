# Tests and evidence verification

Install Python 3.11+ and the development dependencies:

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests
```

The suite covers the API, identity verification, bounty lifecycle, GitHub
checks, model review, MCP sessions and the agent runner. It uses local fixtures.
The Docker isolation probe runs when `BOUNTYGUARD_TEST_IMAGE` is configured;
otherwise that probe is skipped. The push workflow builds and tests the image.

## Focused checks

`./demo.sh` requires Bash and runs these eight checks. It creates a virtual
environment and installs dependencies on its first run. Successful output ends
with `8/8 verification checks as expected.`

| Behavior | Test |
| --- | --- |
| Demo links match the recorded evidence | `test_api.APITests.test_public_demo_links_to_recorded_evidence` |
| A merged bounty pays once | `test_bounties.BountyTests.test_full_merge_flow_pays_only_once` |
| A protected workflow change requires review | `test_bounties.BountyTests.test_sensitive_workflow_change_requires_review` |
| A new commit invalidates the old review | `test_bounties.BountyTests.test_changed_head_invalidates_passing_review` |
| Refund waits for the deadline | `test_bounties.BountyTests.test_refund_waits_for_deadline` |
| A previous PR head cannot reuse passing CI | `test_github.GitHubTests.test_old_pr_head_cannot_reuse_green_run` |
| A previous base cannot reuse passing CI | `test_github.GitHubTests.test_old_base_cannot_reuse_green_run` |
| A same-name check from another app is rejected | `test_github.GitHubTests.test_same_name_wrong_app_is_rejected` |

## Public records

```bash
python tools/verify_acceptance.py
python tools/verify_acceptance.py --receipt deployments/agent-acceptance.json
```

These commands need public GitHub and NEAR testnet RPC access. An optional
`GITHUB_TOKEN` increases the GitHub rate allowance. No private key or model
request is needed. The extended record includes two paid bounties, one refunded
bounty and six wallet signatures. A successful run reports `verified: true`.

The verifier checks current chain state, signature validity and GitHub facts
against stored records. It does not reconstruct historical challenge use or
independently establish model reasoning and authorship. Receipt contents are
retained as recorded so their hashes remain verifiable.

## Wallet and contract tests

```bash
npm ci --ignore-scripts --no-fund
npm test
npm run build
python tools/contract.py test
```

The wallet bundle is committed. After rebuilding, check that any bundle diff
matches an intended source or dependency change. Contract tests require Rust;
`python tools/contract.py build` also requires `wasm32-unknown-unknown`.

## Read-only PR inspection

```bash
python tools/inspect_github.py --pr https://github.com/OWNER/REPO/pull/NUMBER
```

Inspection stores local output in ignored `artifacts/`. It creates no bounty
or transaction. Review intents and runner checkpoints belong in ignored `data/`.
