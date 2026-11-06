"""Bounded source edits and disposable, credential-free Python test execution."""
import difflib
import os
from pathlib import PurePosixPath
import re
import shutil
import subprocess
import uuid

from .verifier import SENSITIVE_NAMES


class IsolationError(Exception):
    pass


SECRET = re.compile(
    r"(?:github_pat_[A-Za-z0-9_]+|gh[pousr]_[A-Za-z0-9]+|"
    r"sk-[A-Za-z0-9_-]{16,}|ed25519:[1-9A-HJ-NP-Za-km-z]{40,}|"
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----)"
)


def safe_path(path):
    parts = path.split("/")
    reserved = {"CON", "PRN", "AUX", "NUL", *(f"{prefix}{n}" for prefix in ("COM", "LPT") for n in range(10))}
    return all(re.fullmatch(r"[A-Za-z0-9_.-]+", p) and not p.endswith(".")
               and p.split(".")[0].upper() not in reserved and p.lower() != ".git" for p in parts)


def editable(path):
    name = PurePosixPath(path).name
    return (safe_path(path) and re.fullmatch(r"(?:bountyguard|tools|tests)/[A-Za-z0-9_/-]+\.py", path)
            and name not in SENSITIVE_NAMES and name != "__init__.py"
            and not name.startswith("requirements"))


def scan_edits(original, edits, secrets):
    if not isinstance(edits, dict) or not edits or not edits.keys() <= original.keys():
        raise IsolationError("Model returned files outside the approved change set.")
    changed = {}
    size = 0
    for path, content in edits.items():
        if not editable(path) or not isinstance(content, str) or "\x00" in content or "\r" in content:
            raise IsolationError("Model returned a protected path or unsupported file content.")
        before = original[path] or ""
        if content == before or not content.strip():
            raise IsolationError("Model must provide a nonempty change without deleting a file.")
        delta = "\n".join(difflib.unified_diff(before.splitlines(), content.splitlines(), n=0))
        size += len(delta.encode("utf-8"))
        if len(content.encode("utf-8")) > 16_000 or SECRET.search(content) or any(s and s in content for s in secrets):
            raise IsolationError("Candidate contains a credential pattern or exceeds the file limit.")
        changed[path] = content
    if size > 12_000:
        raise IsolationError("Candidate exceeds the change size limit.")
    return changed


class DockerTests:
    TEST = ("python", "-B", "-m", "unittest", "discover", "-s", "tests")

    def __init__(self, image, *, timeout=120):
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", image):
            raise IsolationError("Use a trusted local Linux Docker image ID (sha256:...).")
        self.image = image
        self.timeout = timeout
        self.docker = shutil.which("docker")
        if not self.docker:
            raise IsolationError("Docker is required before the Agent can claim a bounty.")
        names = {"PATH", "SYSTEMROOT", "WINDIR", "PATHEXT", "TEMP", "TMP", "HOME", "USERPROFILE"}
        self.env = {key: value for key, value in os.environ.items() if key.upper() in names}

    def command(self, name, args, workspace=None):
        command = [self.docker, "run", "--rm", "--pull=never", "--name", name,
                   "--platform=linux", "--network=none", "--ipc=none", "--read-only",
                   "--log-driver=none",
                   "--cap-drop=ALL", "--security-opt=no-new-privileges", "--user=65534:65534",
                   "--memory=512m", "--cpus=1", "--pids-limit=64",
                   "--tmpfs", "/tmp:rw,nosuid,nodev,noexec,size=64m,mode=1777",
                   "--env", "HOME=/tmp", "--env", "PYTHONDONTWRITEBYTECODE=1",
                   "--entrypoint", args[0]]
        # Docker's client configuration can otherwise inject credential-bearing proxy URLs.
        for proxy in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "FTP_PROXY"):
            command += ["--env", proxy + "=", "--env", proxy.lower() + "="]
        if workspace is not None:
            source = str(workspace.resolve())
            if "," in source:
                raise IsolationError("Workspace path contains a Docker mount delimiter.")
            command += ["--mount", f"type=bind,source={source},target=/work,readonly", "--workdir", "/work"]
        return command + [self.image, *args[1:]]

    def run(self, args, workspace=None):
        name = "bountyguard-demo-" + uuid.uuid4().hex
        try:
            result = subprocess.run(self.command(name, args, workspace), env=self.env,
                                    cwd=os.path.dirname(self.docker), stdin=subprocess.DEVNULL,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=self.timeout)
        except (OSError, subprocess.TimeoutExpired):
            try:
                subprocess.run([self.docker, "rm", "-f", name], env=self.env, cwd=os.path.dirname(self.docker),
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
            except (OSError, subprocess.TimeoutExpired):
                pass
            raise IsolationError("The isolated test process could not finish safely.") from None
        if result.returncode in (125, 126, 127):
            raise IsolationError("Docker could not run the isolated test process.")
        return result.returncode == 0

    def check(self):
        probe = ("import os, httpx2, mcp, cryptography, fastapi, uvicorn; "
                 "assert os.geteuid() != 0; "
                 "assert not (set(os.environ) & {'GITHUB_TOKEN', 'NEAR_AI_API_KEY', "
                 "'BOUNTYGUARD_AGENT_SEED', 'BOUNTYGUARD_AGENT_GITHUB_TOKEN', "
                 "'BOUNTYGUARD_CODING_API_KEY', 'BOUNTYGUARD_MAINTAINER_GITHUB_TOKEN'})")
        if not self.run(("python", "-B", "-c", probe)):
            raise IsolationError("The local test image did not pass the isolation or dependency check.")

    def test(self, workspace):
        if os.name != "nt":
            # The container runs as nobody. Only this disposable checkout is
            # made readable, never its parent (which holds private state).
            workspace.chmod(0o755)
            for path in workspace.rglob("*"):
                path.chmod(0o755 if path.is_dir() else 0o644)
        return self.run(self.TEST, workspace)
