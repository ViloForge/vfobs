import hashlib

import pytest
from fastapi import HTTPException

from vfobs.adapters.dto import WhoamiPrincipal
from vfobs.adapters.vtf import VtfAuthError
from vfobs.api.read_auth import (
    Principal,
    StaticPrincipalAuth,
    VtfTokenAuth,
    _hash_prefix,
)


class FakeVtf:
    """Stub VtfClient — counts whoami calls; no network."""

    def __init__(self, principal: WhoamiPrincipal | None = None) -> None:
        self.calls = 0
        self._principal = principal or WhoamiPrincipal(
            user_id="op", display_name="Op"
        )
        self.raise_auth = False

    async def whoami(self, token: str) -> WhoamiPrincipal:
        self.calls += 1
        if self.raise_auth:
            raise VtfAuthError("bad")
        return self._principal


@pytest.mark.unit
async def test_cold_miss_calls_whoami_warm_hit_does_not() -> None:
    vtf = FakeVtf()
    auth = VtfTokenAuth(vtf, ttl_seconds=60)  # type: ignore[arg-type]

    p1 = await auth.verify("tok")
    p2 = await auth.verify("tok")

    assert p1 == p2 == Principal(user_id="op", display_name="Op")
    assert vtf.calls == 1  # second call served from cache


@pytest.mark.unit
async def test_post_ttl_expiry_refetches(monkeypatch: pytest.MonkeyPatch) -> None:
    vtf = FakeVtf()
    auth = VtfTokenAuth(vtf, ttl_seconds=60)  # type: ignore[arg-type]

    clock = {"t": 1000.0}
    monkeypatch.setattr(
        "vfobs.api.read_auth.time.monotonic", lambda: clock["t"]
    )

    await auth.verify("tok")
    assert vtf.calls == 1
    clock["t"] += 59  # still within TTL
    await auth.verify("tok")
    assert vtf.calls == 1
    clock["t"] += 2  # now 61s > TTL
    await auth.verify("tok")
    assert vtf.calls == 2


@pytest.mark.unit
async def test_cache_key_is_hash_prefix_not_raw_token() -> None:
    vtf = FakeVtf()
    auth = VtfTokenAuth(vtf)  # type: ignore[arg-type]
    raw = "super-secret-token"
    await auth.verify(raw)

    keys = list(auth._cache.keys())
    assert raw not in keys
    assert keys == [hashlib.sha256(raw.encode()).hexdigest()[:16]]
    assert _hash_prefix(raw) == keys[0]


@pytest.mark.unit
async def test_missing_token_is_401() -> None:
    auth = VtfTokenAuth(FakeVtf())  # type: ignore[arg-type]
    with pytest.raises(HTTPException) as ei:
        await auth.verify(None)
    assert ei.value.status_code == 401


@pytest.mark.unit
async def test_upstream_auth_error_maps_to_401() -> None:
    vtf = FakeVtf()
    vtf.raise_auth = True
    auth = VtfTokenAuth(vtf)  # type: ignore[arg-type]
    with pytest.raises(HTTPException) as ei:
        await auth.verify("tok")
    assert ei.value.status_code == 401


@pytest.mark.unit
async def test_static_principal_auth_returns_fixed_for_any_token() -> None:
    fixed = Principal(user_id="stub", display_name="Stub")
    auth = StaticPrincipalAuth(fixed)
    assert await auth.verify("anything") is fixed
    assert await auth.verify(None) is fixed
