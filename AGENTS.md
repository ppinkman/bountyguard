# Verify BountyGuard

Open the [public replay](https://ppinkman.github.io/bountyguard/) to see four
recorded decisions. Each card links to its original GitHub or NEAR evidence.

From the repository root, run `./demo.sh` with Python 3.11+ and Bash. Expect
`8/8 verification checks as expected.` The first run may need internet access
to install Python packages. The checks use fixtures and recorded evidence.
They require no GitHub login, wallet, model key, or Docker.

| Behavior | Check run by `./demo.sh` |
| --- | --- |
| The public page shows links for all four recorded decisions | `test_api.APITests.test_public_demo_links_to_recorded_evidence` |
| The reviewed and merged delivery is paid exactly once | `test_bounties.BountyTests.test_full_merge_flow_pays_only_once` |
| A change to a protected workflow requires review | `test_bounties.BountyTests.test_sensitive_workflow_change_requires_review` |
| Changing the head after review invalidates settlement | `test_bounties.BountyTests.test_changed_head_invalidates_passing_review` |
| The principal can be refunded after expiry | `test_bounties.BountyTests.test_refund_waits_for_deadline` |
| Old CI cannot authorize a different head or base | `test_github.GitHubTests.test_old_pr_head_cannot_reuse_green_run`, `test_old_base_cannot_reuse_green_run` |
| A check from a different app cannot supply trusted CI | `test_github.GitHubTests.test_same_name_wrong_app_is_rejected` |

For a read-only check against GitHub and NEAR testnet, run
`python tools/verify_acceptance.py` in the installed environment. Expect
`"verified": true` with chain states `Paid` and `Refunded`. The network check
does not submit a transaction. See the [recorded evidence](deployments/live-acceptance.json)
and [README](README.md) for scope and reproduction details.
