# Wallet connection and identity signing

BountyGuard uses `@hot-labs/near-connect` 0.12.0 to connect a named testnet
account and request a NEP-413 message signature. This establishes wallet
ownership for a bounty. Transactions use the separately configured local
development signer.

## Connect and bind a wallet

1. Start the application and open http://127.0.0.1:8766/. Sign in with GitHub.
2. Choose Meteor or Intear and select **Connect wallet**.
3. Select a named `.testnet` account in the wallet.
4. Open an unassigned bounty draft, choose Contributor or Maintainer, and select
   **Sign & bind account**. Check the bounty, role and account in the message
   before signing. The message signature does not transfer funds.
5. The server checks the signature, single-use challenge and current on-chain
   FullAccess-key membership. Contributors can then select
   **Request this assignment**. The maintainer assigns and funds the bounty.

The app accepts public signed proofs, never wallet private keys. To change the
recipient after binding, create a new draft.

## Import a signed proof

Use **Advanced: import a signed proof** to download a challenge and sign it in
a compatible wallet. A local test wallet can also sign with the CLI:

```powershell
.venv/Scripts/python -m bountyguard sign-challenge challenge.json --vault data/testnet/claimant.dpapi
```

Paste the returned public proof into the form and select **Verify wallet
ownership**. Keep the encrypted vault and private key local.

## Compatibility and test coverage

Both included adapters declare testnet message-signing support. Browser
integration testing on November 5, 2026 confirmed that Intear's connection
chooser loads and cancellation returns to the app. A complete browser-wallet
signature round trip has not been verified. Meteor's connection remains
untested. Wallet availability can also depend on its host and browser settings.

Client tests use wallet adapters with controlled responses. Backend tests verify
Ed25519 signatures against RPC fixtures. These tests cover application behavior
without establishing compatibility with every wallet version.

## Build the wallet bundle

```bash
npm ci --ignore-scripts --no-fund
npm test
npm run build
```

The generated bundle is committed so running the Python application does not
require Node.js. `package-lock.json` pins the connector and esbuild versions.
`tools/build_wallet.mjs` adds CSP nonces to the connector's parent and iframe
stylesheets, failing if their expected insertion points change. The server
generates a fresh nonce per HTML response.

Wallet executors load from the authors' URLs in the connector's sandbox. They
remain external dependencies; the local manifest records their declared
capabilities and URLs. Server-side signature and account checks determine
whether a binding is accepted.

Sources: [connector package](https://www.npmjs.com/package/@hot-labs/near-connect),
[upstream repository](https://github.com/hot-dao/near-selector),
[wallet manifest](https://github.com/hot-dao/near-selector/blob/main/repository/manifest.json).
