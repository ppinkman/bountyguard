# Single-bounty agent demo

This runner is for one explicit BountyGuard testnet task. The project operator
prepares a GitHub machine account and separate testnet wallet. A successful demo
would show separate credentials and automated execution under the same project
operator. The previously published [walkthrough](AGENT_WALKTHROUGH.md) records a
different run in a development session. A fixture test does not establish a new
live payment.

## Responsibilities

| Role | Work |
| --- | --- |
| Maintainer | Publish the Issue, create the bounty, assign the verified claim, fund it with testnet tokens, review and merge the PR, and trigger settlement |
| Agent | Read one bounty, bind a testnet identity, claim, wait for funding, ask the coding model for file changes, run isolated tests, publish one fork PR, submit it via MCP, wait for trusted CI, request review, and read the final receipt |
| NEAR contract | Enforce the existing escrow terms and the recorded delivery and review hashes |

Use the planned Issue about showing full terms in the stdout of
`tools/agent_client.py get`. Allow that file and one new regression test such as
`tests/test_agent_get_terms.py`. Pin the maintained repository's current CI and
set `tools/` as an accepted source path. Preserve the original `--output` behavior.
Publish the baseline containing the revision-binding job before creating the
demo bounty. The bounty pins the workflow blob at creation. Sync the machine
fork to that baseline as well. Keep `Python checks` and `Contract checks` as
the required CI names.

## Prepare the machine account

