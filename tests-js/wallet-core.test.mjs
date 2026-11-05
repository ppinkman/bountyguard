import test from 'node:test';
import assert from 'node:assert/strict';
import { signChallenge, supportedWallet, testnetAccount, sameBindingContext } from '../frontend/wallet-core.mjs';

function fixture() {
  const expected = { id: 'bounty-one', terms_hash: 'terms-one', github_user_id: 22, account: 'alice.testnet', purpose: 'claimant' };
  const challenge = { id: 'challenge-one', bounty_id: expected.id, near_account_id: expected.account, github_user_id: expected.github_user_id, purpose: expected.purpose, expires_at: Math.floor(Date.now()/1000)+300, recipient: 'bountyguard.local', callback_url: null, nonce: btoa(String.fromCharCode(...new Uint8Array(32).fill(7))) };
  challenge.message = JSON.stringify({ application: 'BountyGuard', network: 'testnet', bounty_id: expected.id, terms_hash: expected.terms_hash, near_account_id: expected.account, github_user_id: expected.github_user_id, purpose: expected.purpose, challenge_id: challenge.id, expires_at: challenge.expires_at });
  const calls = [];
  const wallet = { manifest: { features: { testnet: true, signMessage: true } }, async signMessage(params) { calls.push(params); return { accountId: expected.account, publicKey: 'ed25519:unit-test-public-key', signature: 'unit-test-signature', privateKey: 'never-forward-this-unit-field' }; } };
  return { expected, challenge, wallet, calls };
}

test('only named testnet accounts and declared capabilities are accepted', () => {
  assert.equal(testnetAccount('alice.testnet'), true);
  for (const account of ['alice.near', 'a'.repeat(64), 'ALICE.testnet', 'evil..testnet', 'alice.testnet.evil']) assert.equal(testnetAccount(account), false);
  assert.equal(supportedWallet({ manifest: { features: { signMessage: true } } }), false);
});

test('forwards exact NEP-413 values, requests no transaction, strips extra fields', async () => {
  const { expected, challenge, wallet, calls } = fixture();
  const proof = await signChallenge(wallet, expected.account, challenge, expected);
  assert.equal(calls.length, 1);
  assert.deepEqual([...calls[0].nonce], new Array(32).fill(7));
  assert.equal(calls[0].message, challenge.message);
  assert.equal(calls[0].network, 'testnet');
  assert.equal(calls[0].signerId, expected.account);
  assert.deepEqual(Object.keys(proof).sort(), ['challenge_id', 'public_key', 'signature']);
});

test('mismatched task, terms, actor or role never reaches the wallet', async () => {
  for (const [key, value] of [['id', 'other-bounty'], ['terms_hash', 'other-terms'], ['github_user_id', 33], ['purpose', 'maintainer']]) {
    const { expected, challenge, wallet, calls } = fixture();
    await assert.rejects(signChallenge(wallet, expected.account, challenge, { ...expected, [key]: value }));
    assert.equal(calls.length, 0);
  }
});

test('expired, callback, wrong-account and malformed nonce requests stop before signing', async () => {
  for (const mutate of [c => c.expires_at = 1, c => c.callback_url = 'https://evil.test', c => c.near_account_id = 'mallory.testnet', c => c.nonce = btoa('short')]) {
    const { expected, challenge, wallet, calls } = fixture(); mutate(challenge);
    await assert.rejects(signChallenge(wallet, expected.account, challenge, expected));
    assert.equal(calls.length, 0);
  }
});

test('a different returned account and a rejected wallet prompt cannot become a proof', async () => {
  const { expected, challenge, wallet } = fixture();
  wallet.signMessage = async () => ({ accountId: 'mallory.testnet', publicKey: 'ed25519:unit-test', signature: 'unit-test' });
  await assert.rejects(signChallenge(wallet, expected.account, challenge, expected));
  wallet.signMessage = async () => { throw new Error('User rejected'); };
  await assert.rejects(signChallenge(wallet, expected.account, challenge, expected), /User rejected/);
});

test('changing any binding context while the prompt is open invalidates submission', () => {
  const { expected } = fixture();
  assert.equal(sameBindingContext(expected, { ...expected }), true);
  assert.equal(sameBindingContext(expected, null), false);
  for (const key of Object.keys(expected)) assert.equal(sameBindingContext(expected, { ...expected, [key]: 'changed' }), false);
});
