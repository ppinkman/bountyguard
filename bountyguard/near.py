"""Bounded testnet transport and durable, non-retrying transaction intents.

The V0 Borsh layout, base58 and CurrentUser DPAPI approach are adapted from
ProofPay's low-level testnet transport. Bounty lifecycle logic is independent.
"""
import base64
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import struct
import threading
import time
import urllib.error
import urllib.request

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, PublicFormat, NoEncryption

from .domain import GuardError, canonical, digest, testnet_account
from .github import opener
from .identity import b58encode, b58decode, borsh_string

RPC_URL = "https://rpc.testnet.near.org"
FAUCET_URL = "https://helper.nearprotocol.com/account"


class Blob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]


def protect(raw, decrypt=False):
    if os.name != "nt":
        raise GuardError("This development signer requires Windows CurrentUser DPAPI. Read-only verification remains cross-platform.")
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]; kernel.LocalFree.restype = ctypes.c_void_p
    crypt.CryptProtectData.argtypes = [ctypes.POINTER(Blob), ctypes.c_wchar_p, ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    crypt.CryptUnprotectData.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    buffer = (ctypes.c_ubyte * len(raw)).from_buffer_copy(raw)
    source, output = Blob(len(raw), buffer), Blob()
    if decrypt:
        ok = crypt.CryptUnprotectData(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output))
    else:
        ok = crypt.CryptProtectData(ctypes.byref(source), "BountyGuard testnet", None, None, None, 1, ctypes.byref(output))
    if not ok:
        raise GuardError("Current Windows user could not access the development vault.")
    try:
        return ctypes.string_at(output.data, output.size)
    finally:
        kernel.LocalFree(ctypes.cast(output.data, ctypes.c_void_p))


def make_key():
    key = Ed25519PrivateKey.generate()
    return {"seed": base64.b64encode(key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())).decode(), "public_key": "ed25519:" + b58encode(key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw))}


