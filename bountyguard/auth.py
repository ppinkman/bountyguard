"""Local-session authentication. GitHub tokens remain in process memory only."""
import hashlib
import secrets
import threading
import time

from .domain import GuardError
from .github import GitHub


class Sessions:
    def __init__(self, github_factory=GitHub):
        self.factory = github_factory
        self.sessions = {}; self.lock = threading.RLock()

    def login(self, token):
        github = self.factory(token)
        actor = github.me()
        raw, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        value = {"actor": actor, "csrf": csrf, "github": github, "expires_at": time.time() + 3600}
        with self.lock:
            self.sessions = {k: v for k, v in self.sessions.items() if v["expires_at"] > time.time()}
            if len(self.sessions) >= 100:
                raise GuardError("Local session limit reached.", 429)
            self.sessions[hashlib.sha256(raw.encode()).hexdigest()] = value
        return raw, value

    def get(self, raw):
        with self.lock:
            value = self.sessions.get(hashlib.sha256((raw or "").encode()).hexdigest())
        if not value or value["expires_at"] <= time.time():
            raise GuardError("Sign in with GitHub to continue.", 401)
        return value

    def logout(self, raw):
        with self.lock:
            self.sessions.pop(hashlib.sha256((raw or "").encode()).hexdigest(), None)
