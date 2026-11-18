"""Token auth with a pluggable store so per-user access can be added later."""
from __future__ import annotations

import hmac
import os
from dataclasses import dataclass
from typing import Mapping, Protocol

MIN_TOKEN_LENGTH = 16


@dataclass(frozen=True)
class User:
    id: str


class TokenStore(Protocol):
    def resolve(self, token: str) -> User | None: ...


class EnvTokenStore:
    def __init__(self, env: Mapping[str, str] | None = None) -> None:
        if env is None:
            env = os.environ
        entries: list[tuple[str, User]] = []

        single = (env.get("APP_TOKEN") or "").strip()
        if single:
            entries.append((single, User("owner")))

        for item in (env.get("APP_TOKENS") or "").split(","):
            item = item.strip()
            if not item or ":" not in item:
                continue
            name, token = item.split(":", 1)
            name, token = name.strip(), token.strip()
            if not name or not token:
                continue
            entries.append((token, User(name)))

        for i, (token, user) in enumerate(entries):
            if len(token) < MIN_TOKEN_LENGTH:
                raise ValueError(
                    f"Configured token for user {user.id!r} (entry {i + 1}) is "
                    f"shorter than {MIN_TOKEN_LENGTH} characters"
                )

        self._entries = [(t.encode("utf-8"), u) for t, u in entries]
        self.configured: bool = bool(self._entries)

    def resolve(self, token: str | None) -> User | None:
        if not token or not self._entries:
            return None
        candidate = token.encode("utf-8")
        match: User | None = None
        for known, user in self._entries:
            if hmac.compare_digest(candidate, known) and match is None:
                match = user
        return match


def parse_bearer(header: str | None) -> str | None:
    if not header:
        return None
    scheme, sep, token = header.partition(" ")
    if not sep or scheme.lower() != "bearer" or not token:
        return None
    return token
