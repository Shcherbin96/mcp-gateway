# Demo recording script (2 min)

> **Цель:** показать end-to-end защиту: Claude Desktop → MCP Gateway → Telegram approval → reject → audit log. Запись для Loom / YouTube. Версии: русский (основная) + English voiceover (опционально).

---

## Pre-recording checklist

- [ ] `docker compose up -d && make seed` — стэк запущен
- [ ] Claude Desktop перезапущен, в нём виден MCP-сервер `mcp-gateway` (5 tools)
- [ ] Telegram bot работает — проверь через любой test-tool, что карточка приходит на телефон
- [ ] Браузер открыт на http://localhost:8000/audit (с admin token, например через расширение [ModHeader](https://modheader.com/))
- [ ] Раскладка экрана:
  - Левая половина: Claude Desktop
  - Правая половина: браузер с `/audit` (потом переключим на `/approvals`)
  - Телефон с Telegram держи в кадре (можно через QuickTime mirroring или просто на стол рядом с ноутом)
- [ ] Микрофон проверен, записывающее ПО (Loom / QuickTime) готово
- [ ] Один тестовый прогон без записи — убедись что flow работает

---

## Timeline (рус)

| Время | Что в кадре | Что говоришь / показываешь |
|---|---|---|
| **0:00–0:15** | Hero-слайд / GitHub-репо страница | «Привет. Я построил MCP Gateway — production-grade прослойку между AI-агентами и боевыми системами компании. Покажу за 2 минуты как это работает.» |
| **0:15–0:35** | Claude Desktop, открыт `claude_desktop_config.json` рядом | «Claude Desktop подключён к gateway по MCP-протоколу. Вот config — gateway передаёт agent'у 5 инструментов: получить клиента, обновить заказ, **вернуть деньги**, и так далее.» |
| **0:35–1:00** | Claude Desktop, ввод | «Прошу Claude: *верни клиенту C001 пятьдесят тысяч рублей за заказ*.» Печатаешь, нажимаешь enter. Claude вызывает `refund_payment`. **Подожди — Claude уточнит, надо подтвердить.** Печатаешь «подтверждаю». |
| **1:00–1:25** | Переключение на телефон с Telegram (split-screen или camera) | «На телефоне моментально приходит карточка от бота: какой агент, какой инструмент, какие параметры, **сумма 50 000 ₽**, кнопки Approve / Reject. Это и есть human-in-the-loop — критичные операции не делаются без меня.» |
| **1:25–1:35** | Тыкаешь Reject в Telegram | «Жму **Reject**.» Камера показывает что Telegram-сообщение обновилось — «❌ Rejected». |
| **1:35–1:50** | Вернись в Claude Desktop | «Claude мгновенно получает ответ от gateway — *approval rejected* — и в чате объясняет: операция отклонена системой. **Mock-payments так и не был вызван.**» |
| **1:50–2:00** | Браузер, http://localhost:8000/audit | «А вот audit log. Вся цепочка зафиксирована: refund_payment, статус `rejected`, decided_by `tg:GFMoki` — мой Telegram username, точное время. Эта таблица **физически не может быть изменена** — Postgres-триггеры запрещают UPDATE/DELETE даже application-пользователю.» |
| **2:00–end** | GitHub URL крупно | «Код, тесты, write-up, deploy-инструкции — всё на github.com/Shcherbin96/mcp-gateway. Спасибо за внимание.» |

---

## Timeline (EN — optional)

| Time | What's on screen | Voice |
|---|---|---|
| 0:00–0:15 | Repo / hero | "I built MCP Gateway — a production-grade security envelope between AI agents and internal company systems. Two-minute walkthrough." |
| 0:15–0:35 | Claude Desktop config | "Claude Desktop is wired to the gateway via MCP. Five tools exposed — get customer, list orders, update order, **refund payment**, charge card." |
| 0:35–1:00 | Claude chat | "I ask Claude: *refund 50,000 rubles to customer C001*. Claude calls the refund tool. The gateway sees this is a destructive operation and pauses." |
| 1:00–1:25 | Phone / Telegram | "Within a second, the bot pings my phone with a structured card: which agent, which tool, what amount. Plus Approve and Reject buttons. This is the human-in-the-loop layer — money doesn't move without me." |
| 1:25–1:35 | Tap Reject | "I reject." |
| 1:35–1:50 | Back to Claude | "Claude gets the rejection from the gateway and explains it in chat. The payments service was never even called." |
| 1:50–2:00 | Audit log | "Audit log captured everything: tool, parameters, status `rejected`, the rejector's identity, exact timestamp. This table is physically append-only — Postgres triggers block UPDATE and DELETE even for the app user." |
| 2:00–end | Repo link | "Code, tests, deploy guide — github.com/Shcherbin96/mcp-gateway. Thanks." |

---

## Recording tips

- **Двигай мышь медленно.** Зрителю нужно успевать читать карточку Telegram и audit log.
- **Не торопись с печатью в Claude.** Подготовь промпт заранее (можно вставить из буфера) — снимай момент когда Claude вызывает tool, а не как ты печатаешь.
- **Если flow затянулся** — самый сжимаемый кусок это audit log в конце (2:00–2:30 вырезается до 2:00–2:10). Никогда не режь момент с Telegram reject.
- **Один дубль обычно идёт криво.** Сделай 2-3 захода — потом возьми лучший.
- **Loom умеет сжимать паузы автоматом** — не парься о тишине между шагами.
- **Микрофон**: даже встроенный MacBook ок если без эха. Если жуткий шум — пиши silent screencast и добавь субтитры, выглядит профессионально.

## После записи

1. Loom даёт публичную ссылку — скопируй
2. Замени `*(Loom link goes here)*` в README на реальную ссылку
3. Push → готово к шарингу в LinkedIn / dev.to / резюме
