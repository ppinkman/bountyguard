# Architecture and security boundaries

BountyGuard combines a local Python service, GitHub Actions checks, NEAR AI
review and a Rust escrow contract on NEAR testnet.

## Bounty lifecycle

The service records an open Issue's text, repository ID, reward, deadline,
allowed source paths and required workflow checks in hashed terms. Draft
creation sends no funds. Both participants sign a NEP-413 challenge before
the maintainer assigns a contributor and funds the bounty.

A submitted PR must belong to the expected repository and authenticated
contributor. It must reference the Issue through GitHub's closing-Issue
relationship. Fork contributions are supported.

The review records the PR number, head commit and diff hash. The service checks
the configured workflow and CI results, then requests an advisory NEAR AI
review. Findings must cite server-issued evidence IDs that resolve to patch
text. Protected configuration changes, removed-assertion signals and configured
review-manipulation signals require manual attention.

The maintainer accepts the work by merging it. Settlement rechecks the PR
author, repository, Issue terms, head, diff, CI and merge ancestry. A different
revision invalidates the old review. Merge and squash ancestry must match the
reviewed base; changed bases or complex rebases require another review.

## Identity and signing

GitHub numeric user IDs identify participants; login names are display values.
NEP-413 challenges are single-use and expire after five minutes. Their context
includes the user ID, wallet, role, bounty, repository, Issue, network and terms.
Verification checks both the signature and current on-chain FullAccess-key
membership. Maintainer and contributor wallets must be distinct.

Browser wallets sign identity messages only. The current development service
uses a local Windows DPAPI signer for transactions. It attests to off-chain
checks on behalf of the maintainer. The contract cannot query GitHub or assess
AI reasoning; it enforces escrow terms, evidence hashes and signer authority.

## CI verification

The policy pins the workflow ID, path and file hash, GitHub app ID, run
head/base association, check suite and required jobs. A matching job name
alone is insufficient. If GitHub clears a run's PR association after merge,
the service can reuse the previously accepted association only for the same
run, attempt, head, base and checks. Current success and merge ancestry are
still required.

For fork runs without a PR association, the pinned workflow's revision-binding
job can establish the PR number and base SHA. The job must belong to the same
run and attempt, and both branches must contain the pinned workflow. Required
test jobs must pass independently.

## Execution and payment

The API parses PR patches without executing submitted code. Review input is
limited to 40 files, 48 KB of JSON patches and 24 KB per patch. Missing, binary
or incomplete patches stop automatic acceptance. The separate agent runner
uses an isolated test container; see [its setup guide](AGENT_DEMO.md).

Transaction intents and review results are persistent. An unknown transaction
outcome is reconciled using its original hash. Only a matching successful
transfer callback marks a bounty paid. Repeated settlement or refund calls
return the recorded result.

While the maintainer is signed in with the page open, the browser checks ready
bounties every 30 seconds. Closing the page stops this polling; there is no
background settlement service. The API and refresh button can also trigger a
check. Expired rewards require an explicit refund call; storage and gas are
not refunded.

## Current limitations

- CI success and an AI review do not prove correctness or absence of a backdoor.
  Review signals are heuristics and can miss problems or raise false positives.
- The maintainer controls merge and the transaction signer. Independent
  arbitration and disputes over refusal to merge are not implemented.
- This is a local testnet application without a security audit, hosted OAuth,
  private repository support or unattended scheduling.
- The recorded examples were operated by the project developer using one GitHub
  account and separate wallets. The standalone agent runner has fixture coverage;
  its separate machine-account workflow still needs a live test.
- Browser wallet support has partial integration coverage. See the
  [wallet compatibility notes](WALLET_ONBOARDING.md).
- NEAR AI TEE attestation is not implemented. Public receipt verification
  confirms recorded signatures and current key membership, not historical
  challenge use, model reasoning or code authorship.

## References

- [NEP-413 message signing](https://github.com/near/NEPs/blob/master/neps/nep-0413.md)
- [GitHub workflow runs API](https://docs.github.com/en/rest/actions/workflow-runs)
- [GitHub Actions security](https://docs.github.com/en/actions/reference/security/secure-use)
- [NEAR AI verification](https://docs.near.ai/cloud/verification)
