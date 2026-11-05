# BountyGuard

Assigned GitHub bounties with verified claimant identity, revision-bound review,
and NEAR testnet settlement after a maintainer merges the reviewed PR.

**Development preview, not an audited service.** This repository is a new project;
[NOTICE](NOTICE.md) describes its relationship to the earlier ProofPay prototype.
The submission plan is to select one final project.

## Live demonstration

The public, project-operated demonstration completed on November 5, 2026:

| Scenario | Observed result |
| --- | --- |
| [Issue #1](https://github.com/ppinkman/bountyguard/issues/1) → [PR #3](https://github.com/ppinkman/bountyguard/pull/3) → trusted CI → NEAR AI review → merge | **Paid 0.005 tNEAR** to the assigned contributor ([transaction](https://testnet.nearblocks.io/txns/B35cMBZLzvYjpBVEF24isUd9HAr4tTa596fGv771XYQt)) |
| [Adversarial PR #4](https://github.com/ppinkman/bountyguard/pull/4), with genuinely green CI | **NEEDS_REVIEW**, no payment: protected workflow modification and review-manipulation text |
| A new commit pushed after a successful review | **REVISION_CHANGED**, no settlement against the old report; probe retained on `codex/toctou-probe` |
| [Issue #2](https://github.com/ppinkman/bountyguard/issues/2), intentionally without delivery | **Refunded 0.005 tNEAR principal** ([transaction](https://testnet.nearblocks.io/txns/GWtzhGA7PTGgBK8CXLnkkeqV1pKRUedT2xVZ3VZyrDq9)); storage/gas not returned |
| Repeated settlement/refund requests | Original receipts returned; only one pay and one refund intent |
| Real MCP stdio review of the same accepted revision | Cached result reused; model request count stayed at three |

Both GitHub roles were operated by **the same project developer**, with distinct
NEP-413-verified testnet wallets. These are controlled acceptance tests, not
independent customers or paid production activity. No mainnet funds or recharge
were used. Three actual NEAR AI requests reported 25,190 total tokens; one
response failed grounding validation and did not authorize payment. Token usage
and catalog estimates do not establish the provider's actual bill.

The [public evidence bundle](deployments/live-acceptance.json) includes wallet
proofs, revision-bound reports, CI identifiers, operation receipts and rejection
records. Check current chain state and public GitHub facts without private keys
or another model call:

```powershell
.venv/Scripts/python tools/verify_acceptance.py
```

The verifier needs public GitHub/testnet RPC access. An optional `GITHUB_TOKEN`
increases GitHub's rate allowance. It verifies recorded signatures and **current**
key membership; it cannot independently reconstruct historical challenge use,
prove the model's conclusions, or prove commercial adoption.

## Start locally

Python 3.11+:

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
.\start.ps1
```

Open **http://127.0.0.1:8766/**. English is the default; the top-right button
switches to Chinese. The board starts empty. No model call or transaction is
sent at startup. This is a loopback development application, not a hosted OAuth
service; do not expose it to the public internet.

For the existing local development machine:

```powershell
.\start_dev.ps1 -UseGitHubLogin -UseExistingAiCredits -DirectNetwork
```

This uses the existing `gh` login in process memory and can optionally read the
existing encrypted NEAR AI key without copying it. Alternatively set
`NEAR_AI_API_KEY` in the launching process. No token or private key belongs in
chat, Git, screenshots, command arguments or browser local storage.

## Assigned-bounty flow

1. **Maintainer signs in.** A GitHub token is verified with `GET /user`.
   Numeric user IDs are authoritative; login names are display values. Tokens
   are retained only in server memory for a one-hour session. Public repository
   bounties require verified repository write/maintain/admin permission.
2. **Create a draft for a real, open Issue.** The Issue text, repository ID,
   amount, deadline, source paths and trusted workflow/check requirements are
   fixed in hashed terms. Draft creation does not fund anything.
3. **Bind both wallets.** Each participant obtains a five-minute, single-use
   NEP-413 challenge. Its context includes the numeric GitHub ID, account, role,
   bounty, repository, Issue, network and terms. Verification also queries the
   current testnet access key and requires FullAccess. A valid signature from
   an unrelated, locally generated key is rejected.
4. **Claim, assign and confirm funding.** The contributor requests assignment;
   the maintainer selects that claim and confirms the exact assigned terms hash.
   Distinct maintainer/claimant wallets are fixed before the chain call.
5. **Submit an existing PR as its authenticated author.** Its base repository
   and author IDs must match. A fork is allowed. GitHub closing-Issue references
   establish linkage; merely mentioning an Issue is insufficient.
6. **Review one exact revision.** Collect complete bounded file patches, trusted
   workflow/run/job/check evidence, and optional real NEAR AI review. Ordinary
   test changes are listed; sensitive configuration changes, removed-assertion
   signals and configured manipulation signals require review and cannot pass
   automatically in this release.
7. **Merge, recheck, settle.** The maintainer's merge is the acceptance action.
   Current PR author/repository/head/diff, Issue terms, CI and merge ancestry are
   rechecked. Changed code invalidates the old review. With the page open and
   the maintainer signed in, the browser checks a ready bounty every 30 seconds;
   there is no unattended keeper when that page is closed. The API/refresh button
   can also trigger the same check. Only a matching final transfer callback is
   marked paid. Repeated syncs return the same paid bounty.
8. **Expiry.** A caller explicitly triggers the contract's refund method. The
   principal returns to the original maintainer; storage and spent gas do not.

### Wallet signing in this preview

Wallet-extension connection is not implemented yet. The UI downloads a standard
NEP-413 challenge and accepts a signed proof, never a private key. A local test
account can sign via:

```powershell
.venv/Scripts/python -m bountyguard sign-challenge challenge.json --vault data/testnet/claimant.dpapi
```

Paste the returned public proof into the wallet-verification form. This developer
flow is a stated limitation, not a claim of tested OKX/Wallet Selector support.
FullAccess signing must occur locally in a trusted wallet/signing environment.

## Testnet development

New BountyGuard accounts and journals are isolated from ProofPay. Windows DPAPI
is used for the development signer; the application never imports ProofPay code.
Reading and verifying public data is cross-platform.

```powershell
# Requires the testnet faucet to be available; saves keys encrypted before use.
.venv/Scripts/python tools/setup_testnet.py create-free-accounts

# Rust + wasm32-unknown-unknown required. A preinstalled tool bundle can be selected.
.venv/Scripts/python tools/contract.py build
.venv/Scripts/python tools/setup_testnet.py deploy
.\start_dev.ps1 -UseGitHubLogin -UseExistingAiCredits -EnableTestnet -DirectNetwork
```

| Guard | Development value |
| --- | --- |
| Network | Named `.testnet` accounts only; runtime network check |
| Maximum reward | 0.01 tNEAR per bounty |
| Storage charge | 0.01 tNEAR per funded bounty, separate from reward |
| Funding intents | 2, persisted in this project's journal |
| Model intents | 3 per rolling 24 hours, persisted in the same application DB |
| Model estimate | Conservative public-catalog estimate ≤ $0.02 per request |
| Unknown outcome | Retain the original intent/hash; query it, never replace payment |

The price estimate is not a provider-enforced billing cap. Model usage is
separate from tNEAR payments and is not reversed by a bounty refund. No mainnet
transaction, currency conversion, recharge or live paid bounty is claimed.

## Evidence and verification

```powershell
.venv/Scripts/python -m pip install -r requirements-dev.txt
.venv/Scripts/python -m unittest discover -s tests
.venv/Scripts/python tools/contract.py test

# Read-only inspection: no bounty/funding/transaction; uses existing gh login.
.venv/Scripts/python tools/inspect_github.py --pr https://github.com/pallets/flask/pull/6176
```

The Python fixtures are explicitly labelled unit-test adapters. They are not
third-party suppliers or real chain receipts. Local inspection evidence is saved
under ignored `artifacts/`; review intents live in ignored `data/`.
See [DEVELOPMENT_STATUS](DEVELOPMENT_STATUS.md) for what has actually been run.

## MCP

Start `.venv/Scripts/python -m bountyguard.mcp_server` with the web/API service
already running. Tools list/read bounties, request a verified claim, submit an
existing PR and review its revision. Writes require operator environment flag
`BOUNTYGUARD_MCP_ALLOW_WRITES=1` and the participant's `GITHUB_TOKEN`.
Model use additionally requires `BOUNTYGUARD_MCP_ALLOW_MODEL=1` and backend
credit permission. Funding and payment are not exposed as MCP tools in v0.1.
This server does not write GitHub issues, comments or PRs.

## Security boundaries

- The contract cannot read GitHub or verify AI reasoning. The maintainer-owned
  signer attests to off-chain evidence; hashes prevent substituting that evidence.
- CI success and an AI PASS do not prove correctness or absence of a backdoor.
  Model findings select server-issued evidence IDs that resolve to exact patch
  text; uncertainty or invalid evidence does not authorize pay.
- An app name/green badge is insufficient: policy binds app ID, workflow ID/path,
  workflow blob, run head/base association, suite, named jobs and check status.
  After merge, GitHub may clear a run's PR association. Only the previously
  accepted association for the identical run, attempt, head/base and checks can
  be reused; current CI success and merge ancestry are still required.
- Review size is bounded (40 files, 48 KB JSON patches, 24 KB per patch); missing,
  binary or incomplete patches stop automatic acceptance. No PR code is executed
  by this server, and no signing secret is sent to a CI job.
- Protected paths and assertion/injection signals are conservative heuristics.
  False positives and missed attacks remain possible. Exceptions/independent
  arbitration are not implemented. Maintainer refusal to merge is not solved.
- Merge/squash ancestry must match the reviewed base; complex rebases or changed
  bases require another review. Sessions and automatic browser polling expire.
- Issues/patches sent for AI review are public. Private repositories, hosted auth,
  account recovery, unattended scheduling and external commercial adoption are
  outside this release.

## References

- [NEP-413](https://github.com/near/NEPs/blob/master/neps/nep-0413.md)
- [GitHub workflow runs](https://docs.github.com/en/rest/actions/workflow-runs)
- [GitHub Actions security](https://docs.github.com/en/actions/reference/security/secure-use)
- [NEAR AI verification](https://docs.near.ai/cloud/verification) — TEE verification
  is not yet implemented here; using the API alone is not presented as attestation.
