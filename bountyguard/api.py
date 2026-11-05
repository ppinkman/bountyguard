"""Loopback-only development API; no public hosting or OAuth app is assumed."""
import base64
import json
import os
from pathlib import Path
import secrets
import time
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import Field

from . import __version__
from .auth import Sessions
from .domain import CreateBounty, GuardError, StrictModel
from .near import NearRPC, TestnetSigner
from .service import Bounties
from .store import Store
from .limits import development_limit

ROOT = Path(__file__).resolve().parents[1]


class Login(StrictModel):
    token: str = Field(min_length=8, max_length=512)


class Challenge(StrictModel):
    account: str
    purpose: str


class Signature(StrictModel):
    challenge_id: str
    public_key: str = Field(max_length=100)
    signature: str = Field(max_length=200)


class Assign(StrictModel):
    claim_id: str


class Funding(StrictModel):
    expected_terms_hash: str = Field(min_length=64, max_length=64)


class Submission(StrictModel):
    pr_url: str = Field(max_length=300)


class Review(StrictModel):
    allow_model: bool = False


class Operation(StrictModel):
    operation_id: str = Field(max_length=180)


def create_app(store=None, rpc=None, signer=None, sessions=None, reviewer=None):
    store = store or Store(os.getenv("BOUNTYGUARD_DB", str(ROOT / "data/bountyguard.sqlite3")))
    rpc = rpc or NearRPC()
    if signer is None and os.getenv("BOUNTYGUARD_CONTRACT") and os.getenv("BOUNTYGUARD_CODE_HASH"):
        signer = TestnetSigner(store, rpc, os.environ["BOUNTYGUARD_CONTRACT"], os.getenv("BOUNTYGUARD_VAULT", str(ROOT / "data/testnet/maintainer.dpapi")), os.environ["BOUNTYGUARD_CODE_HASH"])
    sessions = sessions or Sessions()
    service = Bounties(store, rpc, signer, reviewer)
    app = FastAPI(title="BountyGuard", version=__version__)
    app.state.service = service; app.state.sessions = sessions
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])

    @app.exception_handler(GuardError)
    async def guard_error(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=exc.status)

    @app.middleware("http")
    async def local_policy(request, call_next):
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            if origin and (urlsplit(origin).netloc != request.url.netloc or urlsplit(origin).scheme != request.url.scheme):
                return JSONResponse({"detail": "Cross-origin writes are refused."}, status_code=403)
            if request.headers.get("content-type", "").split(";")[0] != "application/json":
                return JSONResponse({"detail": "Use application/json."}, status_code=415)
            if int(request.headers.get("content-length", "0")) > 80_000:
                return JSONResponse({"detail": "Request exceeds the size limit."}, status_code=413)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        nonce = getattr(request.state, "csp_nonce", None)
        nonce_source = " 'nonce-" + nonce + "'" if nonce else ""
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'" + nonce_source + "; style-src 'self'" + nonce_source + "; img-src 'self' data:; connect-src 'self' https://raw.githubusercontent.com https://wallet.intear.tech https://mc.meteorwallet.app https://meteor-connect-backend-development.meteorwallet.workers.dev https://rpc.testnet.near.org https://test.rpc.fastnear.com; frame-src 'self' https://wallet.intear.tech https://wallet.meteorwallet.app; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        return response

    def authenticated(request):
        bearer = request.headers.get("authorization", "")
        raw = bearer[7:] if bearer.startswith("Bearer ") else request.cookies.get("bg_session", "")
        value = sessions.get(raw)
        if request.method != "GET" and not bearer.startswith("Bearer ") and not secrets.compare_digest(value["csrf"], request.headers.get("x-csrf-token", "")):
            raise GuardError("Session confirmation token is missing or invalid.", 403)
        return value

    @app.get("/")
    def index(request: Request):
        request.state.csp_nonce = base64.b64encode(secrets.token_bytes(24)).decode()
        return HTMLResponse((ROOT / "bountyguard/web/index.html").read_text(encoding="utf-8").replace("__CSP_NONCE__", request.state.csp_nonce))

    @app.get("/api/status")
    def status():
        funding_limit, model_limit = development_limit("funding"), development_limit("model")
        with store.connection() as db:
            funding_used = db.execute("SELECT COUNT(*) FROM operations WHERE kind='fund_assigned'").fetchone()[0]
            model_used = db.execute("SELECT COUNT(*) FROM ai_calls WHERE created_at>=?", (int(time.time())-86400,)).fetchone()[0]
        return {"version": __version__, "network": "testnet", "model_enabled": os.getenv("BOUNTYGUARD_ENABLE_AI") == "1", "signing_enabled": os.getenv("BOUNTYGUARD_ENABLE_TESTNET") == "1" and signer is not None, "local_github_enabled": os.getenv("BOUNTYGUARD_LOCAL_GITHUB") == "1" and bool(os.getenv("GITHUB_TOKEN")), "max_bounty_tnear": "0.01", "storage_charge_tnear": "0.01", "max_funding_intents": funding_limit, "funding_intents_used": funding_used, "funding_intents_remaining": max(0,funding_limit-funding_used), "max_model_intents_per_day": model_limit, "model_intents_used": model_used, "model_intents_remaining": max(0,model_limit-model_used), "quota_scope": "Development safeguards, not wallet or provider balances. Existing settlement, refunds and cached reviews remain available.", "wallet_binding": "NEP-413 + current FullAccess key lookup", "settlement": "Maintainer attestation after reviewed PR merge; contract does not query GitHub."}

    @app.post("/api/session")
    def login(body: Login):
        raw, session = sessions.login(body.token)
        response = JSONResponse({"actor": session["actor"], "csrf": session["csrf"], "session": raw})
        response.set_cookie("bg_session", raw, httponly=True, samesite="strict", max_age=3600)
        return response

    @app.get("/api/session")
    def me(request: Request):
        session = authenticated(request)
        return {"actor": session["actor"], "csrf": session["csrf"]}

    @app.post("/api/session/local")
    def local_login():
        if os.getenv("BOUNTYGUARD_LOCAL_GITHUB") != "1" or not os.getenv("GITHUB_TOKEN"):
            raise GuardError("Local GitHub login was not enabled by the operator.", 403)
        return login(Login(token=os.environ["GITHUB_TOKEN"]))

    @app.post("/api/logout")
    def logout(request: Request):
        authenticated(request)
        sessions.logout(request.cookies.get("bg_session", ""))
        response = JSONResponse({"signed_out": True}); response.delete_cookie("bg_session")
        return response

    @app.get("/api/bounties")
    def listing():
        return store.list()

    @app.get("/api/bounties/{identifier}")
    def get_bounty(identifier: str):
        return {**store.get(identifier), "claims": service.claims(identifier), "events": store.events(identifier), "operations": store.operations(identifier)}

    @app.post("/api/bounties")
    def create(body: CreateBounty, request: Request):
        session = authenticated(request)
        return service.create(body, session["actor"], session["github"])

    @app.post("/api/bounties/{identifier}/wallet/challenge")
    def challenge(identifier: str, body: Challenge, request: Request):
        session = authenticated(request)
        return service.identity.challenge(store.get(identifier), session["actor"], body.account, body.purpose)

    @app.get("/api/bounties/{identifier}/wallet/status")
    def wallet_status(identifier: str, request: Request):
        session = authenticated(request); store.get(identifier)
        result = {}
        for purpose in ("maintainer", "claimant"):
            try:
                binding = store.binding(identifier, session["actor"]["id"], purpose)
            except GuardError:
                result[purpose] = None
            else:
                result[purpose] = {"account": binding["near_account_id"], "verified_at": binding["verified_at"]}
        return result

    @app.post("/api/bounties/{identifier}/wallet/verify")
    def verify_signature(identifier: str, body: Signature, request: Request):
        session = authenticated(request)
        with store.connection() as db:
            row = db.execute("SELECT bounty_id FROM challenges WHERE id=?", (body.challenge_id,)).fetchone()
        if not row or row[0] != identifier:
            raise GuardError("Challenge belongs to another bounty.", 403)
        return service.identity.verify(body.challenge_id, session["actor"], body.public_key, body.signature)

    @app.post("/api/bounties/{identifier}/claim")
    def claim(identifier: str, request: Request):
        return service.claim(identifier, authenticated(request)["actor"])

    @app.post("/api/bounties/{identifier}/assign")
    def assign(identifier: str, body: Assign, request: Request):
        return service.assign(identifier, body.claim_id, authenticated(request)["actor"])

    @app.post("/api/bounties/{identifier}/fund")
    def fund(identifier: str, body: Funding, request: Request):
        return service.fund(identifier, authenticated(request)["actor"], body.expected_terms_hash)

    @app.post("/api/bounties/{identifier}/pr")
    def submit(identifier: str, body: Submission, request: Request):
        session = authenticated(request)
        return service.submit_pr(identifier, body.pr_url, session["actor"], session["github"])

    @app.post("/api/bounties/{identifier}/review")
    def review(identifier: str, body: Review, request: Request):
        session = authenticated(request)
        return service.verify(identifier, session["actor"], session["github"], body.allow_model)

    @app.post("/api/bounties/{identifier}/sync")
    def sync(identifier: str, request: Request):
        session = authenticated(request)
        return service.sync(identifier, session["actor"], session["github"])

    @app.post("/api/bounties/{identifier}/refund")
    def refund(identifier: str, request: Request):
        return service.refund(identifier, authenticated(request)["actor"])

    @app.post("/api/bounties/{identifier}/reconcile")
    def reconcile(identifier: str, body: Operation, request: Request):
        session = authenticated(request); bounty = store.get(identifier)
        service.creator(bounty, session["actor"])
        with store.connection() as db:
            operation = db.execute("SELECT bounty_id FROM operations WHERE id=?", (body.operation_id,)).fetchone()
        if not operation or operation[0] != identifier:
            raise GuardError("Operation does not belong to this bounty.")
        receipt = service.require_signer().reconcile(body.operation_id)
        if body.operation_id == identifier + ":fund":
            if bounty.get("funding_receipt"):
                return bounty
            chain = rpc.view(signer.contract, "get_bounty", {"id": identifier})
            if receipt.get("state") == "NOT_SIGNED" and chain is None and bounty["state"] == "FUNDING_UNCERTAIN":
                return store.save(bounty, "ASSIGNED", "unsigned_intent_recovered", receipt)
            if chain["terms_hash"] != bounty["assigned_terms_hash"] or chain["claimant"] != bounty["claim"]["near_account_id"] or chain["amount"] != bounty["amount_yocto"]:
                raise GuardError("Recovered chain bounty does not match the assigned terms.")
            bounty["funding_receipt"] = receipt
            return store.save(bounty, "FUNDED", "funding_reconciled", receipt)
        return {"receipt": receipt, "bounty": store.get(identifier), "next": "Refresh settlement/refund using the same bounty."}

    app.mount("/assets", StaticFiles(directory=ROOT / "bountyguard/web"), name="assets")
    return app
