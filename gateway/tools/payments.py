"""Payment tool definitions: refunds + charges (with PAN redaction)."""

from collections.abc import Awaitable, Callable

from gateway.audit.redaction import redact_card_number
from gateway.tools.registry import ToolMeta
from gateway.tools.upstream import UpstreamClient


def build_payment_tools(
    client: UpstreamClient,
) -> list[tuple[ToolMeta, Callable[..., Awaitable[dict]]]]:
    async def refund_payment(customer_id: str, amount: float, reason: str | None = None) -> dict:
        return await client.post(
            "/refunds",
            json={"customer_id": customer_id, "amount": amount, "reason": reason},
        )

    async def charge_card(card_number: str, amount: float, customer_id: str | None = None) -> dict:
        return await client.post(
            "/charges",
            json={
                "card_number": card_number,
                "amount": amount,
                "customer_id": customer_id,
            },
        )

    return [
        (
            ToolMeta(
                name="refund_payment",
                description="Issue a refund to customer",
                input_schema={
                    "type": "object",
                    "properties": {
                        "customer_id": {"type": "string"},
                        "amount": {"type": "number"},
                        "reason": {"type": "string"},
                    },
                    "required": ["customer_id", "amount"],
                },
                destructive=True,
            ),
            refund_payment,
        ),
        (
            ToolMeta(
                name="charge_card",
                description="Charge a credit card",
                input_schema={
                    "type": "object",
                    "properties": {
                        "card_number": {"type": "string"},
                        "amount": {"type": "number"},
                        "customer_id": {"type": "string"},
                    },
                    "required": ["card_number", "amount"],
                },
                destructive=True,
                redact=redact_card_number,
            ),
            charge_card,
        ),
    ]
