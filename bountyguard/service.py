"""Assigned bounty workflow. GitHub facts stay off-chain and are rechecked."""
import json
import threading
import time
import uuid

from .domain import CreateBounty, GuardError, STORAGE_YOCTO, amount_yocto, canonical, digest, diff_digest, github_url, issue_context
from .identity import Identity
from .review import Reviewer
from .verifier import hard_checks


class Bounties:
    def __init__(self, store, rpc, signer=None, reviewer=None):
        self.store, self.rpc, self.signer = store, rpc, signer
        self.identity = Identity(store, rpc)
        self.reviewer = reviewer or Reviewer(store)
        self.locks = {}; self.lock = threading.Lock()

    def guarded(self, identifier):
        with self.lock:
            return self.locks.setdefault(identifier, threading.RLock())

    def creator(self, bounty, actor):
        if bounty["creator_id"] != actor["id"]:
            raise GuardError("Only this bounty's verified GitHub maintainer can perform this action.", 403)

    def create(self, request: CreateBounty, actor, github):
        repo, number = github_url(request.issue_url, "issues")
        repository = github.repo(repo)
        if repository.get("private"):
            raise GuardError("This first release supports public repository bounties only.", 422)
        permissions = repository.get("permissions", {})
        if not (permissions.get("admin") or permissions.get("maintain") or permissions.get("push")):
            raise GuardError("Your GitHub identity must have write/maintain/admin access to this repository.", 403)
        if repository["full_name"].lower() != repo.lower():
            raise GuardError("Repository moved. Confirm its current canonical URL.")
        issue = github.issue(repo, number)
        if issue["state"] != "open":
            raise GuardError("Create a bounty for an open Issue.")
        now = int(time.time())
        if not now + 300 <= request.deadline <= now + 7 * 86400:
            raise GuardError("Choose a deadline between five minutes and seven days from now.", 422)
        workflow = github.workflow(repo, request.workflow_path)
        if workflow["path"] != request.workflow_path or workflow["state"] != "active":
            raise GuardError("Select an active workflow in the maintained repository.")
        source = github.file(repo, request.workflow_path, repository["default_branch"])
        app = github.request("/apps/github-actions")
        if app["slug"] != "github-actions":
            raise GuardError("Could not establish the GitHub Actions application identity.")
        document = {"id": uuid.uuid4().hex, "creator_id": actor["id"], "creator_login": actor["login"], "repo": repository["full_name"], "repo_id": repository["id"], "issue_url": issue["html_url"], "issue_number": number, "issue": issue_context(issue, repository["id"]), "issue_hash": digest(issue_context(issue, repository["id"])), "amount_yocto": str(amount_yocto(request.amount)), "amount": request.amount, "network": "testnet", "deadline": request.deadline, "source_paths": request.source_paths, "ci": {"workflow_id": workflow["id"], "workflow_path": workflow["path"], "workflow_blob_sha": source["sha"], "app_id": app["id"], "required_checks": request.required_checks}, "require_merge": True, "acceptance_version": "bountyguard/v1", "created_at": now}
        document["terms_hash"] = digest(document)
        return self.store.create(document)

    def claim(self, bounty_id, actor):
        with self.guarded(bounty_id), self.store.connection() as db:
            bounty = self.store.get(bounty_id)
            if bounty["state"] != "DRAFT":
                raise GuardError("This bounty is no longer accepting unassigned claims.")
            binding = self.store.binding(bounty_id, actor["id"], "claimant")
            existing = db.execute("SELECT document FROM claims WHERE bounty_id=? AND actor_id=?", (bounty_id, actor["id"])).fetchone()
            if existing:
                return json.loads(existing[0])
            claim = {"id": uuid.uuid4().hex, "bounty_id": bounty_id, "actor_id": actor["id"], "login": actor["login"], "near_account_id": binding["near_account_id"], "binding_hash": digest(binding)}
            db.execute("INSERT INTO claims VALUES (?,?,?,?)", (claim["id"], bounty_id, actor["id"], canonical(claim)))
        return claim

    def claims(self, bounty_id):
        with self.store.connection() as db:
            return [json.loads(r[0]) for r in db.execute("SELECT document FROM claims WHERE bounty_id=? ORDER BY id", (bounty_id,))]

    def assign(self, bounty_id, claim_id, actor):
        with self.guarded(bounty_id):
            bounty = self.store.get(bounty_id); self.creator(bounty, actor)
            if bounty["state"] == "ASSIGNED" and bounty["claim"]["id"] == claim_id:
                return bounty
            if bounty["state"] != "DRAFT":
                raise GuardError("Only draft bounties can be assigned.")
            claims = [c for c in self.claims(bounty_id) if c["id"] == claim_id]
            if len(claims) != 1:
                raise GuardError("Choose an existing verified claim.")
            maintainer = self.store.binding(bounty_id, actor["id"], "maintainer")
            claimant = self.store.binding(bounty_id, claims[0]["actor_id"], "claimant")
            if maintainer["near_account_id"] == claimant["near_account_id"]:
                raise GuardError("Maintainer and claimant must use distinct testnet accounts.")
            for binding in (maintainer, claimant):
                if self.rpc.access_key(binding["near_account_id"], binding["public_key"])["permission"] != "FullAccess":
                    raise GuardError("An identity key was revoked or restricted. Rebind before assigning.")
            bounty.update({"claim": claims[0], "maintainer_account": maintainer["near_account_id"]})
            bounty["assigned_terms_hash"] = digest({"terms_hash": bounty["terms_hash"], "claim": bounty["claim"], "maintainer_account": bounty["maintainer_account"]})
            return self.store.save(bounty, "ASSIGNED", "assigned", {"claim_id": claim_id, "assigned_terms_hash": bounty["assigned_terms_hash"]})

    def require_signer(self):
        if self.signer is None:
            raise GuardError("No BountyGuard testnet contract/signer is configured. No chain transaction was created.")
        return self.signer

    def fund(self, bounty_id, actor, expected_terms_hash):
        with self.guarded(bounty_id):
            bounty = self.store.get(bounty_id); self.creator(bounty, actor)
            if expected_terms_hash != bounty.get("assigned_terms_hash"):
                raise GuardError("Assigned bounty terms changed. Confirm the current exact hash.")
            if bounty["state"] not in ("ASSIGNED", "FUNDING_UNCERTAIN"):
                if bounty.get("funding_receipt"):
                    return bounty
                raise GuardError("Bounty must be assigned before funding.")
            if int(time.time()) >= bounty["deadline"]:
                raise GuardError("Bounty expired before funding.")
            for actor_id, purpose in ((bounty["creator_id"], "maintainer"), (bounty["claim"]["actor_id"], "claimant")):
                binding = self.store.binding(bounty_id, actor_id, purpose)
                if self.rpc.access_key(binding["near_account_id"], binding["public_key"])["permission"] != "FullAccess":
                    raise GuardError("A bound wallet identity key is no longer current; funding is blocked.")
            signer = self.require_signer()
            args = {"id": bounty["id"], "claimant": bounty["claim"]["near_account_id"], "github_user_id": str(bounty["claim"]["actor_id"]), "repo_id": str(bounty["repo_id"]), "issue_number": bounty["issue_number"], "terms_hash": bounty["assigned_terms_hash"], "amount": bounty["amount_yocto"], "deadline_ns": str(bounty["deadline"] * 10**9)}
            try:
                receipt = signer.execute(bounty_id + ":fund", bounty_id, bounty["maintainer_account"], "fund_assigned", args, int(bounty["amount_yocto"]) + STORAGE_YOCTO)
            except GuardError as exc:
                # A reserved intent is reconciled, never replaced by a new order.
                with self.store.connection() as db:
                    exists = db.execute("SELECT 1 FROM operations WHERE id=?", (bounty_id + ":fund",)).fetchone()
                if exists:
                    self.store.save(bounty, "FUNDING_UNCERTAIN", "funding_attention", {"reason": str(exc)})
                raise
            bounty["funding_receipt"] = receipt
            return self.store.save(bounty, "FUNDED", "funded", receipt)

    def submit_pr(self, bounty_id, pr_url, actor, github):
        with self.guarded(bounty_id):
            bounty = self.store.get(bounty_id)
            if actor["id"] != bounty.get("claim", {}).get("actor_id"):
                raise GuardError("Only the assigned GitHub identity can submit this PR.", 403)
            if bounty["state"] not in ("FUNDED", "PR_SUBMITTED", "REVIEW_REQUIRED", "READY_TO_MERGE", "REVISION_CHANGED"):
                raise GuardError("This bounty does not accept a new delivery in its current state.")
            repo, number = github_url(pr_url, "pull")
            if repo.lower() != bounty["repo"].lower():
                raise GuardError("PR must target the assigned Issue repository.")
            pr = github.request(f"/repos/{bounty['repo']}/pulls/{number}")
            if pr["base"]["repo"]["id"] != bounty["repo_id"] or pr["user"]["id"] != actor["id"]:
                raise GuardError("PR repository or author does not match the verified claim.", 403)
            bounty["pr_number"] = number; bounty["pr_url"] = pr["html_url"]
            bounty.pop("review", None)
            return self.store.save(bounty, "PR_SUBMITTED", "pr_submitted", {"number": number, "head_sha": pr["head"]["sha"]})

    def verify(self, bounty_id, actor, github, allow_model=False):
        with self.guarded(bounty_id):
            bounty = self.store.get(bounty_id)
            if actor["id"] not in (bounty["creator_id"], bounty.get("claim", {}).get("actor_id")):
                raise GuardError("Only assigned participants can request a review.", 403)
            if bounty["state"] not in ("PR_SUBMITTED", "REVIEW_REQUIRED", "READY_TO_MERGE", "REVISION_CHANGED"):
                raise GuardError("Submit a PR for a funded bounty before requesting review.")
            if time.time() >= bounty["deadline"]:
                raise GuardError("Bounty expired. Use the original refund path.")
            repo = bounty["repo"]
            pr, files = github.pr_snapshot(repo, bounty["pr_number"])
            issue = github.issue(repo, bounty["issue_number"])
            workflow = github.file(repo, bounty["ci"]["workflow_path"], pr["base"]["sha"])
            linked = github.closes_issue(repo, pr["number"], bounty["issue_number"])
            ci = github.ci_evidence(repo, pr, bounty["ci"])
            hard = hard_checks(bounty, pr, files, issue, workflow, linked, ci)
            anchored = {"bounty_id": bounty_id, "terms_hash": bounty["assigned_terms_hash"], "pr_number": pr["number"], "head_sha": pr["head"]["sha"], "base_sha": pr["base"]["sha"], "diff_hash": diff_digest(files)}
            model_fingerprint = digest({**anchored, "issue": bounty["issue"]})
            model = None
            if hard["verdict"] == "PASS" and allow_model:
                model = self.reviewer.review(model_fingerprint, {"issue": bounty["issue"], **anchored, "files": files})
            fingerprint = digest({**anchored, "ci": ci, "hard": hard, "model": model})
            verdict = hard["verdict"] if hard["verdict"] != "PASS" else model["verdict"] if model else "NEEDS_REVIEW"
            report = {**anchored, "fingerprint": fingerprint, "verdict": verdict, "hard": hard, "ci": ci, "ai": model, "created_at": int(time.time()), "delivery_hash": digest({"pr_number": pr["number"], "head_sha": pr["head"]["sha"], "diff_hash": diff_digest(files)})}
            report["report_hash"] = digest(report)
            with self.store.connection() as db:
                db.execute("INSERT OR IGNORE INTO reviews VALUES (?,?,?,?)", (fingerprint, bounty_id, canonical(report), report["created_at"]))
                # Same evidence always resolves to the first immutable report.
                report = json.loads(db.execute("SELECT document FROM reviews WHERE fingerprint=?", (fingerprint,)).fetchone()[0])
            bounty["review"] = report
            return self.store.save(bounty, "READY_TO_MERGE" if report["verdict"] == "PASS" else "REVIEW_REQUIRED", "reviewed", {"head_sha": report["head_sha"], "report_hash": report["report_hash"], "verdict": report["verdict"]})

    def sync(self, bounty_id, actor, github):
        with self.guarded(bounty_id):
            bounty = self.store.get(bounty_id); self.creator(bounty, actor)
            if bounty["state"] == "PAID":
                return bounty
            report = bounty.get("review")
            if not report or report["verdict"] != "PASS" or bounty["state"] not in ("READY_TO_MERGE", "SETTLEMENT_ATTENTION"):
                raise GuardError("A passing, version-bound review is required before settlement.")
            github_repo = github.repo(bounty["repo"])
            if not github_repo.get("permissions", {}).get("push"):
                raise GuardError("Maintainer repository permission is no longer present.", 403)
            pr, files = github.pr_snapshot(bounty["repo"], bounty["pr_number"])
            same = pr["head"]["sha"] == report["head_sha"] and diff_digest(files) == report["diff_hash"] and pr["user"]["id"] == bounty["claim"]["actor_id"] and pr["base"]["repo"]["id"] == bounty["repo_id"]
            if not same:
                return self.store.save(bounty, "REVISION_CHANGED", "review_invalidated", {"reviewed_head": report["head_sha"], "current_head": pr["head"]["sha"]})
            if not pr.get("merged") or not pr.get("merged_at") or not pr.get("merged_by"):
                if pr["base"]["sha"] != report["base_sha"]:
                    return self.store.save(bounty, "REVISION_CHANGED", "base_changed", {})
                raise GuardError("Waiting for a repository maintainer to merge the reviewed PR.")
            commit = github.request(f"/repos/{bounty['repo']}/commits/{pr['merge_commit_sha']}")
            parents = [p["sha"] for p in commit["parents"]]
            if not parents or parents[0] != report["base_sha"] or len(parents) > 2 or len(parents) == 2 and parents[1] != report["head_sha"]:
                raise GuardError("Merge ancestry differs from the reviewed base/head. Re-review or use a supported merge/squash flow.")
            issue = github.issue(bounty["repo"], bounty["issue_number"])
            if digest(issue_context(issue, bounty["repo_id"])) != bounty["issue_hash"]:
                raise GuardError("Issue terms changed after review.")
            ci_pr = {**pr, "base": {**pr["base"], "sha": report["base_sha"]}}
            ci = github.ci_evidence(bounty["repo"], ci_pr, bounty["ci"])
            if not ci["passed"]:
                raise GuardError("Trusted CI is no longer passing; settlement is blocked.")
            if time.time() >= bounty["deadline"]:
                raise GuardError("Settlement deadline passed. The principal follows the refund path.")
            signer = self.require_signer()
            bounty["merge_evidence"] = {"merge_commit_sha": pr["merge_commit_sha"], "merged_at": pr["merged_at"], "merged_by_id": pr["merged_by"]["id"], "head_sha": report["head_sha"], "ci": ci}
            try:
                signer.execute(bounty_id + ":review:" + report["report_hash"], bounty_id, bounty["maintainer_account"], "record_review", {"id": bounty_id, "delivery_hash": report["delivery_hash"], "report_hash": report["report_hash"]})
                chain = self.rpc.view(signer.contract, "get_bounty", {"id": bounty_id})
                if chain["delivery_hash"] != report["delivery_hash"] or chain["report_hash"] != report["report_hash"]:
                    raise GuardError("On-chain delivery/review differs from the approved revision.")
                if chain["status"] != "Paid":
                    nonce = int(chain["transfer_nonce"])
                    receipt = signer.execute(bounty_id + ":pay:" + str(nonce + 1), bounty_id, bounty["maintainer_account"], "pay", {"id": bounty_id, "expected_delivery_hash": report["delivery_hash"], "expected_report_hash": report["report_hash"]}, 1)
                    bounty["payment_receipt"] = receipt
                confirmed = self.rpc.view(signer.contract, "get_bounty", {"id": bounty_id})
                if confirmed["status"] != "Paid":
                    raise GuardError("Payment callback has not confirmed success. Reconcile this operation before retrying.")
            except GuardError as exc:
                self.store.save(bounty, "SETTLEMENT_ATTENTION", "settlement_attention", {"reason": str(exc)})
                raise
            return self.store.save(bounty, "PAID", "paid", {"delivery_hash": report["delivery_hash"], "report_hash": report["report_hash"], "claimant": bounty["claim"]["near_account_id"]})

    def refund(self, bounty_id, actor):
        with self.guarded(bounty_id):
            bounty = self.store.get(bounty_id); self.creator(bounty, actor)
            if bounty["state"] == "REFUNDED":
                return bounty
            if time.time() < bounty["deadline"] or not bounty.get("funding_receipt"):
                raise GuardError("Refund requires an expired, funded bounty.")
            signer = self.require_signer()
            chain = self.rpc.view(signer.contract, "get_bounty", {"id": bounty_id})
            if chain["status"] == "Paid":
                raise GuardError("Paid bounties cannot be refunded.")
            if chain["status"] != "Refunded":
                receipt = signer.execute(bounty_id + ":refund:" + str(int(chain["transfer_nonce"]) + 1), bounty_id, bounty["maintainer_account"], "refund_expired", {"id": bounty_id})
                bounty["refund_receipt"] = receipt
            confirmed = self.rpc.view(signer.contract, "get_bounty", {"id": bounty_id})
            if confirmed["status"] != "Refunded":
                raise GuardError("Refund transfer has not confirmed success. Reconcile its original operation.")
            return self.store.save(bounty, "REFUNDED", "refunded", {"principal_yocto": bounty["amount_yocto"], "storage_and_gas_refunded": False})
