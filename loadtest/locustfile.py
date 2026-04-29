"""Locust smoke load test for the MCP Gateway.

At test start we register a client with the mock IdP and obtain a bearer
token via the client_credentials grant. The token is stashed onto the
shared ``environment.parsed_options`` namespace so each spawned
``GatewayUser`` can pick it up in ``on_start``.

Run locally:
    locust -f loadtest/locustfile.py --host http://localhost:8000

Headless smoke (matches CI):
    locust -f loadtest/locustfile.py --headless \
        -u 10 -r 5 -t 30s --host http://localhost:8000 --only-summary
"""

import os

import httpx
from locust import HttpUser, between, events, task


IDP = os.environ.get("IDP_URL", "http://localhost:9000")


@events.test_start.add_listener
def fetch_token(environment, **kwargs):
    with httpx.Client() as c:
        reg = c.post(f"{IDP}/register", json={
            "client_name": "loadtest", "tenant_id": "00000000-0000-0000-0000-000000000000",
            "scopes": ["tool:get_customer", "tool:list_orders"],
        }).json()
        tok = c.post(f"{IDP}/token", data={
            "grant_type": "client_credentials",
            "client_id": reg["client_id"], "client_secret": reg["client_secret"],
        }).json()
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
