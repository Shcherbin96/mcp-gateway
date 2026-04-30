"""Telegram outbound notifier — pushes approval prompts + result updates."""

import json
from datetime import UTC, datetime
from uuid import UUID

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError

from gateway.observability.logging import get_logger

log = get_logger(__name__)


# Tool → emoji used in headers / decision messages.
_TOOL_EMOJI: dict[str, str] = {
    "refund_payment": "💸",
    "charge_card": "💳",
    "update_order": "📦",
    "get_customer": "👤",
    "list_orders": "👤",
}
_DEFAULT_TOOL_EMOJI = "🔧"

# Param keys that should be rendered as currency.
_MONETARY_KEYS = {"amount", "value", "sum"}

# Telegram hard ceiling on a single message.
_TG_MAX = 4096

# Conservative safety margin when truncating composed messages.
_TG_SAFE = 3800


def _tool_emoji(tool: str | None) -> str:
    if not tool:
        return _DEFAULT_TOOL_EMOJI
    return _TOOL_EMOJI.get(tool, _DEFAULT_TOOL_EMOJI)


def _md_escape(text: str) -> str:
    """Escape characters that have special meaning in legacy Markdown values.

    We use legacy Markdown (not MarkdownV2) since fewer characters need
    escaping; only `_`, `*`, and backticks can break formatting inside
    inline values.
    """
    return text.replace("\\", "\\\\").replace("`", "\\`").replace("*", "\\*").replace("_", "\\_")


def _format_currency(value: object, currency: str = "₽") -> str:
    """Format a number as `12 345,67 ₽` (space thousands sep, comma decimal)."""
    try:
        num = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return str(value)
    formatted = f"{num:,.2f}"  # e.g. "50,000.00"
    # swap separators: "," → " " (thousands), "." → "," (decimal)
    formatted = formatted.replace(",", " ").replace(".", ",")
    return f"{formatted} {currency}"


def _short_id(uid: UUID | str) -> str:
    s = str(uid)
    return s[:8] if len(s) >= 8 else s


def _truncate(text: str, limit: int = 80) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _render_params(params: dict) -> str:
    """Render params as a key-value list. Falls back to JSON if a value is nested."""
    visible = {k: v for k, v in params.items() if not str(k).startswith("__")}
    if not visible:
        return "_(no params)_"

    # Fall back to JSON when any value is a non-trivial nested structure —
    # safer than trying to flatten arbitrary objects/arrays into one line.
    has_nested = any(isinstance(v, (dict, list)) for v in visible.values())
    if has_nested:
        blob = json.dumps(visible, indent=2, ensure_ascii=False, default=str)
        return f"```\n{blob[:1500]}\n```"

    currency = str(visible.get("currency", "₽"))
    lines: list[str] = []
    for key, value in visible.items():
        key_str = _md_escape(str(key))
        if key in _MONETARY_KEYS:
            value_str = _md_escape(_format_currency(value, currency))
        else:
            value_str = _md_escape(_truncate(str(value)))
        lines.append(f"  *{key_str}:* {value_str}")
    return "\n".join(lines)


def _render_pending_message(*, agent_id: UUID, tool: str, params: dict) -> str:
    emoji = _tool_emoji(tool)
    short_agent = _short_id(agent_id)
    timestamp = datetime.now(UTC).strftime("%H:%M:%S UTC")

    parts = [
        f"{emoji} *Pending approval* — `{_md_escape(tool)}`",
        "",
        f"👤 Agent: `{short_agent}` (full id below)",
        f"`{agent_id}`",
        "",
        "*Params:*",
        _render_params(params),
        "",
        f"⏱ Requested at {timestamp}",
    ]
    text = "\n".join(parts)
    if len(text) > _TG_SAFE:
        text = text[: _TG_SAFE - 1] + "…"
    return text


def _render_decided_message(*, approval_id: UUID, status: str, tool: str | None) -> str:
    short = _short_id(approval_id)
    tool_emoji = _tool_emoji(tool)
    tool_suffix = f" `{_md_escape(tool)}`" if tool else ""

    if status == "approved":
        head = "✅ *Approved*"
    elif status == "rejected":
        head = "❌ *Rejected*"
    elif status == "timeout":
        head = "⏰ *Timed out*"
    else:
        head = f"*{_md_escape(status)}*"

    return f"{tool_emoji} {head}{tool_suffix}\nApproval `{short}`"


class TelegramNotifier:
    def __init__(self, bot_token: str, admin_chat_id: str):
        self._bot = Bot(token=bot_token)
        self._chat_id = admin_chat_id

    async def notify_pending(
        self, *, approval_id: UUID, agent_id: UUID, tool: str, params: dict
    ) -> None:
        text = _render_pending_message(agent_id=agent_id, tool=tool, params=params)
        kb = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("✅ Approve", callback_data=f"approve:{approval_id}"),
                    InlineKeyboardButton("❌ Reject", callback_data=f"reject:{approval_id}"),
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

    async def notify_decided(
        self, *, approval_id: UUID, status: str, tool: str | None = None
    ) -> None:
        text = _render_decided_message(approval_id=approval_id, status=status, tool=tool)
        try:
            await self._bot.send_message(
                chat_id=self._chat_id,
                text=text,
                parse_mode="Markdown",
            )
        except TelegramError as e:
            log.warning("telegram_notify_failed", error=str(e))
