# Attribution and third-party components

BountyGuard is licensed under the MIT License. See [LICENSE](LICENSE).

NEAR V0 transaction serialization and Windows CurrentUser DPAPI handling in
`bountyguard/near.py`, and the optional Windows Rust test-tool setup in
`tools/contract.py`, are adapted from ProofPay (MIT, Copyright 2026 ProofPay
contributors). Its copyright and permission notice are retained in LICENSE.

The browser wallet bundle includes HOT Labs' `@hot-labs/near-connect` 0.12.0
(MIT). Build tooling uses esbuild 0.28.2. Versions and integrity values are
recorded in `package-lock.json`. The build adds CSP nonces at two stylesheet
insertion points; see `tools/build_wallet.mjs`.

Meteor and Intear wallet executors are hosted by their authors and retain their
own licensing. They are not redistributed as BountyGuard source.
