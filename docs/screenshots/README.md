# Screenshots

Live screenshots embedded in the project README. Capture these from a running stack (`make up && make seed`) and save to this directory.

## Required screenshots

| File | What to capture | How to reproduce |
|---|---|---|
| `01-telegram-approval.png` | Telegram inline-keyboard approval card from the bot | Trigger any destructive tool (e.g. `refund_payment`); screenshot the bot's message with `✅ Approve` / `❌ Reject` buttons |
| `02-audit-log-ui.png` | Audit log web UI with several rows of mixed statuses | Navigate to http://localhost:8000/audit, run a few `get_customer` + `refund_payment` calls (some approved, some rejected) so the table shows variety, screenshot the table |
| `03-approvals-pending-ui.png` | Approvals dashboard with a pending row + Approve/Reject buttons | Trigger a destructive tool, navigate to http://localhost:8000/approvals before approving via Telegram, screenshot |
| `04-grafana-dashboard.png` | Grafana dashboard with at least one populated panel | Run `docker compose -f docker-compose.observability.yml up -d`, generate ~30s of traffic via locust, navigate to http://localhost:3000 and screenshot the MCP Gateway dashboard |
| `05-swagger-docs.png` | OpenAPI / Swagger UI showing the route catalog | Navigate to http://localhost:8000/docs, expand a couple of endpoints, screenshot |

## Tips

- **macOS:** `Cmd+Shift+4` then drag selection. Or `Cmd+Shift+5` for window-level capture.
- **Crop tightly.** Cut Chrome chrome / OS menubar where possible.
- **Resolution:** ~1600px wide is enough for README; bigger files just slow down the page.
- **Format:** PNG. SVG-rendered SwaggerUI also screenshots cleanly.

## Embedding

Once captured, the README's "Screenshots" section already references these paths:

```markdown
![Telegram approval](docs/screenshots/01-telegram-approval.png)
```

No further changes needed — just commit the .png files.