def save_vault(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_bytes(protect(canonical(value).encode()))
    os.replace(temporary, path)


def load_vault(path):
    return json.loads(protect(Path(path).read_bytes(), decrypt=True))


class NearRPC:
    def __init__(self):
        self._testnet = False

    def call(self, method, params):
        request = urllib.request.Request(RPC_URL, data=canonical({"jsonrpc": "2.0", "id": "bountyguard", "method": method, "params": params}).encode(), headers={"Content-Type": "application/json"})
        try:
            with opener().open(request, timeout=30) as response:
                raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise GuardError("Testnet evidence exceeds the response limit.")
            result = json.loads(raw)
            if "error" in result or isinstance(result.get("result"), dict) and "error" in result["result"]:
                raise GuardError("Testnet RPC did not confirm the requested operation or state.", 502)
            return result["result"]
        except (OSError, ValueError, KeyError):
            raise GuardError("Testnet result is unavailable. Reconcile the original operation; do not recreate payment.", 502) from None

    def assert_testnet(self):
        if not self._testnet:
            if self.call("status", [])["chain_id"] != "testnet":
                raise GuardError("Signing is restricted to the testnet network.")
            self._testnet = True

    def access_key(self, account, public_key):
        self.assert_testnet()
        return self.call("query", {"request_type": "view_access_key", "finality": "final", "account_id": testnet_account(account), "public_key": public_key})

    def account(self, account):
        self.assert_testnet()
        return self.call("query", {"request_type": "view_account", "finality": "final", "account_id": testnet_account(account)})

    def view(self, contract, method, args):
        self.assert_testnet()
        result = self.call("query", {"request_type": "call_function", "finality": "final", "account_id": testnet_account(contract), "method_name": method, "args_base64": base64.b64encode(canonical(args).encode()).decode()})
        try:
            return json.loads(bytes(result["result"]))
        except (KeyError, ValueError):
            raise GuardError("Invalid testnet contract response.") from None


def serialize_call(signer, public_key, nonce, contract, block_hash, method, args, deposit):
    public = b58decode(public_key.removeprefix("ed25519:")); block = b58decode(block_hash)
    if len(public) != 32 or len(block) != 32 or not 0 < nonce < 2**64 or deposit < 0:
        raise GuardError("Invalid transaction fields.")
    encoded_args = canonical(args).encode()
    action = b"\x02" + borsh_string(method) + struct.pack("<I", len(encoded_args)) + encoded_args + struct.pack("<Q", 100_000_000_000_000) + deposit.to_bytes(16, "little")
    return borsh_string(testnet_account(signer)) + b"\0" + public + struct.pack("<Q", nonce) + borsh_string(testnet_account(contract)) + block + struct.pack("<I", 1) + action


class TestnetSigner:
    def __init__(self, store, rpc, contract, vault_path, code_hash):
        self.store, self.rpc = store, rpc
        self.contract, self.vault_path, self.code_hash = testnet_account(contract), Path(vault_path), code_hash
        self.lock = threading.RLock()

    def check(self, maintainer):
        if os.getenv("BOUNTYGUARD_ENABLE_TESTNET") != "1":
            raise GuardError("Testnet signing is disabled. No transaction was created.")
        vault = load_vault(self.vault_path)
        if vault["account_id"] != maintainer:
            raise GuardError("Configured signer does not match this bounty's verified maintainer.")
        if self.rpc.account(self.contract)["code_hash"] != self.code_hash:
            raise GuardError("Deployed contract does not match the pinned code hash.")
        return vault

    def execute(self, operation_id, bounty_id, maintainer, method, args, deposit=0):
        with self.lock:
            if method not in {"fund_assigned", "record_review", "pay", "refund_expired"} or deposit < 0 or deposit > 2 * 10**22:
                raise GuardError("Operation is outside the bounded bounty signer policy.")
            vault = self.check(maintainer)
            intent = {"contract": self.contract, "signer": maintainer, "method": method, "args": args, "deposit": str(deposit), "code_hash": self.code_hash}
            row, created = self.store.operation(operation_id, bounty_id, method, intent)
            if not created:
                if row["state"] == "CONFIRMED":
                    return json.loads(row["document"])["receipt"]
                raise GuardError("Original chain operation is pending or uncertain. Reconcile it before continuing.")
            key = self.rpc.access_key(maintainer, vault["public_key"])
            raw = serialize_call(maintainer, vault["public_key"], key["nonce"] + 1, self.contract, key["block_hash"], method, args, deposit)
            private = Ed25519PrivateKey.from_private_bytes(base64.b64decode(vault["seed"]))
            transaction_hash = b58encode(hashlib.sha256(raw).digest())
            signed = raw + b"\0" + private.sign(hashlib.sha256(raw).digest())
            document = {"intent": intent, "tx_hash": transaction_hash, "signed_dpapi": base64.b64encode(protect(signed)).decode()}
            with self.store.connection() as db:
                db.execute("UPDATE operations SET state='SUBMITTED',document=? WHERE id=?", (canonical(document), operation_id))
            try:
                result = self.rpc.call("send_tx", {"signed_tx_base64": base64.b64encode(signed).decode(), "wait_until": "FINAL"})
                return self.confirm(row["id"], document, result)
            except GuardError:
                with self.store.connection() as db:
                    db.execute("UPDATE operations SET state='UNKNOWN' WHERE id=? AND state='SUBMITTED'", (operation_id,))
                raise

    def confirm(self, operation_id, document, result):
        transaction = result.get("transaction", {})
        if result.get("final_execution_status") != "FINAL" or transaction.get("hash") != document["tx_hash"] or transaction.get("receiver_id") != self.contract or transaction.get("signer_id") != document["intent"]["signer"]:
            raise GuardError("Original transaction has not reached matching final execution. Reconcile its existing hash.")
        status = result.get("status", {})
        if not isinstance(status, dict) or "SuccessValue" not in status:
            with self.store.connection() as db:
                db.execute("UPDATE operations SET state='FAILED' WHERE id=?", (operation_id,))
            raise GuardError("Transaction did not succeed. Inspect its original chain receipt.")
        receipt = {"transaction_hash": document["tx_hash"], "explorer_url": "https://testnet.nearblocks.io/txns/" + document["tx_hash"], "contract": self.contract, "network": "testnet", "status": status, "final_execution_status": result.get("final_execution_status")}
        document["receipt"] = receipt
        document["raw_result"] = result
        with self.store.connection() as db:
            db.execute("UPDATE operations SET state='CONFIRMED',document=? WHERE id=?", (canonical(document), operation_id))
        return receipt

    def reconcile(self, operation_id):
        with self.store.connection() as db:
            row = db.execute("SELECT * FROM operations WHERE id=?", (operation_id,)).fetchone()
        if not row:
            raise GuardError("Operation not found.", 404)
        document = json.loads(row["document"])
        if row["state"] == "CONFIRMED":
            return document["receipt"]
        if not document.get("tx_hash"):
            if row["state"] == "PREPARED":
                with self.store.connection() as db:
                    db.execute("UPDATE operations SET state='NOT_SIGNED' WHERE id=? AND state='PREPARED'", (operation_id,))
                return {"state": "NOT_SIGNED", "operation_id": operation_id, "network": "testnet"}
            raise GuardError("No signed transaction exists for this operation.")
        result = self.rpc.call("tx", {"tx_hash": document["tx_hash"], "sender_account_id": document["intent"]["signer"], "wait_until": "FINAL"})
        return self.confirm(operation_id, document, result)
