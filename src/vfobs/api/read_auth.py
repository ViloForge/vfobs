"""ReadAuth — Strategy for read-API authentication (OIQ3 read-half).

Mirrors the write-side `IngestAuth` Strategy in `api/auth.py`, but
`verify` is async because the v1 strategy makes a network call to
vtaskforge. v1 ships `VtfTokenAuth` (vtf-token piggyback with a
60s sha256-prefix-keyed TTL cache) + `StaticPrincipalAuth` (test
substitute). v2 can add OIDC / web-user auth by plugging a new
strategy at app construction — no endpoint changes.
"""

from __future__ import annotations

import hashlib
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from vfobs.adapters.vtf import VtfAuthError, VtfClient

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Principal:
    user_id: str
    display_name: str | None = None


def _hash_prefix(token: str) -> str:
    """sha256 hex prefix — the ONLY on-wire form of the token outside
    the original Authorization header. The raw token is never logged,
    never used as a cache key."""
    return hashlib.sha256(token.encode()).hexdigest()[:16]


class ReadAuth(ABC):
    @abstractmethod
    async def verify(self, token: str | None) -> Principal:
        """Return the resolved Principal, or raise HTTPException(401)."""


class VtfTokenAuth(ReadAuth):
    def __init__(self, vtf: VtfClient, ttl_seconds: int = 60) -> None:
        self._vtf = vtf
        self._ttl = ttl_seconds
        self._cache: dict[str, tuple[Principal, float]] = {}

    async def verify(self, token: str | None) -> Principal:
        if not token:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED, "Missing bearer token"
            )
        key = _hash_prefix(token)
        now = time.monotonic()
        cached = self._cache.get(key)
        if cached is not None and (now - cached[1]) < self._ttl:
            return cached[0]
        try:
            who = await self._vtf.whoami(token)
        except VtfAuthError:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED, "Invalid bearer token"
            ) from None
        principal = Principal(
            user_id=who.user_id, display_name=who.display_name
        )
        self._cache[key] = (principal, now)
        return principal


class StaticPrincipalAuth(ReadAuth):
    """Test substitute — returns a fixed principal for any token
    (including None). Used by all non-auth-focused WG2 tests."""

    def __init__(self, principal: Principal) -> None:
        self._principal = principal

    async def verify(self, token: str | None) -> Principal:
        return self._principal


async def get_read_principal(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> Principal:
    auth: ReadAuth = request.app.state.read_auth
    return await auth.verify(creds.credentials if creds else None)
