"""Facts and policy are distinct from the model's advisory judgments."""
from pathlib import PurePosixPath
import re

from .domain import digest

SENSITIVE_NAMES = {"pyproject.toml", "pytest.ini", "tox.ini", "setup.cfg", "setup.py", "conftest.py", "package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "Cargo.toml", "Cargo.lock", "Makefile", "Dockerfile"}
INJECTION = re.compile(r"ignore.{0,40}(?:review|previous|instructions)|approve.{0,20}(?:payout|payment)|reveal.{0,20}(?:secret|key)", re.I)


def hard_checks(bounty, pr, files, issue, workflow, linked, ci):
    checks = []
    def add(name, passed, detail, manual=False):
        checks.append({"name": name, "passed": bool(passed), "detail": detail, "manual": manual})
    from .domain import issue_context
    add("repository", pr["base"]["repo"]["id"] == bounty["repo_id"], "PR base repository must match the funded repository; forks are allowed.")
    add("author", pr["user"]["id"] == bounty["claim"]["actor_id"], "PR author numeric GitHub ID must match the assigned claimant.")
    add("issue_context", digest(issue_context(issue, bounty["repo_id"])) == bounty["issue_hash"], "Issue title/body must match the agreed terms.")
    add("issue_link", any(r["number"] == bounty["issue_number"] and r["repository"]["databaseId"] == bounty["repo_id"] for r in linked), "GitHub closing-Issue references must include this Issue.")
    add("not_draft", not pr.get("draft"), "Draft pull requests cannot authorize payment.")
    add("workflow_source", workflow["sha"] == bounty["ci"]["workflow_blob_sha"], "Trusted workflow content must still match the agreed source.")
    sensitive, test_changes, removed_assertions, instructions = [], [], [], []
    source_changed = False
    for file in files:
        names = [file["filename"]] + ([file["previous_filename"]] if file.get("previous_filename") else [])
        for name in names:
            path = PurePosixPath(name)
            if name.startswith((".github/", "scripts/", "build/")) or path.name in SENSITIVE_NAMES or path.name.startswith("requirements") or path.suffix in (".lock", ".pth"):
                sensitive.append(name)
        filename, patch = file["filename"], file["patch"]
        is_test = filename.startswith(("tests/", "test/")) or PurePosixPath(filename).name.startswith("test_")
        if is_test:
            test_changes.append(filename)
            if re.search(r"(?m)^-(?!--).*\b(?:assert|assertEqual|assertTrue|raises|fail)\b", patch):
                removed_assertions.append(filename)
        added = [line[1:].strip() for line in patch.splitlines() if line.startswith("+") and line[1:].strip() and not line[1:].lstrip().startswith(("#", "//"))]
        removed = [line[1:].strip() for line in patch.splitlines() if line.startswith("-") and line[1:].strip() and not line[1:].lstrip().startswith(("#", "//"))]
        code_suffixes = {".py", ".rs", ".ts", ".tsx", ".js", ".jsx", ".go", ".java", ".c", ".h", ".cpp", ".sol", ".kt", ".swift", ".vue"}
        if any(filename.startswith(prefix) for prefix in bounty["source_paths"]) and PurePosixPath(filename).suffix in code_suffixes and added != removed:
            source_changed = True
        if INJECTION.search(patch):
            instructions.append(filename)
    add("source_change", source_changed, "A non-comment textual change is required under an agreed source path; this is not semantic correctness proof.")
    add("sensitive_paths", not sensitive, "Sensitive changes: " + ", ".join(sorted(set(sensitive))) if sensitive else "No sensitive configuration changes.", manual=True)
    add("test_integrity_signal", not removed_assertions, "Removed assertion signals: " + ", ".join(removed_assertions) if removed_assertions else "No removed-assertion signal. Ordinary test additions/changes are listed.", manual=True)
    add("review_manipulation_signal", not instructions, "Potential review-manipulation text: " + ", ".join(instructions) if instructions else "No configured review-manipulation signal; detection is incomplete.", manual=True)
    add("trusted_ci", ci["passed"], ci["reason"])
    hard_failed = any(not c["passed"] and not c["manual"] for c in checks)
    manual = any(not c["passed"] and c["manual"] for c in checks)
    return {"checks": checks, "test_changes": test_changes, "verdict": "FAIL" if hard_failed else "NEEDS_REVIEW" if manual else "PASS"}
