"""Telegram outbound notifier — pushes approval prompts + result updates."""

import json
from uuid import UUID

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError

from gateway.observability.logging import get_logger

log = get_logger(__name__)


class TelegramNotifier:
    def __init__(self, bot_token: str, admin_chat_id: str):
        self._bot = Bot(token=bot_token)
        self._chat_id = admin_chat_id

    async def notify_pending(
        self, *, approval_id: UUID, agent_id: UUID, tool: str, params: dict
    ):
        text = (
            f"🔔 *Pending approval*\n\n"
            f"Tool: `{tool}`\n"
            f"Agent: `{agent_id}`\n"
            f"Params:\n```\n{json.dumps(params, indent=2)[:500]}\n```"
        )
        kb = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "✅ Approve", callback_data=f"approve:{approval_id}"
                    ),
                    InlineKeyboardButton(
                        "❌ Reject", callback_data=f"reject:{approval_id}"
                    ),
                ]
            ]
        )
        try:
            await self._bot.send_message(
                chat_id=self._chat_id,
                text=text,
                reply_markup=kb,
                parse_mode="Markdown",
            )
        except TelegramError as e:
            log.warning(
                "telegram_notify_failed",
                error=str(e),
                approval_id=str(approval_id),
            )

    async def notify_decided(self, *, approval_id: UUID, status: str):
        try:
            await self._bot.send_message(
                chat_id=self._chat_id,
                text=f"Approval `{approval_id}` → *{status}*",
                parse_mode="Markdown",
            )
        except TelegramError as e:
            log.warning("telegram_notify_failed", error=str(e))
