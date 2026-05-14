import hmac
from abc import ABC, abstractmethod

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from vfobs.config import Settings

bearer = HTTPBearer(auto_error=False)


class IngestAuth(ABC):
    """Strategy interface for write-API authentication.

    v1 ships `StaticTokenAuth` (shared service-account token). v2 can
    add MultiTokenAuth (per-pod) or MutualTLSAuth without changing the
    endpoint shape — just plug a different strategy at app construction.
    """

    @abstractmethod
    def verify(self, token: str | None) -> str:
        """Return the resolved principal name on success.

        Raises fastapi.HTTPException(401) on any failure mode (missing
        token, wrong token, malformed token)."""


class StaticTokenAuth(IngestAuth):
    def __init__(self, settings: Settings) -> None:
        self._expected = settings.ingest_token.get_secret_value()

    def verify(self, token: str | None) -> str:
        if not token:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
        if not hmac.compare_digest(token, self._expected):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid bearer token")
        return "controller"


async def get_principal(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> str:
    auth: IngestAuth = request.app.state.ingest_auth
    return auth.verify(creds.credentials if creds else None)
