# Setup and configuration

Install Python 3.11+ and follow the local startup commands in the
[README](../README.md). The API listens on loopback at port 8766. Node.js is
needed only to rebuild the committed wallet bundle; Rust is needed to build or
test the contract.

## GitHub login

The application verifies tokens with GitHub's `GET /user`. Tokens stay in
server memory for a one-hour session. Maintainers need write, maintain or admin
permission on the public repository. Contributors submit PRs as their own
authenticated GitHub identity.

On Windows, the development launcher can use an existing GitHub CLI login:

```powershell
.\start_dev.ps1 -UseGitHubLogin
```

Alternatively, use **Advanced: use your GitHub token** in the interface. Keep
credentials out of source control. This release does not support private
repositories or hosted OAuth.

## NEAR AI review

Set `NEAR_AI_API_KEY` in the launching process, then enable review:

```powershell
.\start_dev.ps1 -UseGitHubLogin -UseExistingAiCredits
```

`-AiKeyFile` optionally selects a Windows CurrentUser DPAPI-encrypted provider
key file instead of an environment variable. The launcher restores the previous
process environment on exit. `-DirectNetwork` disables inherited proxies for
the application process when a direct connection is needed.

Model requests send public Issue text and code patches to NEAR AI. The default
limit is three requests per rolling 24 hours. Each request must pass a catalog
price estimate of at most $0.02. This estimate is not a provider billing cap.
An uncertain or invalid response is retained without an automatic paid retry.

## Testnet deployment

The current transaction signer uses Windows DPAPI. Public verification and the
application's read-only features work on other platforms.

```powershell
# Create accounts and save their keys encrypted locally.
.venv/Scripts/python tools/setup_testnet.py create-free-accounts
# Requires Rust and the wasm32-unknown-unknown target.
.venv/Scripts/python tools/contract.py build
.venv/Scripts/python tools/setup_testnet.py deploy
.\start_dev.ps1 -UseGitHubLogin -UseExistingAiCredits -EnableTestnet
```

Deployment state and encrypted keys are stored under the ignored `data/testnet/`
directory. Browser wallet signatures establish identity; funding and settlement
use this configured local signer. See [wallet setup](WALLET_ONBOARDING.md).

| Setting | Default |
| --- | --- |
| Network | Named `.testnet` accounts |
| Maximum reward | 0.01 tNEAR per bounty |
| Storage charge | 0.01 tNEAR per funded bounty, plus transaction gas |
| Funding attempts | 2, tracked in the persistent journal |
| Model requests | 3 per rolling 24 hours |
| Model price estimate | At most $0.02 per request |

The launcher accepts `-FundingIntentLimit` from 2 to 4 and `-ModelIntentLimit`
from 3 to 6. Existing usage persists across restarts and configuration changes.
If a transaction result is unknown, reconcile its original operation ID in the
interface instead of creating a replacement transaction.

Refunds return the bounty principal after expiry. Storage charges, spent gas
and model usage are separate costs. Expiry requires an explicit refund call.

## MCP service

Start the web/API service before starting the MCP stdio server:

```bash
python -m bountyguard.mcp_server
```

`GITHUB_TOKEN` identifies the participant. Writes require
`BOUNTYGUARD_MCP_ALLOW_WRITES=1`. Model use also requires
`BOUNTYGUARD_MCP_ALLOW_MODEL=1` and an enabled backend model configuration.
MCP exposes bounty lookup, assignment requests, PR submission and review.
Funding and payment use the maintainer's web/API flow.

See the [MCP walkthrough](AGENT_WALKTHROUGH.md) for CLI examples and the
[agent runner](AGENT_DEMO.md) for isolated coding and PR creation.
