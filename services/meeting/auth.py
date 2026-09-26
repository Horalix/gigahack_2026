"""Local account and server-side session handling."""

import hashlib
import secrets
import threading
import time
from collections import defaultdict, deque

from argon2 import PasswordHasher, exceptions


SESSION_COOKIE = "mom_session"
SESSION_SECONDS = 8 * 60 * 60
ALLOWED_ROLES = {"clinician", "reviewer", "administrator"}
_USERNAME_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789._-")


class AuthService:
    def __init__(self, store):
        self.store = store
        self.passwords = PasswordHasher()
        self._dummy_hash = self.passwords.hash(secrets.token_urlsafe(24))
        self._failed_logins: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    @staticmethod
    def normalize_username(username: str) -> str:
        value = username.strip().casefold()
        if not 3 <= len(value) <= 64 or any(ch not in _USERNAME_CHARS for ch in value):
            raise ValueError("Username must be 3–64 characters: letters, numbers, dot, underscore or hyphen")
        return value

    @staticmethod
    def validate_password(password: str) -> None:
        if len(password) < 12 or len(password) > 256:
            raise ValueError("Password must be between 12 and 256 characters")

    def create_user(self, organization_id: str, username: str, password: str, role: str, *, bootstrap: bool = False) -> dict:
        username = self.normalize_username(username)
        self.validate_password(password)
        if role not in ALLOWED_ROLES:
            raise ValueError("Unsupported account role")
        encoded = self.passwords.hash(password)
        return self.store.create_user(organization_id, username, encoded, role, bootstrap=bootstrap)

    def authenticate_password(self, username: str, password: str, client_ip: str) -> tuple[str, dict] | None:
        now = time.monotonic()
        with self._lock:
            failures = self._failed_logins[client_ip]
            while failures and now - failures[0] >= 60:
                failures.popleft()
            if len(failures) >= 5:
                return None

        try:
            username = self.normalize_username(username)
        except ValueError:
            username = ""
        user = self.store.get_user_by_username(username) if username else None
        encoded = user["password_hash"] if user and user["active"] else self._dummy_hash
        valid = False
        try:
            valid = self.passwords.verify(encoded, password)
        except (exceptions.VerifyMismatchError, exceptions.VerificationError, exceptions.InvalidHashError):
            pass

        if not user or not user["active"] or not valid:
            with self._lock:
                self._failed_logins[client_ip].append(time.monotonic())
            return None

        if self.passwords.check_needs_rehash(encoded):
            self.store.update_password_hash(user["id"], self.passwords.hash(password))
        with self._lock:
            self._failed_logins.pop(client_ip, None)
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode("ascii")).hexdigest()
        self.store.create_session(token_hash, user["id"], SESSION_SECONDS)
        return token, self.public_user(user)

    def authenticate_session(self, token: str | None) -> dict | None:
        if not token or len(token) > 128:
            return None
        token_hash = hashlib.sha256(token.encode("ascii", errors="ignore")).hexdigest()
        return self.store.get_session_user(token_hash)

    def logout(self, token: str | None) -> None:
        if token:
            token_hash = hashlib.sha256(token.encode("ascii", errors="ignore")).hexdigest()
            self.store.revoke_session(token_hash)

    @staticmethod
    def public_user(user: dict) -> dict:
        return {"id": user["id"], "username": user["username"], "role": user["role"],
                "organizationId": user["organization_id"]}
