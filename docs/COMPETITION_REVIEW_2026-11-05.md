# Competition snapshot and implications

Checked November 5, 2026, Asia/Shanghai. This is a dated public-directory
observation, not a prediction of judging outcomes. No competitor code or
deployment was executed during this review.

## Reproduced directory counts

Source: the official page's public [project API](https://nearhackathon.com/api/projects?page=1).
All 17 pages were read, using the API's advertised total and page size (8).
There were 131 distinct public project IDs; `preview` was false. The local raw
snapshot is kept in ignored `artifacts/competition-directory-2026-11-05.json`.

| Track | Projects bearing the tag |
| --- | ---: |
| security | 76 |
| agents | 66 |
| realworld | 27 |
| business | 22 |
| defi | 21 |
| privacy | 21 |
| open | 20 |
| thesis | 18 |
| swarms | 9 |
| social | 5 |
| memecoins | 4 |
| nfts | 3 |
| games | 1 |

Projects may select multiple tags. Counts are overlapping, not independent pools.

## Important correction: the first tag is not a preference

The official submission form normalizes selected tracks into the published
track order before sending the payload. This was observed in the public page
bundle `/_next/static/chunks/app/page-2d0fc5973b074b22.js` on November 5.
Every one of the 131 public track arrays followed that canonical order:
defi, thesis, privacy, business, swarms, security, agents, realworld, games,
nfts, memecoins, social, open.

Counting first elements does yield 5 for realworld and 13 for business. Those
numbers cannot be described as the number of entrants choosing them as a
primary track. The public API has no primary-track field. Lower-order tags
appear first whenever a team also selected a later tag. Award selection should
not be inferred from these array positions.

The reported general tooling popularity and distribution of discussion between
X, Reddit and forums were not independently quantified in this review.

## Nearby projects: existence verified, feature claims attributed

These names and demo-post links are in the official directory. Their public
repositories were found separately; README features below are the authors'
descriptions, not independently reproduced results or an endorsement.

| Project and README | What its README describes | Why it matters |
| --- | --- | --- |
| [Patch Fund](https://github.com/emilhuseyn/patch-fund) | GitHub security-fix bounties, verified merges, Sputnik DAO payouts, earned contributor limits, challenge/veto/pause and testnet examples | Direct overlap with paying contributors after merged fixes. GitHub bounty settlement is not an empty niche. |
| [Proof of Ship on NEAR](https://github.com/hey-research-lab/proof-of-ship-near) | Signed shipping-count attestations, USDC escrow, testnet claim receipts and a mainnet deployment | Evidence-based builder rewards already have another implementation and an existing ecosystem narrative. |
| [MilestonePay](https://github.com/kickenad/milestonepay-near) | Stablecoin milestone payments, wallet connection, timeout claims and optional dispute splitting | Moving the label to contractor payments would not by itself create differentiation. |

README blob hashes read: Patch Fund `47f323f2266ec881058901811d315c2eb0bbf380`,
Proof of Ship `893a9b50909bb6a62f4bb014683770c4602e3a2f`,
MilestonePay `d4084306aaa33ea199dd1b3efa40f5d7f1d663e1`.
No claim is made here that BountyGuard is more secure or feature-complete.

## Consequences for BountyGuard

- A generic spending guard, an extra quote badge or another single-operator
  payment is insufficient evidence of differentiation. There is no defensible
  numerical probability of winning from the current directory.
- Focus the coding-agent journey on the existing exact-revision acceptance
  conditions: verified claimant, trusted CI, grounded advisory review and a
  maintainer merge of the reviewed head. Show the agent completing work as well
  as requesting review. Clearly distinguish the coding agent from the review model.
- Add replayable negative cases alongside success: changed head, wrong claimant,
  changed terms/recipient and untrusted CI. Do not claim these ideas are unique;
  make their behavior and limits easy to inspect.
- Other-person onboarding and an accessible demo are material gaps. Today's
  same-operator/two-wallet evidence is an integration demonstration, not external
  adoption. A wallet import form alone is a substantial obstacle for reviewers.
- Select tracks by implemented behavior. `agents` and `security` currently have
  supporting evidence. `realworld` might fit a completed contributor-payment
  product, but the current testnet prototype is not ready for normal businesses.
  `business` remains weak without autonomous business operations. Adding tags
  solely because their counts are smaller is not a development strategy.

## Rules rechecked

[Live HACKATHON.md](https://nearhackathon.com/HACKATHON.md), Q-007/Q-010/Q-011:
Intents has no testnet, but Intents itself is not mandatory and testnet projects
are eligible. Therefore this report does not justify buying mainnet funds.
Dry quotes and actual mainnet execution must remain clearly distinguished.
Q-012 requires video for a local-only demo. Q-015 allows at most two independent,
disclosed projects per person. Saved submission mistakes use change requests.

## Development state when this review interrupted implementation

The additional MCP agent run has not created an Issue, funded a new bounty or
sent another model request. A bounded development-limit configuration change is
prepared locally, but the running service retains the original 2 funding / 3
model limits. Existing payment/refund evidence and contract state are intact.
Do not describe the planned new agent journey as completed.
