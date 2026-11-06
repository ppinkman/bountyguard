# Coding-agent bounty walkthrough

This project-operated run uses real GitHub, MCP stdio, GitHub Actions,
NEAR AI Cloud and NEAR testnet. The coding agent is **Codex in the development
session**; the separate advisory review model is **Qwen/Qwen3.6-35B-A3B-FP8**
through NEAR AI Cloud. The MCP client is a tool adapter, not another coding model.

The separate [single-bounty machine-account runner](AGENT_DEMO.md) has local
fixture coverage. This walkthrough records the earlier development-session run.

## Task and acceptance

[Issue #5](https://github.com/ppinkman/bountyguard/issues/5) describes an actual
long-running-agent problem: the local API session expires after one hour, but
the MCP backend keeps reusing that expired session. Authorized writes then fail
until the MCP process restarts.

The assigned reward is 0.005 free tNEAR. Both GitHub roles use `ppinkman`
(numeric user ID 100271001). The maintainer is
`bg-c7e1a78e-owner.testnet`; the claimant is
`bg-c7e1a78e-worker.testnet`. Both wallet identities were verified using
NEP-413 signatures and current FullAccess-key membership. This is not an
independent contributor, customer or commercial payment.

## Who did each step

| Step | Role and actual action | Evidence |
| --- | --- | --- |
| Create and bind | Operator acting as maintainer created the Issue/draft; each role used a separate local test signer to bind its wallet | Bounty `a42812e2aa774476b0ad2478f2ba6c58`; public wallet proofs in the evidence bundle |
| Read and claim | Codex called `get_bounty` then `request_claim` through the real MCP stdio client | Claim `063cbc52241f41b092f2aab835189cea` |
| Assign and fund | Operator acting as maintainer confirmed that claim and funded its exact terms; MCP has no funding tool | [Funding receipt](https://testnet.nearblocks.io/txns/4o4oragjmfiQxXuG32dXzBkp7WQXPdZEjX4YzMoub7GY) |
| Fix | Codex added seven regression tests, observed the old failure, then implemented one-time recovery only for explicit HTTP 401 | [PR #6](https://github.com/ppinkman/bountyguard/pull/6), head `0dc050e55a48ebec5aef19bbf021b496f6a44f14` |
| Submit | Codex called `submit_pull_request` through MCP | Same bounty, claim and PR |
| Verify | GitHub hosted CI passed; Codex requested one advisory model review through MCP; deterministic checks and model report passed | [CI run](https://github.com/ppinkman/bountyguard/actions/runs/41984133420); report hash `ce170adbf3c09b5e42656f3c7701de57acbf7df82992d55de8fda4fe73d96b9f` |
| Merge | Operator acting as maintainer merged with an expected-head condition | Merge commit `1e94cbe58ce33e08517de2326d4ecb9fae312af6` |
| Settle and read | Maintainer service rechecks the merge and sends the existing order's settlement; claimant reads its final receipt through MCP | Final result is recorded in the public acceptance bundle |

Result: **PAID**. The agent obtained [the actual payment transaction](https://testnet.nearblocks.io/txns/EHb7dgpu3ZTJdp5edLdPd5fq7yYkr3tkRrdKXR76A6Yg)
through its final MCP `get_bounty` call. Repeating settlement returned that same
receipt. The run added one model request (5,862 provider-reported tokens), one
funding intent, one evidence-recording intent and one payment intent. No mainnet
funds or recharge were used. Wallet/storage/gas amounts are testnet-only.

Read-only verification of this run and the original payment/refund:

```sh
python tools/verify_acceptance.py --receipt deployments/agent-acceptance.json
```

Expect `verified: true`, two `Paid` bounties, one `Refunded` bounty, six verified
wallet signatures and the reviewed heads for PR #3 and PR #6. This checks public
facts and receipt consistency; it cannot independently prove which model typed
the code. Full MCP tool arguments/results are in the evidence bundle and contain
no GitHub tokens, provider keys or wallet private keys.

The maintainer actions above were performed by the development assistant under
the user's explicit authorization. This does not demonstrate a separate human
reviewer approving the patch, an unattended autonomous coder, or two independent
businesses. The review model never received signing keys or payment authority.

## Run the claimant-side commands

Start the API first. A contributor provides their own GitHub token in the process
environment and completes wallet binding. Replace `BOUNTY_ID` with an existing
draft/funded bounty appropriate for each stage. The maintainer must assign and
fund the claim before delivery; these commands do not bypass those steps.

```sh
python tools/agent_client.py get BOUNTY_ID --output artifacts/01-read.json
python tools/agent_client.py claim BOUNTY_ID --allow-writes --output artifacts/02-claim.json
# Implement the Issue, run tests, push a branch and open a real GitHub PR.
python tools/agent_client.py submit BOUNTY_ID --pr-url https://github.com/OWNER/REPO/pull/NUMBER --allow-writes --output artifacts/03-submit.json
# Wait until the trusted workflow has completed successfully.
python tools/agent_client.py review BOUNTY_ID --allow-writes --allow-model --use-model --output artifacts/04-review.json
# Maintainer merges the exact reviewed version and triggers settlement.
python tools/agent_client.py receipt BOUNTY_ID --output artifacts/05-receipt.json
```

Only the review command may consume model credits, and it needs both process
permission and the backend's model configuration. Receipt lookup never pays.
An unavailable/invalid model result is retained without an automatic paid retry.
Never retry an uncertain signed operation by creating a replacement bounty.

## What the fix changes

An authenticated request that receives HTTP 401 clears the cached session,
logs in again as the same process-local GitHub actor, and retries once. Another
401 stops. Other HTTP errors and ambiguous transport outcomes are not retried.
Error response streams are closed. The write/model permission gates, destination
restriction and redirect refusal remain in place.

The seven new tests produced two failures and one error before the fix and all
passed after it; the full Python suite passed 82 tests. These regression cases
use controlled HTTP responses, not a claim that the real service was left idle
for an hour. The surrounding bounty flow uses real external services.
