# Attribution and project boundary

BountyGuard is a new assigned-GitHub-bounty application. Its GitHub identities,
NEP-413 challenge lifecycle, workflow/run/job verification, revision-bound review,
assigned bounty schema, web interface and Rust bounty contract are implemented here.

The basic NEAR V0 transaction serialization / CurrentUser DPAPI approach in
`bountyguard/near.py`, and optional Windows native Rust test-tool setup in
`tools/contract.py`, are adapted from ProofPay (MIT, Copyright 2026 ProofPay
contributors). That copyright and permission notice are retained in LICENSE.
Common NEAR callback safety patterns are acknowledged; they are not presented as
novel cryptographic techniques.

ProofPay remains at the sibling `ProofPay/` directory as an archived alternative.
The current plan is to choose one final hackathon submission, not claim these as
two unrelated entries. BountyGuard has no runtime Python import from ProofPay.
`start_dev.ps1 -UseExistingAiCredits` can optionally read its existing encrypted
provider key; this is a local convenience, not a portable setup requirement.

The browser wallet bundle includes `@hot-labs/near-connect` 0.12.0, published by
HOT Labs with MIT license metadata. Build tooling uses esbuild 0.28.2. Versions
and registry integrity values are recorded in package-lock.json. The build makes
two documented CSP-nonce additions to the connector's style insertion points.
Meteor/Intear wallet executors remain hosted by their authors and are not
redistributed as BountyGuard source or assigned BountyGuard's MIT license.
