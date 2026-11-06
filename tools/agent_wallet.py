"""Bind a claimant's existing testnet key to one BountyGuard task."""
import argparse
import base64
import json
import os
from pathlib import Path
import re
import time

import httpx2
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from bountyguard.domain import testnet_account
from bountyguard.identity import b58encode, nep413_digest
from bountyguard.near import make_key

ORIGIN = "http://127.0.0.1:8766"


class DemoError(Exception):
    """An operator-facing error that contains no upstream payload."""


def checked_id(value):
    if not re.fullmatch(r"[0-9a-f]{32}", value):
        raise DemoError("Use an exact bounty ID.")
    return value


class LocalAPI:
    def __init__(self):
        self.http = httpx2.Client(base_url=ORIGIN, trust_env=False, timeout=90)
        self.session = None

    def close(self):
        self.http.close()

    def call(self, path, body=None):
        headers = {"Authorization": "Bearer " + self.session} if self.session else {}
        try:
            response = self.http.request("GET" if body is None else "POST", "/api/" + path,
                                         headers=headers, json=body)
            response.raise_for_status()
            return response.json()
        except (httpx2.HTTPError, ValueError):
            raise DemoError("Local API request failed. Check the service and inspect the current bounty state.") from None

    def login(self, token):
        result = self.call("session", {"token": token})
        self.session = result["session"]
        return result["actor"]


def signature(challenge, bounty, actor_id, account, seed, *, now=None):
    testnet_account(account)
    context = json.loads(challenge["message"])
    expiry = context["expires_at"]
    now = time.time() if now is None else now
    expected = {
        "application": "BountyGuard", "version": 1, "network": "testnet",
        "bounty_id": bounty["id"], "repo": bounty["repo"], "repo_id": bounty["repo_id"],
        "issue_number": bounty["issue_number"], "github_user_id": actor_id,
        "near_account_id": account, "purpose": "claimant", "terms_hash": bounty["terms_hash"],
        "challenge_id": challenge["id"], "expires_at": expiry,
    }
    if (context != expected or challenge["recipient"] != "bountyguard.local"
            or challenge.get("callback_url") is not None or not now < expiry <= now + 300):
        raise DemoError("Refused to sign a mismatched or expired testnet identity challenge.")
    key = Ed25519PrivateKey.from_private_bytes(base64.b64decode(seed, validate=True))
    signed = key.sign(nep413_digest(challenge["message"], base64.b64decode(challenge["nonce"], validate=True),
                                   challenge["recipient"]))
    return {"challenge_id": challenge["id"],
            "public_key": "ed25519:" + b58encode(key.public_key().public_bytes_raw()),
            "signature": base64.b64encode(signed).decode("ascii")}


def bind(api, bounty, actor_id, account, key_file):
    base = "bounties/" + checked_id(bounty["id"])
    binding = api.call(base + "/wallet/status")["claimant"]
    if binding:
        if binding["account"] != account:
            raise DemoError("This claimant is already bound to a different account.")
        return
    seed = os.environ.get("BOUNTYGUARD_AGENT_SEED")
    if seed is None and key_file:
        if os.name != "nt" and key_file.stat().st_mode & 0o077:
            raise DemoError("The key file must be accessible only to its owner.")
        seed = json.loads(key_file.read_text(encoding="utf-8"))["seed"]
    if not seed:
        raise DemoError("Supply the claimant identity key via environment or --key-file.")
    challenge = api.call(base + "/wallet/challenge", {"account": account, "purpose": "claimant"})
    api.call(base + "/wallet/verify", signature(challenge, bounty, actor_id, account, seed))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("key_file", type=Path, help="New file inside a private, ignored directory")
    args = parser.parse_args()
    key = make_key()
    fd = os.open(args.key_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as target:
        json.dump(key, target)
    print(key["public_key"])


if __name__ == "__main__":
    main()
