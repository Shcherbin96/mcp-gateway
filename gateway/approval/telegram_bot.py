"""Telegram polling app — handles inline approve/reject button callbacks plus
``/approve``, ``/reject``, ``/pending`` text commands so reviewers can attach
context (a decision reason) to a decision instead of one-tap-only buttons.
"""

from uuid import UUID

from sqlalchemy import select
from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from gateway.approval.store import APPROVED, PENDING, REJECTED, ApprovalStore
from gateway.db.models import ApprovalRequest
from gateway.observability.logging import get_logger

log = get_logger(__name__)


def _is_authorized(update: Update, admin_chat_id: str | None) -> bool:
    """Validate sender chat matches the configured admin chat. If no admin
    chat is configured (open mode) callers are accepted; otherwise only
    messages from the admin chat are allowed.
    """
    if admin_chat_id is None:
        return True
    chat = update.effective_chat
    return bool(chat and str(chat.id) == str(admin_chat_id))


def _parse_id_and_reason(args: list[str]) -> tuple[str | None, str | None]:
    """``["8d3de94b", "too", "risky"]`` → ("8d3de94b", "too risky")."""
    if not args:
        return None, None
    head = args[0]
    rest = " ".join(args[1:]).strip() or None
    return head, rest


async def _resolve_pending(store: ApprovalStore, id_prefix: str) -> ApprovalRequest | None:
    """Match a pending approval by full UUID or 8-char short prefix."""
    # Full UUID fast path.
    try:
        full = UUID(id_prefix)
    except (ValueError, AttributeError):
        full = None
    if full is not None:
        req = await store.get(full)
        if req is not None and req.status == PENDING:
            return req
        return None

    # Short prefix lookup. Match against hex of id, restricted to PENDING.
    if len(id_prefix) < 4:
        return None
    async with store._session_factory() as s:
        res = await s.execute(select(ApprovalRequest).where(ApprovalRequest.status == PENDING))
        candidates = [r for r in res.scalars().all() if r.id.hex.startswith(id_prefix.lower())]
    if len(candidates) == 1:
        return candidates[0]
    return None


def build_telegram_app(
    token: str,
    store: ApprovalStore,
    broadcaster,
    admin_chat_id: str | None = None,
) -> Application:
    app = Application.builder().token(token).build()

    async def _decide(
        update: Update,
        approval_uuid: UUID,
        decision: str,
        reason: str | None,
    ) -> tuple[bool, str | None]:
        user_obj = update.effective_user
        user = (user_obj.username or str(user_obj.id)) if user_obj else "unknown"
        ok = await store.decide(
            approval_uuid,
            decision=decision,
            decided_by=f"tg:{user}",
            reason=reason,
        )
        if ok:
            req = await store.get(approval_uuid)
            tool = req.tool if req is not None else None
            await broadcaster.notify_decided(
                approval_id=approval_uuid,
                status=decision,
                tool=tool,
                reason=reason,
            )
        return ok, None

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
        approval_uuid = UUID(approval_id)
        ok, _ = await _decide(update, approval_uuid, decision, reason=None)
        if ok:
            await q.answer(f"{decision}", show_alert=False)
            await q.edit_message_reply_markup(reply_markup=None)
        else:
            await q.answer("Already decided", show_alert=True)

    async def _on_command_decision(update: Update, ctx: ContextTypes.DEFAULT_TYPE, decision: str):
        msg = update.effective_message
        if msg is None:
            return
        if not _is_authorized(update, admin_chat_id):
            await msg.reply_text("Unauthorized")
            return
        id_prefix, reason = _parse_id_and_reason(list(ctx.args or []))
        if not id_prefix:
            verb = decision[:-1] if decision.endswith("d") else decision
            await msg.reply_text(f"Usage: /{verb} <approval_id> [reason]")
            return
        req = await _resolve_pending(store, id_prefix)
        if req is None:
            await msg.reply_text(
                f"No pending approval matches `{id_prefix}`",
                parse_mode="Markdown",
            )
            return
        ok, _ = await _decide(update, req.id, decision, reason=reason)
        if ok:
            tail = f"\nReason: _{reason}_" if reason else ""
            await msg.reply_text(
                f"{decision} `{req.id.hex[:8]}` ({req.tool}){tail}",
                parse_mode="Markdown",
            )
        else:
            await msg.reply_text("Already decided")

    async def on_approve(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        await _on_command_decision(update, ctx, APPROVED)

    async def on_reject(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        await _on_command_decision(update, ctx, REJECTED)

    async def on_pending(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        msg = update.effective_message
        if msg is None:
            return
        if not _is_authorized(update, admin_chat_id):
            await msg.reply_text("Unauthorized")
            return
        async with store._session_factory() as s:
            res = await s.execute(
                select(ApprovalRequest)
                .where(ApprovalRequest.status == PENDING)
                .order_by(ApprovalRequest.created_at.desc())
                .limit(20)
            )
            rows = res.scalars().all()
        if not rows:
            await msg.reply_text("No pending approvals.")
            return
        lines = ["*Pending approvals:*"]
        for r in rows:
            lines.append(f"`{r.id.hex[:8]}` — {r.tool}")
        await msg.reply_text("\n".join(lines), parse_mode="Markdown")

    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(CommandHandler("approve", on_approve))
    app.add_handler(CommandHandler("reject", on_reject))
    app.add_handler(CommandHandler("pending", on_pending))
    return app
