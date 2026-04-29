"""CRM tool definitions: customer + order operations."""

from collections.abc import Awaitable, Callable

from gateway.tools.registry import ToolMeta
from gateway.tools.upstream import UpstreamClient


def build_crm_tools(
    client: UpstreamClient,
) -> list[tuple[ToolMeta, Callable[..., Awaitable[dict]]]]:
    async def get_customer(customer_id: str) -> dict:
        return await client.get(f"/customers/{customer_id}")

    async def list_orders(customer_id: str) -> dict:
        return await client.get("/orders", params={"customer_id": customer_id})

    async def update_order(order_id: str, status: str) -> dict:
        return await client.patch(f"/orders/{order_id}", json={"status": status})

    return [
        (
            ToolMeta(
                name="get_customer",
                description="Fetch customer profile by ID",
                input_schema={
                    "type": "object",
                    "properties": {"customer_id": {"type": "string"}},
                    "required": ["customer_id"],
                },
                destructive=False,
            ),
            get_customer,
        ),
        (
            ToolMeta(
                name="list_orders",
                description="List orders for a customer",
                input_schema={
                    "type": "object",
                    "properties": {"customer_id": {"type": "string"}},
                    "required": ["customer_id"],
                },
                destructive=False,
            ),
            list_orders,
        ),
        (
            ToolMeta(
                name="update_order",
                description="Update order status",
                input_schema={
                    "type": "object",
                    "properties": {
                        "order_id": {"type": "string"},
                        "status": {"type": "string"},
                    },
                    "required": ["order_id", "status"],
                },
                destructive=False,
            ),
            update_order,
        ),
    ]
