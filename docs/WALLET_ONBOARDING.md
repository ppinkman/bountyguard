# Browser wallet identity binding

The page now uses `@hot-labs/near-connect` 0.12.0 to connect a named testnet
account and request a NEP-413 identity signature. It does **not** request a
transaction, deploy a contract, add an access key or replace the server's
development transaction signer.

## Try the connection

1. Start the app and open http://127.0.0.1:8766/. Use local GitHub login when
   explicitly enabled, or expand the advanced token option for your own identity.
2. Choose Meteor or Intear, then click **Connect wallet**. These two adapters
   declare testnet and message-signing support in the upstream manifest. The
   current OKX adapter does not declare testnet support and is not offered here.
3. In your wallet, choose a named `.testnet` account you control. Complete any
   account setup yourself; do not share a seed phrase or private key with this app.
4. Select an unassigned draft bounty, choose Contributor or Maintainer, then
   click **Sign & bind account**. Read and approve the exact task/role/account
   message in the wallet. This message signature does not transfer funds.
5. The backend verifies the signature, single-use challenge and current
   FullAccess-key membership. Only after a contributor binding is recorded does
   **Request this assignment** become available. Assignment and funding remain
   maintainer actions. A recorded identity proof does not by itself move money.

On the project development machine, Issue #7 has an **unfunded** draft for trying
this flow. It has no bound wallet, claim, funding or model result at the time of
the UI check. This is an identity-entry test, not another paid demonstration.
Its terms pin the workflow at creation; do not fund this UI-only draft after
changing the workflow without reviewing/recreating its terms.

Advanced challenge download and signed-proof import remain available. Wallet
private keys are neither requested nor accepted by the API. A previously bound
account cannot be silently changed; use a new draft for a different recipient.

## Observed versus still unverified

Observed in the actual browser on November 5, 2026:

- Local GitHub login verified numeric GitHub user 100271001.
- The real Intear wallet connection frame loaded its Web/App choices.
- Cancelling returned to the page without a bound account or claim.
- English/Chinese labels, disabled unverified claim controls and the draft
  details were inspected. Existing paid/refunded orders remained visible.

No compatible personal testnet wallet was connected or used to sign during this
check. **A complete real-wallet signature round trip remains unverified.** Meteor
was offered based on upstream capabilities but its connection was not exercised.
Browser adapters can depend on wallet-host availability and pop-up settings.
The deterministic client tests use labelled adapters; backend tests verify actual
Ed25519 signatures against explicit RPC fixtures. Neither proves compatibility
with an untested wallet version or a real owner's account.

## Build and dependency boundary

The generated local bundle is committed so Python users do not need Node to run
the page. To rebuild and test it:

```sh
npm ci --ignore-scripts --no-fund
npm test
npm run build
```

`package-lock.json` pins the connector and esbuild. `tools/build_wallet.mjs`
adds CSP nonces to the connector's parent stylesheet and iframe stylesheet at
build time; it fails if the expected upstream insertion points change. The
backend generates a fresh nonce per HTML response. Inline script/eval permission
is not globally enabled. Wallet frames are allowed only for the selected wallet
hosts; connector network sources are explicitly listed in the page policy.

The two wallet executors are fetched from the wallet authors' upstream URLs and
run in the connector's sandbox. They are not bundled, redistributed or claimed
to be immutable here. The curated manifest records those URLs and declared
capabilities; future wallet updates remain an external dependency. The connector
selection UI is implemented by BountyGuard; no custom/debug-wallet option is
exposed. Server signature and account ownership checks remain authoritative.

Sources: [connector package](https://www.npmjs.com/package/@hot-labs/near-connect),
[upstream repository](https://github.com/hot-dao/near-selector),
[wallet manifest](https://github.com/hot-dao/near-selector/blob/main/repository/manifest.json).
