"""Single-use NEP-413 challenges bound to numeric GitHub identities."""
import base64
import hashlib
import json
import secrets
import struct
import time
import uuid

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .domain import GuardError, canonical, testnet_account

ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def b58encode(raw):
    number = int.from_bytes(raw, "big"); value = ""
    while number:
        number, remainder = divmod(number, 58); value = ALPHABET[remainder] + value
    return "1" * (len(raw) - len(raw.lstrip(b"\0"))) + value


def b58decode(value):
    if not value or len(value) > 100:
        raise GuardError("Invalid base58 key.", 422)
    number = 0
    try:
        for character in value:
            number = number * 58 + ALPHABET.index(character)
    except ValueError:
        raise GuardError("Invalid base58 key.", 422) from None
    return b"\0" * (len(value) - len(value.lstrip("1"))) + number.to_bytes((number.bit_length() + 7) // 8, "big")


def borsh_string(value):
    raw = value.encode("utf-8")
    return struct.pack("<I", len(raw)) + raw


def nep413_digest(message, nonce, recipient, callback_url=None):
    if len(nonce) != 32:
        raise GuardError("NEP-413 nonce must be 32 bytes.", 422)
    callback = b"\0" if callback_url is None else b"\1" + borsh_string(callback_url)
    payload = struct.pack("<I", 2**31 + 413) + borsh_string(message) + nonce + borsh_string(recipient) + callback
    return hashlib.sha256(payload).digest()


class Identity:
    def __init__(self, store, rpc):
        self.store, self.rpc = store, rpc

    def challenge(self, bounty, actor, account, purpose):
        testnet_account(account)
        if purpose not in ("maintainer", "claimant"):
            raise GuardError("Invalid binding purpose.", 422)
        if purpose == "maintainer" and actor["id"] != bounty["creator_id"]:
            raise GuardError("Only the bounty creator can bind its funding account.", 403)
        if bounty["state"] != "DRAFT":
            raise GuardError("Wallet bindings are frozen after assignment.")
        identifier = uuid.uuid4().hex
        expiry = int(time.time()) + 300
        message = canonical({"application": "BountyGuard", "version": 1, "network": "testnet", "bounty_id": bounty["id"], "repo": bounty["repo"], "repo_id": bounty["repo_id"], "issue_number": bounty["issue_number"], "github_user_id": actor["id"], "near_account_id": account, "purpose": purpose, "expires_at": expiry, "terms_hash": bounty["terms_hash"], "challenge_id": identifier})
        document = {"id": identifier, "message": message, "nonce": base64.b64encode(secrets.token_bytes(32)).decode(), "recipient": "bountyguard.local", "callback_url": None, "near_account_id": account, "github_user_id": actor["id"], "expires_at": expiry, "purpose": purpose, "bounty_id": bounty["id"]}
        with self.store.connection() as db:
            db.execute("INSERT INTO challenges VALUES (?,?,?,?,?,0,?)", (identifier, actor["id"], bounty["id"], purpose, expiry, canonical(document)))
        return document

    def verify(self, challenge_id, actor, public_key, signature):
        with self.store.connection() as db:
            row = db.execute("SELECT * FROM challenges WHERE id=?", (challenge_id,)).fetchone()
        if not row or row["actor_id"] != actor["id"] or row["used"] or row["expires_at"] <= time.time():
            raise GuardError("Signature challenge is missing, expired, used or belongs to another GitHub identity.", 403)
        challenge = json.loads(row["document"])
        try:
            if not public_key.startswith("ed25519:"):
                raise ValueError()
            key = b58decode(public_key.split(":", 1)[1])
            raw_signature = base64.b64decode(signature, validate=True)
            Ed25519PublicKey.from_public_bytes(key).verify(raw_signature, nep413_digest(challenge["message"], base64.b64decode(challenge["nonce"]), challenge["recipient"]))
        except (ValueError, InvalidSignature):
            raise GuardError("NEP-413 signature is invalid.", 403) from None
        ownership = self.rpc.access_key(challenge["near_account_id"], public_key)
        if ownership.get("permission") != "FullAccess":
            raise GuardError("Signing key is not a current FullAccess key of the claimed testnet account.", 403)
        proof = {**challenge, "public_key": public_key, "signature": signature, "verified_at": int(time.time()), "key_block_hash": ownership["block_hash"], "key_block_height": ownership["block_height"]}
        with self.store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            current = db.execute("SELECT state FROM bounties WHERE id=?", (challenge["bounty_id"],)).fetchone()
            if not current or current[0] != "DRAFT":
                raise GuardError("Assignment froze wallet binding while verification was in progress.")
            consumed = db.execute("UPDATE challenges SET used=1 WHERE id=? AND used=0 AND expires_at>?", (challenge_id, int(time.time())))
            if consumed.rowcount != 1:
                raise GuardError("Challenge was already consumed or expired.")
            existing = db.execute("SELECT document FROM bindings WHERE bounty_id=? AND actor_id=? AND purpose=?", (challenge["bounty_id"], actor["id"], challenge["purpose"])).fetchone()
            if existing and json.loads(existing[0])["near_account_id"] != challenge["near_account_id"]:
                raise GuardError("A different recipient is already bound. Create a new bounty to change it.")
            db.execute("INSERT OR REPLACE INTO bindings VALUES (?,?,?,?)", (challenge["bounty_id"], actor["id"], challenge["purpose"], canonical(proof)))
        return proof
