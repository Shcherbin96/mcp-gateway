"""Locust smoke load test for the MCP Gateway.

At test start we extract the seeded OAuth client_id/secret from the gateway
container logs (the ``make seed`` step prints them on startup) and exchange
them for a bearer token. Reusing the seeded credentials means our load
generator hits a real agent that exists in the gateway DB and has the
right role/permissions — registering a fresh client at the IdP would
fail policy checks since no Agent row backs it.

Override with explicit env vars when running outside CI:
    LOADTEST_CLIENT_ID=client-... LOADTEST_CLIENT_SECRET=... locust ...

Run locally:
    locust -f loadtest/locustfile.py --host http://localhost:8000

Headless smoke (matches CI):
    locust -f loadtest/locustfile.py --headless \
        -u 10 -r 5 -t 30s --host http://localhost:8000 --only-summary
"""

import os
import re
import subprocess

import httpx
from locust import HttpUser, between, events, task

IDP = os.environ.get("IDP_URL", "http://localhost:9000")


def _seeded_creds() -> tuple[str, str]:
    cid = os.environ.get("LOADTEST_CLIENT_ID")
    sec = os.environ.get("LOADTEST_CLIENT_SECRET")
    if cid and sec:
        return cid, sec
    out = subprocess.check_output(  # noqa: S607 — `docker` resolved on PATH at CI time
        ["docker", "compose", "-f", "docker-compose.test.yml", "logs", "gateway"],
        text=True,
        timeout=10,
    )
    cid_m = re.search(r"OAuth client_id:\s*(\S+)", out)
    sec_m = re.search(r"OAuth client_secret:\s*(\S+)", out)
    if not cid_m or not sec_m:
        raise RuntimeError("seed credentials not found in gateway logs")
    return cid_m.group(1), sec_m.group(1)


@events.test_start.add_listener
def fetch_token(environment, **kwargs):
    cid, sec = _seeded_creds()
    with httpx.Client() as c:
        tok = c.post(
            f"{IDP}/token",
            data={
                "grant_type": "client_credentials",
                "client_id": cid,
                "client_secret": sec,
            },
        ).json()
        environment.parsed_options.token = tok["access_token"]


class GatewayUser(HttpUser):
    wait_time = between(0.1, 0.5)

    def on_start(self):
        self.headers = {"Authorization": f"Bearer {self.environment.parsed_options.token}"}

    @task(3)
    def get_customer(self):
        self.client.post(
            "/mcp/call/get_customer",
            json={"customer_id": "C001"},
            headers=self.headers,
            name="get_customer",
        )

    @task(1)
    def list_orders(self):
        self.client.post(
            "/mcp/call/list_orders",
            json={"customer_id": "C001"},
            headers=self.headers,
            name="list_orders",
        )
