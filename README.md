# BountyGuard

GitHub bounty payments on NEAR. Assign a contributor to an Issue, fund a bounty,
and review their pull request. BountyGuard releases payment through NEAR escrow
after the maintainer merges the reviewed code.

**[View the testnet demo](https://ppinkman.github.io/bountyguard/)** ·
[Coding-agent example](docs/AGENT_WALKTHROUGH.md) ·
[Local setup](docs/SETUP.md)

The demo shows recorded payments, held payments and a refund. It requires no
account or wallet. To create and manage bounties, run the local application.
This release uses NEAR testnet and a local transaction signer.

## How it works

1. **Create a bounty.** Choose an open GitHub Issue, reward, deadline and required
   checks. The application saves these terms as a draft.
2. **Assign and fund.** Both participants verify their GitHub identity and NEAR
   wallet. The maintainer selects a contributor and deposits the reward in escrow.
3. **Review the pull request.** BountyGuard checks the configured GitHub Actions
   workflow and requests an advisory review through NEAR AI. The report records
   the commit and code changes it reviewed.
4. **Merge and pay.** The maintainer merges the accepted change. Before sending
   payment, BountyGuard checks that the merged code matches the review. Changed
   code requires a new review. An expired bounty can be refunded to its maintainer.

Coding agents can read bounties, request assignment, submit a PR and request a
review through MCP. Assignment, funding and merge remain maintainer actions.

## Testnet examples

| Example | Result | Record |
| --- | --- | --- |
| Session recovery fix by Codex, Issue #5 → PR #6 | Paid 0.005 tNEAR after merge | [Walkthrough](docs/AGENT_WALKTHROUGH.md), [payment](https://testnet.nearblocks.io/txns/EHb7dgpu3ZTJdp5edLdPd5fq7yYkr3tkRrdKXR76A6Yg) |
| Accepted fix, PR #3 | Paid 0.005 tNEAR after merge | [PR](https://github.com/ppinkman/bountyguard/pull/3), [payment](https://testnet.nearblocks.io/txns/B35cMBZLzvYjpBVEF24isUd9HAr4tTa596fGv771XYQt) |
| Workflow modification and review-manipulation text, PR #4 | Payment held for review despite passing CI | [Changes](https://github.com/ppinkman/bountyguard/pull/4/files) |
| New commit after review | Previous approval rejected with `REVISION_CHANGED` | [Commit comparison](https://github.com/ppinkman/bountyguard/compare/17e1da79b199fcaf5890ac5f725c501e1b3548f8...c7863c13362c411055d2662c83edcb3d014eb5fd) |
| Expired bounty, Issue #2 | Refunded 0.005 tNEAR principal | [Refund](https://testnet.nearblocks.io/txns/GWtzhGA7PTGgBK8CXLnkkeqV1pKRUedT2xVZ3VZyrDq9) |

These are controlled tests operated by the project developer using one GitHub
account and separate maintainer and contributor wallets. The transactions use
testnet tokens. Raw records are in [deployments](deployments/).

## Run locally

Requires Python 3.11 or later. On Linux or macOS:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
bash start.sh
```

On Windows PowerShell:

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
.\start.ps1
```

Open **http://127.0.0.1:8766/**. The board starts empty and supports English and
Chinese. Startup sends no model requests or transactions. The API is intended
for local use; hosted authentication is not implemented. Testnet transactions
currently require the Windows DPAPI signer. See [setup](docs/SETUP.md) for
GitHub login, model configuration, deployment and limits.

## Verify the examples

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests
python tools/verify_acceptance.py --receipt deployments/agent-acceptance.json
```

The last command reads public GitHub and NEAR testnet data. It checks recorded
wallet signatures, current key membership, PR revisions and payment states;
it requires network access, but no signing key or model request.

`./demo.sh` runs eight focused checks with Python 3.11+ and Bash. Its first run
installs dependencies. See [testing](docs/TESTING.md) for the check map, wallet
tests and contract tests.

## Documentation

- [Setup and configuration](docs/SETUP.md)
- [Wallet connection and signing](docs/WALLET_ONBOARDING.md)
- [MCP usage and recorded coding-agent example](docs/AGENT_WALKTHROUGH.md)
- [Standalone agent runner](docs/AGENT_DEMO.md)
- [Architecture and security boundaries](docs/ARCHITECTURE.md)
- [Tests and evidence verification](docs/TESTING.md)

The contract enforces escrow terms and payment authority. GitHub verification
and AI review happen off-chain, with the maintainer's signer submitting the
result. CI and AI review assist the maintainer; they do not prove code correct.
See the architecture document for trust assumptions and current limitations.

## License

[MIT](LICENSE). Adapted components and third-party dependencies are credited in
[NOTICE.md](NOTICE.md).
