# Official prompt review and development priorities

Reviewed November 5, 2026 (Asia/Shanghai), after the first live demonstration.
This is an implementation assessment, not an organizer-issued score or prize forecast.

## Sources read

The following official files were read in full, not only their search snippets:

| Source | GitHub file blob SHA at review |
| --- | --- |
| [README](https://github.com/nearai/near-hackathon-prompt-examples/blob/main/README.md) | `3d4da8a4ed597ba6d2073642c135a8e7cf296741` |
| [Setup](https://github.com/nearai/near-hackathon-prompt-examples/blob/main/00-setup.md) | `b2ac768d67b75044678357754a8bd90cb6cca26a` |
| [Agent Economy](https://github.com/nearai/near-hackathon-prompt-examples/blob/main/tracks/07-agents.md) | `306bb48c66dd49693c219dfb89baab052b94c155` |
| [AI Security & Defense](https://github.com/nearai/near-hackathon-prompt-examples/blob/main/tracks/06-security.md) | `02c9d0618b8e446bab20576b38c55f62293f8557` |
| [Autonomous Business](https://github.com/nearai/near-hackathon-prompt-examples/blob/main/tracks/04-business.md) | `c6fb90837210c2d5b1981718e465975f71ab717f` |
| [Submission checklist](https://github.com/nearai/near-hackathon-prompt-examples/blob/main/SUBMITTING.md) | `de6070e60d81459a012dd63358d772fb68b70a47` |

Also read the live [HACKATHON.md](https://nearhackathon.com/HACKATHON.md)
and [access-key documentation](https://docs.near.org/protocol/accounts-contracts/access-keys).
File hashes identify the reviewed content; they are blob hashes, not commit IDs.
Reading the setup prompt does not mean its skill-install command was run.

## Rules versus examples

Q-010 allows testnet-only entries. Q-011 and the Tracks section explicitly make
suggested integrations and starter prompts optional. BountyGuard does not need
to become the example contractor, counterparty scoring service or research shop.
There is no published basis here for claiming negotiation, Intents or Agent Market
are universally mandatory, or that their presence guarantees additional points.

The starter submission checklist says one entry per team and no direct edits.
The live rule is more specific: Q-015 allows at most two independent, disclosed
projects per person, one submission per project. Saved mistakes use a manually
reviewed change request, not a second submission. Our current plan remains one
final project, with ProofPay disclosed as the earlier prototype.

Q-012 requires a video for a local-only demo. Screenshots alone do not complete
that requirement. Video remains deferred at the user's request, not waived.
The deadline is November 15, 2026, 07:59 in Asia/Shanghai. Formal submission and
social publication remain separate user-approved actions.

## Fit and actual gaps

| Track | Starter emphasis | BountyGuard evidence | Remaining gap / interpretation |
| --- | --- | --- | --- |
| `agents` | Agents earn/spend, hire, verify work, keep budgets and receipts; contractor example includes one counteroffer | Verified claimant, real PR, trusted CI, NEAR AI review, MCP adapter, fixed reward and testnet payment | A reproducible coding-agent journey through claim, code, PR and receipt is still needed. Existing MCP evidence proves cached review, not that entire journey through MCP. Negotiation and Market integration are absent and are not claimed. |
| `security` | Bounded signing, refusal on block, human involvement on warning, injected-payment attack evidence | Fixed recipient/terms, protected-path checks, revision invalidation, bad-PR rejection, contract callback safeguards | Development signer still uses FullAccess. Encryption and Python allowlists do not restrict its on-chain authority. Existing malicious-PR rejection is not proof of a scoped wallet stopping an arbitrary-recipient signing attempt. |
| `business` | Autonomous treasury/sales/costs/payouts, configurable limits and kill switch | Bounty terms, persistent operation journal and payouts | No autonomous sales/revenue loop or configurable operating business. Currently a weaker fit; do not claim an autonomous company. |

Track-fit judgments above are our interpretation of the published material.
Recommended development focus: `agents` and `security`; revisit final track
selection only against the completed implementation.

## Key custody: two different operations

1. **Identity proof:** the current NEP-413 flow requires a signature from a
   FullAccess key currently registered on the claimed account. The server receives
   the signature and public key, not the user's private key. That is an identity
   policy; it does not require handing the agent a FullAccess transaction key.
2. **Transaction authority:** the local testnet signer decrypts a separate
   maintainer FullAccess key and signs chain calls. DPAPI protects storage, while
   the application allowlist and deposit checks constrain normal application
   execution. They do not prevent a compromised signer from bypassing that code.

NEAR function-call keys are scoped to a receiver and optionally methods/gas, but
cannot attach NEAR. Current `fund_assigned` attaches reward/storage, and `pay`
requires one yocto. Therefore replacing the key alone will not work. Do not
remove the one-yocto check or weaken the deployed contract just to fit a prompt.

A future delegated settlement design needs explicit contract authorization and
zero-deposit agent calls against pre-funded, fixed terms, with revocation and
limits enforced by the contract. Evaluate it as a separate version/deployment,
preserving existing contract state, journals and public receipts. No such scoped
settlement design has been implemented or verified yet.

## Next development order and acceptance evidence

1. **Make the judge path easy to reproduce.** Separate key-free evidence
   verification from creating a fresh bounty. Include Linux/macOS startup and
   numbered actions with observable expected results. Never ship development
   credentials or replayable personal login sessions.
2. **Demonstrate one coding agent earning the reward.** Record an actual agent
   reading assigned terms, changing implementation, submitting a real PR and
   obtaining the final receipt. Keep maintainer assignment, merge and funding
   consent explicit. Report every remaining manual step, rather than describing
   the current adapter as an autonomous contractor.
3. **Reduce settlement-key authority.** First document the authorization design;
   then test a separate delegated path if it can preserve the existing contract's
   guarantees. Acceptance includes an unauthorized receiver/method attempt being
   rejected by the chain permission or contract, not only by a Python check.
4. **Remove the onboarding obstacle.** Add wallet-extension signing and usable
   GitHub login so another person can try the flow without the project operator's
   local vaults. Do not advertise wallet compatibility before an actual test.
5. **Complete submission materials.** Video after the user resumes that work,
   public demo post, final track selection and confirmed submission payload.

Do not add a local counteroffer simulator, a dry quote badge or a fabricated
external participant to imply requirements have been met. The existing journal's
two funding intents and three model intents remain unchanged by this review;
new funded/model scenarios require respecting their actual configured limits.