1. Create the machine account and a same-name public fork. Verify the fork is
   current and owned by that account. The Agent uses only
   `BOUNTYGUARD_AGENT_GITHUB_TOKEN`. The credential must read the public upstream,
   write the machine fork, and create a pull request on upstream. A fine-grained
   token restricted to the fork may fail the last operation because GitHub
   limits contributions to public repositories the actor does not belong to.
   Confirm that permission before funding. Keep the maintainer token separate.
   A first-time contributor's fork workflow may also require GitHub approval.
   See [GitHub token limitations](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens#fine-grained-personal-access-tokens)
   and [fork run approvals](https://docs.github.com/en/actions/managing-workflow-runs/approving-workflow-runs-from-public-forks).
2. Prepare a named `.testnet` account. The optional key command below generates a
   local key and prints its public key. Add that public key to the existing
   testnet account as a FullAccess key using your own wallet setup. The runner
   only uses it for NEP-413, and the current service verifies on-chain key
   membership. An existing 32-byte base64 seed can instead be supplied via
   `BOUNTYGUARD_AGENT_SEED`. Keep key files in an ignored directory. On Windows,
   set private file permissions using Windows ACLs or inject the seed through
   your secret manager.
3. In a separate Agent shell, configure `BOUNTYGUARD_CODING_API_KEY` for NEAR AI
   Cloud coding. It goes to the model HTTP endpoint. The model receives the Issue
   and the approved public source files and returns proposed file contents. The
   service's NEAR AI reviewer is a separate call and credential. The Agent
   rejects shells containing the usual maintainer and reviewer credentials.
4. Build the trusted Linux Docker image once and run the isolation test below.
   The build context contains only the dependency lists and Dockerfile. During a
   run, the container has a read-only checkout, a temporary filesystem, no
   network, and no key directory or host socket. Docker must run locally in
   Linux container mode. Use an image you built and inspected. The runner fails
   before claiming if the image preflight fails.
   The repository's push workflow also builds the image and runs the isolation
   probe on a GitHub-hosted Linux runner. That probe verifies the test setup
   independently of the workstation used for the live Agent.

### Bash

Run these from the repository root with the Python environment installed.

```bash
source .venv/bin/activate
mkdir -p -m 700 data/agent
python -m tools.agent_wallet data/agent/machine-key.json
build_dir=$(mktemp -d)
cp requirements.txt requirements-dev.txt tools/agent-demo.Dockerfile "$build_dir/"
docker build -t bountyguard-demo-tests -f "$build_dir/agent-demo.Dockerfile" "$build_dir"
image_id=$(docker image inspect bountyguard-demo-tests --format '{{.Id}}')
BOUNTYGUARD_TEST_IMAGE="$image_id" python -m unittest discover -s tests -p test_secret_isolation.py
python -m tools.agent_demo "$bounty_id" --dry-run
```

After the agreed GitHub and testnet approvals, run from the Agent shell with the
machine credentials loaded. The separate maintainer terminal is required for the
settlement command.

```bash
python -m tools.agent_demo "$bounty_id" --execute --login "$agent_login" \
  --account "$agent_account" --key-file data/agent/machine-key.json --image "$image_id" \
  --allow-file tools/agent_client.py --allow-file tests/test_agent_get_terms.py
python -m tools.maintainer_settle --bounty "$bounty_id" --expect-head "$reviewed_head"
```

### PowerShell

```powershell
New-Item -ItemType Directory -Force data/agent | Out-Null
.venv/Scripts/python -m tools.agent_wallet data/agent/machine-key.json
$buildDir = (New-Item -ItemType Directory -Path (Join-Path ([IO.Path]::GetTempPath()) ([Guid]::NewGuid().ToString()))).FullName
Copy-Item requirements.txt,requirements-dev.txt,tools/agent-demo.Dockerfile -Destination $buildDir
docker build -t bountyguard-demo-tests -f (Join-Path $buildDir agent-demo.Dockerfile) $buildDir
$imageId = docker image inspect bountyguard-demo-tests --format '{{.Id}}'
$env:BOUNTYGUARD_TEST_IMAGE = $imageId
.venv/Scripts/python -m unittest discover -s tests -p test_secret_isolation.py
Remove-Item Env:BOUNTYGUARD_TEST_IMAGE
.venv/Scripts/python -m tools.agent_demo $bountyId --dry-run
```

```powershell
.venv/Scripts/python -m tools.agent_demo $bountyId --execute --login $agentLogin `
  --account $agentAccount --key-file data/agent/machine-key.json --image $imageId `
  --allow-file tools/agent_client.py --allow-file tests/test_agent_get_terms.py
.venv/Scripts/python -m tools.maintainer_settle --bounty $bountyId --expect-head $reviewedHead
```

The settlement terminal uses `BOUNTYGUARD_MAINTAINER_GITHUB_TOKEN`. It displays
the reviewed and current heads, checks for a merge and asks you to type `yes`.
Use one settlement operator and leave the automatic settlement page closed
while using this terminal. The API performs its existing server-side recheck
before signing. The CLI precheck is local and is not an atomic expected-head
parameter on the existing API.

## Limits, recovery, and evidence

- The runner operates on one named testnet bounty and pins the GitHub base. The
  default reward cap is 0.005 tNEAR. The model ID and limits are configurable.
  Defaults are two coding requests, up to 4,096 generated tokens each, and a
  conservative catalog estimate of at most 0.02 USD of existing credits per
  coding request. The reviewer uses its separate service limit. The wait
  deadline defaults to 30 minutes, with independent per-operation timeouts.
- Dry run reads and prints the bounty via MCP. It writes no journal and sends
  no model request. Execute mode can create one branch in the machine fork and
  one upstream PR. It rejects edits outside the exact approved paths, checks
  candidate files for credential patterns, and keeps raw test output out of logs.
- After interruption, repeat the same command and arguments. The runner reads
  the observed claim, branch, and PR before taking another action. A pending
  model request or unresolved PR creation requires operator inspection. After a
  hard crash, remove the empty `data/agent/<bounty-id>.lock` directory only after
  confirming no runner is still active. Leave the checkpoint intact. If
  GitHub omits the PR association for a fork, the verifier can use the pinned
  workflow's revision-binding job. Its GitHub-generated name carries the PR
  number and base SHA. The job must belong to the same Actions run and attempt,
  point to the same fork head, and be backed by the same pinned workflow file
  on both sides. The job has no checkout step or repository permissions. The
  required test jobs must also pass. With neither form of association, the
  runner records `ci_association_missing` and stops before requesting review.
  An [open fork PR](https://github.com/astral-sh/ruff/pull/30069) with a
  [successful run](https://github.com/astral-sh/ruff/actions/runs/42055654929)
  exhibited the missing association in the public API. The BountyGuard fork
  path still needs its own live run.
- The private checkpoint is under `data/agent/`. After a confirmed receipt the
  runner writes a separate sanitized evidence record there. Review that file
  before copying it into `deployments/`. Only record a live run after it happens.
  Public verification checks the PR revision, its recorded CI attempt and the
  final on-chain payment. Runner events, model authorship and operator roles are
  disclosed from local records.

```bash
python tools/verify_acceptance.py --receipt "$receipt_file"
```

```powershell
.venv/Scripts/python tools/verify_acceptance.py --receipt $receiptFile
```
