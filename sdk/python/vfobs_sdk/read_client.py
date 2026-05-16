"""Thin typed read client over the WG2 vfobs read API. Read-side
degradable (D-T0-1 lineage): a transient read failure raises
ReadUnavailable for the caller to degrade gracefully, never a
bare crash deep in httpx.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx


class ReadUnavailable(Exception):
    """vfobs read API unreachable / errored this poll."""


@dataclass(frozen=True)
class StoredEventView:
    id: int
    type: str
    timestamp: str  # ISO 8601 (as returned by the API)
    data: dict


class ReadClient:
    def __init__(
        self, base_url: str, token: str, *, timeout: float = 5.0,
        http: httpx.Client | None = None,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {token}"}
        self._timeout = timeout
        self._http = http or httpx.Client(timeout=timeout)

    def task_events(
        self, task_id: str, *, page_limit: int = 1000
    ) -> list[StoredEventView]:
        """All events for a task, id ASC (follows the cursor)."""
        out: list[StoredEventView] = []
        from_id: int | None = None
        try:
            while True:
                params: dict = {"limit": page_limit}
                if from_id is not None:
                    params["from_id"] = from_id
                r = self._http.get(
                    f"{self._base}/tasks/{task_id}/events",
                    params=params, headers=self._headers,
                    timeout=self._timeout,
                )
                r.raise_for_status()
                body = r.json()
                for se in body["events"]:
                    ev = se["event"]
                    out.append(
                        StoredEventView(
                            id=se["id"], type=ev["type"],
                            timestamp=ev["timestamp"], data=ev.get("data", {}),
                        )
                    )
                nxt = body.get("next_from_id")
                if nxt is None:
                    return out
                from_id = nxt
        except Exception as exc:  # network / 4xx / 5xx / shape
            raise ReadUnavailable(str(exc)) from exc

    def close(self) -> None:
        self._http.close()
