# BountyGuard development status

Updated November 5, 2026 (Asia/Shanghai).

## Completed and observed

- Public repository: https://github.com/ppinkman/bountyguard. GitHub-hosted
  Python and Rust checks passed for the reviewed PR; Actions are restricted to
  GitHub-owned actions. No workflow receives wallet signing secrets.
- 84 Python tests, 6 JavaScript wallet tests and 9 native Rust tests passed locally. The Rust contract was
  built to WASM, deployed to a separate testnet account, and its live code hash
  independently matched the recorded deployment.
- A real assigned bounty completed: Issue #1, contributor identity/wallet proofs,
  funding, PR #3, exact-revision CI and NEAR AI review, maintainer merge, then
  0.005 tNEAR payment. A separate expired bounty returned 0.005 tNEAR principal.
  Both transfers have public receipts in `deployments/live-acceptance.json`.
- The controlled adversarial PR #4 had successful CI but failed protected-path
  and manipulation-signal checks. It was closed without merging or payment.
- Pushing a new revision after review caused REVISION_CHANGED. The probe remains
  on `codex/toctou-probe`; the PR was restored to the exact reviewed revision,
  retested, reviewed from cache and merged.
- Real MCP stdio clients exercised tool listing, denial of unauthorized writes,
  authenticated review and exact-revision model-cache reuse.
- A subsequent coding-agent run completed Issue #5 / PR #6. Codex used real MCP
  calls to read, claim, submit, review and obtain a 0.005 tNEAR paid receipt. It
  implemented the session-expiry fix between claim and submission; seven new
  regression tests failed before and passed after the fix. Maintainer assignment,
  funding and merge were separate authorized operator actions. This is a coding
  assistant session, not an unattended agent runtime or independent adopter.
- Repeated settlement/refund requests returned the original receipts. The chain
  journal contains two funding intents, one review recording, one payment and
  one refund, all confirmed. No extra transfer was created by replay checks.
  After the separate agent run: three funding intents, two review recordings,
  two payments and one refund, all confirmed. Repeating the new settlement also
  returned its original receipt. Default limits remain 2/3; this run explicitly
  used limits of 3 funding intents and 4 rolling-day model intents in the same DB.
- Three actual NEAR AI requests reported 25,190 tokens total: public Flask PR
  read-only inspection (2,952), a rejected invalid-grounding response (6,129),
  and an accepted evidence-ID review (16,109). Invalid output was retained and
  never silently replaced by a fabricated approval or automatically retried.
  The later PR #6 review used 5,862 tokens, passed, and brought the record to
  four model requests / 31,052 tokens. No recharge or mainnet transaction occurred.

## What this evidence means

The demonstration uses real GitHub APIs, hosted CI, NEAR AI and NEAR testnet,
not generated transaction fixtures. Both GitHub roles nevertheless use the same
project operator, with distinct verified test wallets. It proves controlled
integration behavior; it does not establish independent users, production
security, model correctness, provider billing, or a probability of winning.

The chain records maintainer attestations of off-chain evidence. It cannot read
GitHub or judge code. Merge remains the maintainer's acceptance action. Refunds
require an explicit caller, return principal only, and do not return storage/gas.

## Remaining product and submission work

- Browser wallet connection and NEP-413 signing are implemented with a pinned
  NEAR Connect bundle. The real Intear chooser/cancellation and local GitHub login
  were inspected. A complete real-owner wallet signature is still unverified;
  Meteor is untested, and the current OKX adapter has no testnet declaration.
  Hosted GitHub OAuth is not implemented. The app remains loopback-only, with
  local/own-token login and advanced signed-proof import available.
- Browser polling requires an open page and a live maintainer session. There is
  no unattended keeper or independent dispute resolution.
- No outside contributor or customer acceptance has been demonstrated.
- Video, social post, deployment hosting and formal competition submission remain
  separate work. The user has deferred video; nothing has been formally submitted.
- ProofPay is preserved separately as an earlier prototype; choose one final
  submission rather than presenting shared components as two independent entries.

Public evidence can be checked with `python tools/verify_acceptance.py` without
a model request, signer vault or transaction. Unit adapters are explicitly
fixtures; they are not included as claims of external adoption.
Use `--receipt deployments/agent-acceptance.json` to include the later coding-agent
run. See `docs/AGENT_WALKTHROUGH.md` for the exact role boundary and sequence.
