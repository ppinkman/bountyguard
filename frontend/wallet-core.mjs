export function testnetAccount(account) {
  return typeof account === 'string' && account.length <= 64 && /^[a-z0-9]+(?:[._-][a-z0-9]+)*\.testnet$/.test(account);
}

export function supportedWallet(wallet) {
  return wallet?.manifest?.features?.testnet === true && wallet.manifest.features.signMessage === true;
}

export async function signChallenge(wallet, account, challenge, expected) {
  if (!supportedWallet(wallet) || !testnetAccount(account)) throw new Error('Choose a testnet account in a wallet supporting NEP-413.');
  if (challenge.near_account_id !== account || challenge.callback_url != null || challenge.recipient !== 'bountyguard.local') throw new Error('The signing request does not match this connected account.');
  if (!Number.isInteger(challenge.expires_at) || challenge.expires_at * 1000 <= Date.now()) throw new Error('The signing request expired. Start again.');
  const context = JSON.parse(challenge.message);
  if (!expected || context.bounty_id !== expected.id || context.terms_hash !== expected.terms_hash || context.github_user_id !== expected.github_user_id || context.purpose !== expected.purpose || account !== expected.account) throw new Error('The signing request differs from the task you selected.');
  if (context.application !== 'BountyGuard' || context.network !== 'testnet' || context.near_account_id !== account || context.bounty_id !== challenge.bounty_id || context.purpose !== challenge.purpose || context.github_user_id !== challenge.github_user_id || context.challenge_id !== challenge.id || context.expires_at !== challenge.expires_at) throw new Error('The signing request context is inconsistent.');
  const nonce = Uint8Array.from(atob(challenge.nonce), char => char.charCodeAt(0));
  if (nonce.length !== 32) throw new Error('Invalid signing nonce.');
  const result = await wallet.signMessage({ message: challenge.message, recipient: challenge.recipient, nonce, network: 'testnet', signerId: account });
  if (!result || result.accountId !== account || typeof result.publicKey !== 'string' || !result.publicKey.startsWith('ed25519:') || typeof result.signature !== 'string' || !result.signature) throw new Error('The wallet returned a signature for a different account or key type.');
  if (challenge.expires_at * 1000 <= Date.now()) throw new Error('The signing request expired while awaiting wallet approval.');
  return { challenge_id: challenge.id, public_key: result.publicKey, signature: result.signature };
}

export function sameBindingContext(before, after) {
  return !!before && !!after && before.id === after.id && before.terms_hash === after.terms_hash && before.github_user_id === after.github_user_id && before.account === after.account && before.purpose === after.purpose;
}
