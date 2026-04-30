"""Seed CLI: bootstrap a demo tenant, roles, agent, and OAuth client at the IdP."""

import asyncio
import sys

import httpx
from sqlalchemy import select

from gateway.config import get_settings
from gateway.db.models import Agent, Role, RolePermission, Tenant
from gateway.db.session import SessionLocal


async def seed_demo() -> None:
    settings = get_settings()

    async with SessionLocal() as s:
        existing = (
            await s.execute(select(Tenant).where(Tenant.name == "demo"))
        ).scalar_one_or_none()
        if existing:
            tenant = existing
            print(f"Tenant exists: {tenant.id}")
        else:
            tenant = Tenant(name="demo")
            s.add(tenant)
            await s.flush()
            print(f"Created tenant: {tenant.id}")

        # Roles
        roles: dict[str, Role] = {}
        for rname in ("support_agent", "readonly_analyst", "finance_admin"):
            r = (
                await s.execute(select(Role).where(Role.tenant_id == tenant.id, Role.name == rname))
            ).scalar_one_or_none()
            if not r:
                r = Role(tenant_id=tenant.id, name=rname)
                s.add(r)
                await s.flush()
            roles[rname] = r

        # Permissions per role
        perms: dict[str, list[tuple[str, bool]]] = {
            "support_agent": [
                ("get_customer", False),
                ("list_orders", False),
                ("update_order", False),
                ("refund_payment", True),
            ],
            "readonly_analyst": [
                ("get_customer", False),
                ("list_orders", False),
            ],
            "finance_admin": [
                ("refund_payment", True),
                ("charge_card", True),
            ],
        }
        for rname, plist in perms.items():
            for tool, req_app in plist:
                existing_p = (
                    await s.execute(
                        select(RolePermission).where(
                            RolePermission.role_id == roles[rname].id,
                            RolePermission.tool_name == tool,
                        )
                    )
                ).scalar_one_or_none()
                if not existing_p:
                    s.add(
                        RolePermission(
                            role_id=roles[rname].id,
                            tool_name=tool,
                            requires_approval=req_app,
                        )
                    )

        # Agent
        agent_name = "demo-support-bot"
        agent = (
            await s.execute(
                select(Agent).where(Agent.tenant_id == tenant.id, Agent.name == agent_name)
            )
        ).scalar_one_or_none()
        if not agent:
            agent = Agent(
                tenant_id=tenant.id,
                name=agent_name,
                role_id=roles["support_agent"].id,
                owner_email="me@example.com",
            )
            s.add(agent)
            await s.flush()
        await s.commit()

        # Register OAuth client at IdP
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{settings.oauth_issuer}/register",
                json={
                    "client_name": agent_name,
                    "tenant_id": str(tenant.id),
                    "agent_id": str(agent.id),
                    "scopes": [
                        "tool:get_customer",
                        "tool:list_orders",
                        "tool:update_order",
                        "tool:refund_payment",
                    ],
                },
            )
            resp.raise_for_status()
            creds = resp.json()
            print(f"OAuth client_id: {creds['client_id']}")
            print(f"OAuth client_secret: {creds['client_secret']}")
            print("\nObtain token:")
            print(f"  curl -X POST {settings.oauth_issuer}/token \\")
            print("    -d 'grant_type=client_credentials' \\")
            print(f"    -d 'client_id={creds['client_id']}' \\")
            print(f"    -d 'client_secret={creds['client_secret']}'")


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] != "seed":
        print("Usage: python -m gateway.cli seed")
        sys.exit(1)
    asyncio.run(seed_demo())


if __name__ == "__main__":
    main()
