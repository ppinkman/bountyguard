import argparse
import base64
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="BountyGuard local development tools")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve"); serve.add_argument("--port", type=int, default=8766)
    sign = sub.add_parser("sign-challenge"); sign.add_argument("challenge"); sign.add_argument("--vault", required=True)
    args = parser.parse_args()
    if args.command == "serve":
        import uvicorn
        from .api import create_app
        uvicorn.run(create_app(), host="127.0.0.1", port=args.port, access_log=False)
    else:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from .near import load_vault
        from .identity import nep413_digest
        challenge = json.loads(Path(args.challenge).read_text(encoding="utf-8"))
        vault = load_vault(args.vault)
        if vault["account_id"] != challenge["near_account_id"]:
            raise SystemExit("Challenge account does not match the local test wallet.")
        private = Ed25519PrivateKey.from_private_bytes(base64.b64decode(vault["seed"]))
        signature = private.sign(nep413_digest(challenge["message"], base64.b64decode(challenge["nonce"]), challenge["recipient"], challenge.get("callback_url")))
        print(json.dumps({"challenge_id": challenge["id"], "public_key": vault["public_key"], "signature": base64.b64encode(signature).decode()}))


if __name__ == "__main__":
    main()
