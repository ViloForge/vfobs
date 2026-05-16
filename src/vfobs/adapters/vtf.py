"""VtfClient — Adapter wrapping vtaskforge's HTTP/JSON API behind a
typed vfobs interface (plan §D2).

Adapter pattern: the external interface (vtaskforge REST + bearer
auth) is adapted to vfobs's internal typed domain
(WhoamiPrincipal / WorkgraphMetadata / TaskMetadata projections).
Verifier V14: this is a genuine inter-interface adapter, not the
WG1-F4 pattern-theater class.
"""

from __future__ import annotations

import httpx

from vfobs.adapters.dto import TaskMetadata, WhoamiPrincipal, WorkgraphMetadata
from vfobs.config import Settings


class VtfAuthError(Exception):
    """vtaskforge rejected the bearer token (401)."""


class VtfClient:
    def __init__(
        self, settings: Settings, http: httpx.AsyncClient | None = None
    ) -> None:
        # Deviation D-T0-1: enforce the AC-T0-6 "must be set in prod"
        # guarantee here rather than via a strictly-required Settings
        # field (which would regress the WG1 test fixtures that build
        # Settings(...) directly). Production VtfClient is constructed
        # in main.py:_lifespan, so an unconfigured prod app fails to
        # start — the intended guarantee, preserved.
        if settings.vtaskforge_url is None:
            raise ValueError(
                "VFOBS_VTASKFORGE_URL must be set (vfobs read API needs "
                "vtaskforge for whoami + resource metadata)"
            )
        self._base = str(settings.vtaskforge_url).rstrip("/")
        self._timeout = settings.vtaskforge_timeout_seconds
        self._http = http or httpx.AsyncClient(timeout=self._timeout)

    @staticmethod
    def _auth(token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    async def whoami(self, token: str) -> WhoamiPrincipal:
        r = await self._http.get(
            f"{self._base}/v2/auth/whoami", headers=self._auth(token)
        )
        if r.status_code == 401:
            raise VtfAuthError("invalid vtf token")
        r.raise_for_status()
        return WhoamiPrincipal.model_validate(r.json())

    async def get_workgraph(
        self, workgraph_id: str, token: str
    ) -> WorkgraphMetadata | None:
        r = await self._http.get(
            f"{self._base}/v2/workgraphs/{workgraph_id}/",
            headers=self._auth(token),
        )
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return WorkgraphMetadata.model_validate(r.json())

    async def get_task(self, task_id: str, token: str) -> TaskMetadata | None:
        r = await self._http.get(
            f"{self._base}/v2/tasks/{task_id}/", headers=self._auth(token)
        )
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return TaskMetadata.model_validate(r.json())

    async def aclose(self) -> None:
        await self._http.aclose()
