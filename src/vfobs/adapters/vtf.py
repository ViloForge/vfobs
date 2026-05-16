"""VtfClient — Adapter wrapping vtaskforge's REAL HTTP API.

GROUNDED (kb feedback-external-contract-grounding). The original
WG2 design invented `GET /v2/auth/whoami` + `Bearer` auth + a
`/v2/workgraphs/` path — none exist. Corrected against vtaskforge
source + live API:

- Auth scheme: `Authorization: Token <t>` (DRF) —
  vtf-sdk-python/vtf_sdk/transport.py:58. NOT Bearer.
- Token validation: `GET /v2/auth/validate/` —
  src/vtaskforge/urls.py:133 + src/prefs/views.py:100
  (IsAuthenticated ⇒ 200 identity / 401 invalid). Live-confirmed:
  bogus/no/Bearer-scheme token all → 401.
- "workgraph" == milestone ⇒ `GET /v2/milestones/<id>/`.
- task ⇒ `GET /v2/tasks/<id>/` (exists; was already correct).

Metadata calls are FAIL-SAFE: any non-200 / non-JSON / network
error ⇒ None (the read endpoints degrade to the vfobs half; they
never 500 on a vtaskforge hiccup).
"""

from __future__ import annotations

import httpx

from vfobs.adapters.dto import TaskMetadata, VtfPrincipal, WorkgraphMetadata
from vfobs.config import Settings


class VtfAuthError(Exception):
    """vtaskforge rejected the token, or it could not be validated."""


class VtfClient:
    def __init__(
        self, settings: Settings, http: httpx.AsyncClient | None = None
    ) -> None:
        if settings.vtaskforge_url is None:
            raise ValueError(
                "VFOBS_VTASKFORGE_URL must be set (read API needs "
                "vtaskforge to validate tokens)"
            )
        self._base = str(settings.vtaskforge_url).rstrip("/")
        self._timeout = settings.vtaskforge_timeout_seconds
        self._http = http or httpx.AsyncClient(timeout=self._timeout)

    @staticmethod
    def _auth(token: str) -> dict[str, str]:
        # DRF TokenAuthentication scheme — NOT Bearer.
        return {"Authorization": f"Token {token}"}

    async def validate_token(self, token: str) -> VtfPrincipal:
        """GET /v2/auth/validate/ — 200 ⇒ principal, anything else
        ⇒ VtfAuthError (deny). Never raises a non-VtfAuthError to
        the caller (read-auth must 401, never 500)."""
        try:
            r = await self._http.get(
                f"{self._base}/v2/auth/validate/",
                headers=self._auth(token),
            )
        except Exception as e:  # network/timeout — cannot validate
            raise VtfAuthError(f"vtaskforge unreachable: {e}") from None
        if r.status_code == 200:
            try:
                return VtfPrincipal.model_validate(r.json())
            except Exception as e:
                raise VtfAuthError(
                    f"validate returned unparseable 200: {e}"
                ) from None
        # 401 (invalid/missing/wrong-scheme) or any other status:
        # we could not affirmatively validate ⇒ deny.
        raise VtfAuthError(f"token not valid (status {r.status_code})")

    async def _get_json(self, path: str, token: str):
        """Fail-safe GET — returns parsed JSON dict or None on any
        non-200 / non-JSON / error. Never raises."""
        try:
            r = await self._http.get(
                f"{self._base}{path}", headers=self._auth(token)
            )
            if r.status_code != 200:
                return None
            return r.json()
        except Exception:
            return None

    async def get_workgraph(
        self, workgraph_id: str, token: str
    ) -> WorkgraphMetadata | None:
        data = await self._get_json(
            f"/v2/milestones/{workgraph_id}/", token
        )
        if not isinstance(data, dict):
            return None
        try:
            return WorkgraphMetadata.model_validate(data)
        except Exception:
            return None

    async def get_task(
        self, task_id: str, token: str
    ) -> TaskMetadata | None:
        data = await self._get_json(f"/v2/tasks/{task_id}/", token)
        if not isinstance(data, dict):
            return None
        try:
            return TaskMetadata.model_validate(data)
        except Exception:
            return None

    async def aclose(self) -> None:
        await self._http.aclose()
