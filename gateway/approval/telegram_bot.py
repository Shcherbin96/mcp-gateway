"""Telegram polling app — handles inline approve/reject button callbacks."""

from uuid import UUID

from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, ContextTypes

from gateway.approval.store import APPROVED, REJECTED, ApprovalStore
from gateway.observability.logging import get_logger

log = get_logger(__name__)


def build_telegram_app(token: str, store: ApprovalStore, broadcaster) -> Application:
    app = Application.builder().token(token).build()

    async def on_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        q = update.callback_query
        if not q or not q.data:
            return
        action, _, approval_id = q.data.partition(":")
        decision = APPROVED if action == "approve" else REJECTED
        user = (
            (q.from_user.username or str(q.from_user.id))
            if q.from_user
            else "unknown"
        )
        ok = await store.decide(
            UUID(approval_id), decision=decision, decided_by=f"tg:{user}"
        )
        if ok:
            await broadcaster.notify_decided(
                approval_id=UUID(approval_id), status=decision
            )
            await q.answer(f"{decision}", show_alert=False)
            await q.edit_message_reply_markup(reply_markup=None)
        else:
            await q.answer("Already decided", show_alert=True)

    app.add_handler(CallbackQueryHandler(on_callback))
    return app
