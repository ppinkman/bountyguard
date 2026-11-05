import { NearConnector } from '@hot-labs/near-connect';
import { supportedWallet, testnetAccount, signChallenge, sameBindingContext } from './wallet-core.mjs';

let connector, connectedWallet = null, connectedAccount = null;
const ready = (async () => {
  const response = await fetch('/assets/wallet-manifest.json');
  if (!response.ok) throw new Error('Wallet options could not be loaded.');
  const manifest = await response.json();
  connector = new NearConnector({ network: 'testnet', features: { testnet: true, signMessage: true }, autoConnect: false, manifest, cspNonce: document.querySelector('meta[name="bg-csp-nonce"]').content });
  connector.on('wallet:signOut', () => {
    connectedWallet = null; connectedAccount = null;
    window.dispatchEvent(new CustomEvent('bg-wallet-change', { detail: null }));
  });
  await connector.whenManifestLoaded;
  return manifest.wallets;
})();
// Report availability without connecting, signing or adding an access key.
window.BountyGuardWallet = {
  matchesContext: sameBindingContext,
  async options() { return (await ready).filter(item => item.features?.testnet && item.features?.signMessage).map(item => ({ id: item.id, name: item.name })); },
  async connect(walletId) {
    const options = await this.options();
    if (!options.some(item => item.id === walletId)) throw new Error('This wallet is not enabled for testnet signing.');
    const wallet = await connector.connect({ walletId });
    if (!supportedWallet(wallet)) throw new Error('The wallet does not declare testnet message signing support.');
    const accounts = await wallet.getAccounts({ network: 'testnet' });
    const account = accounts.find(item => testnetAccount(item.accountId));
    if (!account) throw new Error('Choose a named .testnet account in your wallet.');
    connectedWallet = wallet; connectedAccount = account.accountId;
    window.dispatchEvent(new CustomEvent('bg-wallet-change', { detail: { account: connectedAccount, wallet: wallet.manifest.name } }));
    return { account: connectedAccount, wallet: wallet.manifest.name };
  },
  async disconnect() { if (connector && connectedWallet) await connector.disconnect(connectedWallet); connectedWallet = null; connectedAccount = null; },
  async sign(challenge, expected) {
    if (!connectedWallet || !connectedAccount) throw new Error('Connect a testnet wallet first.');
    const accounts = await connectedWallet.getAccounts({ network: 'testnet' });
    if (!accounts.some(item => item.accountId === connectedAccount)) throw new Error('Wallet account changed. Reconnect before signing.');
    return signChallenge(connectedWallet, connectedAccount, challenge, expected);
  },
};
ready.catch(() => {});
