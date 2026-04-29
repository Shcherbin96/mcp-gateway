"""Tests for ContextVar-based tenant scoping middleware."""

import asyncio
from uuid import uuid4

import pytest

from gateway.tenants.middleware import current_tenant, require_tenant, set_tenant

pytestmark = pytest.mark.unit


def test_set_get_tenant():
    tid = uuid4()
    set_tenant(tid)
    assert current_tenant() == tid


def test_require_raises_when_unset():
    set_tenant(None)
    with pytest.raises(RuntimeError):
        require_tenant()


async def test_isolated_per_task():
    tid_a = uuid4()
    tid_b = uuid4()

    async def task_a():
        set_tenant(tid_a)
        await asyncio.sleep(0.05)
        assert current_tenant() == tid_a

    async def task_b():
        set_tenant(tid_b)
        await asyncio.sleep(0.05)
        assert current_tenant() == tid_b

    await asyncio.gather(task_a(), task_b())
