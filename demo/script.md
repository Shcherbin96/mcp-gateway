# Demo recording script (2-3 min)

Scenario: Claude Desktop calls `refund_payment` for client Иванов (C001), order O1234, amount 50 000 RUB. The operator rejects the action via Telegram. Audit log shows the full record.

## Pre-recording checklist

- [ ] Gateway deployed at `https://mcp-gateway.fly.dev/mcp` and reachable
- [ ] Mock-IdP at port 9000 issued a fresh JWT, copied into `demo/claude_desktop_config.json` (`Authorization: Bearer <token>`)
- [ ] Telegram bot wired to the operator's phone, bot is online
- [ ] Mock CRM has client `C001` (Иванов), Mock Payments has order `O1234`
- [ ] Audit log endpoint open in a browser tab (filter by `actor=demo-user`)
- [ ] Screen recorder set to 1080p, mic levels checked, split-screen layout ready (laptop + phone)

## Timeline

| Time        | Step | Action |
|-------------|------|--------|
| 0:00–0:20   | 1    | Open Claude Desktop. Show `~/Library/Application Support/Claude/claude_desktop_config.json` with the MCP Gateway URL `https://mcp-gateway.fly.dev/mcp` and the `Authorization: Bearer <token>` header. Voiceover: "Claude Desktop talks to our MCP Gateway over HTTP — one endpoint, one bearer token." |
| 0:20–0:50   | 2    | In Claude Desktop chat type the prompt: **"Верни 50 000 рублей клиенту C001 за заказ O1234"**. Claude picks the `refund_payment` tool and calls the gateway. Show the spinner — request is now waiting on human approval. Voiceover: "The gateway authenticated the JWT, authorized the scope, and parked the call until a human approves." |
| 0:50–1:20   | 3    | Cut to the phone (split-screen). A Telegram message from the bot appears: actor, tool, args (`client_id=C001`, `order_id=O1234`, `amount=50000`), and two inline buttons **Approve** / **Reject**. Voiceover: "The operator sees who, what, and why — in Telegram, on their phone." |
| 1:20–1:40   | 4    | Operator taps **Reject**. Telegram updates the message to "Rejected by @operator". |
| 1:40–2:00   | 5    | Cut back to Claude Desktop. The tool call returns an error and Claude replies: **"Не смог выполнить операцию — она была отклонена оператором."** Voiceover: "No refund happened. Payments was never called." |
| 2:00–2:30   | 6    | Switch to the browser tab with the audit log. Show the JSON record: `actor`, `tool=refund_payment`, `args`, `decision=rejected`, `decided_by=@operator`, `timestamp`, `request_id`. Highlight the request_id matches the one Claude saw. Voiceover: "Every call — approved or rejected — lands in the audit log with the full chain of custody." |
| 2:30–end    | 7    | Outro card: GitHub repo URL, one-line pitch ("MCP Gateway: auth, approval, and audit for agent tool calls"), thanks. |

## Recording tips

- Keep cursor movements slow; viewers need to read the Telegram card.
- Pre-stage the JWT so there is no copy/paste delay during the take.
- If a take runs long, the audit-log step (2:00–2:30) is the one to trim — but never cut the Telegram reject step.
