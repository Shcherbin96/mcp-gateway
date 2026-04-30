"""Telegram polling app — handles inline approve/reject button callbacks."""

from uuid import UUID

from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, ContextTypes

from gateway.approval.store import APPROVED, REJECTED, ApprovalStore
from gateway.observability.logging import get_logger

log = get_logger(__name__)


def build_telegram_app(
    token: str,
    store: ApprovalStore,
    broadcaster,
    admin_chat_id: str | None = None,
) -> Application:
    app = Application.builder().token(token).build()

    async def on_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        q = update.callback_query
        if not q or not q.data:
            return
        # Reject callbacks from chats other than the configured admin chat to
        # prevent unauthorized approve/reject by anyone who guesses the bot.
        if (
            admin_chat_id is not None
            and q.message
            and q.message.chat
            and str(q.message.chat.id) != str(admin_chat_id)
        ):
            await q.answer("Unauthorized", show_alert=True)
            return
        action, _, approval_id = q.data.partition(":")
        decision = APPROVED if action == "approve" else REJECTED
        user = (q.from_user.username or str(q.from_user.id)) if q.from_user else "unknown"
        approval_uuid = UUID(approval_id)
        ok = await store.decide(approval_uuid, decision=decision, decided_by=f"tg:{user}")
        if ok:
            # Look up the tool name so the decision message can use the
            # tool-specific emoji and label.
            req = await store.get(approval_uuid)
            tool = req.tool if req is not None else None
            await broadcaster.notify_decided(approval_id=approval_uuid, status=decision, tool=tool)
            await q.answer(f"{decision}", show_alert=False)
            await q.edit_message_reply_markup(reply_markup=None)
        else:
            await q.answer("Already decided", show_alert=True)

    app.add_handler(CallbackQueryHandler(on_callback))
    return app
