"""Bounty-specific types; these do not import or mutate ProofPay."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

YOCTO = 10**24
STORAGE_YOCTO = 10**22
MAX_BOUNTY_YOCTO = 10**22  # 0.01 tNEAR, separate from storage and gas.


class GuardError(Exception):
    def __init__(self, message: str, status: int = 409):
        super().__init__(message)
        self.status = status


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value) -> str:
    raw = value if isinstance(value, bytes) else canonical(value).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def github_url(value: str, kind: str) -> tuple[str, int]:
    url = urlsplit(value)
    match = re.fullmatch(r"/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/" + kind + r"/([1-9][0-9]*)/?", url.path)
    if url.scheme != "https" or url.netloc != "github.com" or url.query or url.fragment or not match:
        raise GuardError("Use an exact https://github.com/owner/repository/" + kind + "/number URL.", 422)
    owner, repo, number = match.groups()
    if owner in (".", "..") or repo in (".", ".."):
        raise GuardError("Invalid repository name.", 422)
    return owner + "/" + repo, int(number)


def testnet_account(value: str) -> str:
    if not re.fullmatch(r"[a-z0-9]+(?:[._-][a-z0-9]+)*\.testnet", value) or len(value) > 64:
        raise GuardError("This development release accepts named .testnet accounts only.", 422)
    return value


def amount_yocto(value: str) -> int:
    try:
        number = Decimal(value)
        atoms = number * YOCTO
        if not number.is_finite() or atoms != atoms.to_integral_value() or not 0 < atoms <= MAX_BOUNTY_YOCTO:
            raise ValueError()
        return int(atoms)
    except (ValueError, InvalidOperation):
        raise GuardError("Bounty must be positive and at most 0.01 tNEAR; storage and gas are separate.", 422) from None


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateBounty(StrictModel):
    issue_url: str = Field(max_length=300)
    amount: str = "0.005"
    deadline: int
    workflow_path: str = ".github/workflows/ci.yml"
    required_checks: list[str] = Field(min_length=1, max_length=8)
    source_paths: list[str] = Field(default_factory=lambda: ["src/"], min_length=1, max_length=10)

    @field_validator("workflow_path")
    @classmethod
    def workflow(cls, value):
        if not re.fullmatch(r"\.github/workflows/[A-Za-z0-9_.-]+\.ya?ml", value):
            raise ValueError("Choose a workflow file under .github/workflows/.")
        return value

    @field_validator("required_checks", "source_paths")
    @classmethod
    def safe_list(cls, values):
        if len(set(values)) != len(values) or any(not v.strip() or len(v) > 120 or ".." in v or "\\" in v or v.startswith("/") for v in values):
            raise ValueError("Use unique, nonempty relative paths or check names.")
        return values


def issue_context(issue: dict, repo_id: int) -> dict:
    # Closing an issue on merge is expected; the title/body remain pinned.
    return {"repo_id": repo_id, "number": issue["number"], "title": issue["title"], "body": issue.get("body") or ""}
