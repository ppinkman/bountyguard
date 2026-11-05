# BountyGuard development status

Updated November 5, 2026 (Asia/Shanghai).

## Implemented locally

- Independent Python package/database, loopback API, English-first bilingual web
  board, and five MCP tools. GitHub tokens stay in session memory; cookies are
  HttpOnly/SameSite and cookie mutations require a session confirmation token.
- Assigned-bounty terms, numeric GitHub identities, NEP-413 nonces, current
  FullAccess ownership check, fixed recipient, repository permission check.
- Version-bound PR/Issue/workflow/run/job/check verification; immutable review
  records, bounded model review with code-quote grounding, no paid unknown retry.
- New Rust testnet contract with assigned GitHub references, evidence-bound
  maintainer payment, callback nonces, failed-transfer restoration and expiry.
- Separate encrypted development signer and original-transaction reconciliation.
- Windows startup helpers, public-PR inspection and testnet setup/deployment tools.

## Observed evidence so far

- 49 Python tests passed locally: identity, replay, author, changed revision,
  trusted CI, protected changes, model controls, API auth and duplicate payment.
  Unit adapters are explicit fixtures, not external customers or chain proof.
- New contract compiled to WASM. Native Rust tests are being validated separately;
  no hosted CI result is claimed until GitHub actually runs it.
- Read the existing public Flask PR #6176 through GitHub: one complete changed
  file at head `bfc8f983871dcadf0492578d9ab72d951b34c19c`.
- One actual NEAR AI review returned PASS, reporting 2,681 prompt + 271 completion
  tokens (2,952 total). This was read-only inspection of that public PR, not a
  funded bounty, linked-Issue acceptance or proof that Flask endorses this app.

## Remaining before an end-to-end demo

- Verify account/faucet, contract deployment and its code hash; record actual
  funding/payment/refund evidence separately from unit fixtures.
- Publish a reviewed demonstration repository only after publication is approved;
  create a controlled Issue/PR/CI demonstration and disclose project ownership.
- Exercise the complete authenticated browser/MCP journey. Wallet extensions and
  hosted OAuth are not implemented; local NEP-413 proof import is the current path.
- Clean-environment hosted CI, original-transaction recovery acceptance and final
  submission/demo materials remain required. No public repository/submission or
  independent commercial use is claimed.
