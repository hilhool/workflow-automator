# Local Workflow Automator

A self-hosted automation service. Workflows are declared in YAML, run on a
schedule on the local machine, and delegate language tasks to Claude through an
existing Claude Code subscription. No API key is required and no per-request
billing applies.

The process combines three components:

- **Scheduler** — runs workflows on cron and replays anything missed while the
  machine was asleep.
- **Telegram bot** — delivers results and accepts commands from a phone.
- **Web panel** at `http://127.0.0.1:8765` — workflow catalogue, run journal with
  the output of every step, stored items, and Claude usage statistics.

## Quick start

macOS and Linux:

```bash
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
cp .env.example .env            # then fill it in, see below
source .venv/bin/activate
```

Windows (PowerShell):

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
Copy-Item .env.example .env     # then fill it in, see below
.venv\Scripts\Activate.ps1
```

The remaining commands are identical once the environment is active:

```
python scripts/tg_login.py      # one-time sign-in to the Telegram account
python scripts/moodle_check.py  # reports which Moodle access path is available
python main.py                  # start the service
```

Open `http://127.0.0.1:8765` to review the current state. The panel and the
bot are in Russian; this document quotes their labels where relevant.

Throughout this document, `python` refers to the interpreter inside `.venv`.
Without an activated environment it is `./.venv/bin/python` on macOS and Linux
and `.venv\Scripts\python.exe` on Windows.

### Required `.env` values

| Setting | Source | Purpose |
|---|---|---|
| `TELEGRAM_API_ID`, `TELEGRAM_API_HASH` | [my.telegram.org](https://my.telegram.org) → API development tools | reading channels and chats as the account owner |
| `TELEGRAM_BOT_TOKEN` | [@BotFather](https://t.me/BotFather) → `/newbot` | message delivery to the owner |
| `TELEGRAM_OWNER_ID` | send `/start` to the bot; it replies with the id | restricts the bot to a single recipient |
| `MOODLE_URL`, `MOODLE_USERNAME`, `MOODLE_PASSWORD` | the Moodle instance address and ordinary account credentials | deadlines and assignments from enrolled courses |

Both halves are needed because bots cannot see the channels an account is
subscribed to: the account reads, the bot writes.

**Telegram API keys are optional.** Public channels are read by the
`telegram.web` node through `t.me/s/<channel>` without any authentication, which
is how `morning_digest` ships by default. An `api_id` becomes necessary only for
private channels and group chats: replace `node: telegram.web` with
`node: telegram.read` in the YAML, the parameters are identical.

### Running as a service

macOS (launchd):

```bash
./scripts/install_service.sh     # starts at login and after reboot
./scripts/uninstall_service.sh   # removes the agent
```

Windows (Task Scheduler):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_service.ps1
powershell -ExecutionPolicy Bypass -File scripts\uninstall_service.ps1
```

The task is registered as `LocalWorkflowAutomator`. It starts at login and
restarts itself if the process exits. No console window appears — the task runs
`pythonw.exe` and all output goes to the log.

Service logs are written to `data/logs/`.

## Operating behind a blocked network

Declare a proxy in `.env`. It applies to every outbound connection: the Bot API,
channel reads, Moodle, and Claude CLI invocations.

```
TELEGRAM_PROXY=http://user:pass@host:port
```

An empty value means "inherit from the environment" (`HTTPS_PROXY`,
`HTTP_PROXY`, `ALL_PROXY`). Relying on the environment is discouraged: the
service is launched by Task Scheduler, which does not inherit the variables set
in an interactive console, so the service would run with different settings than
those verified by hand.

Supported schemes are `http://`, `https://`, `socks5://` and `socks5h://`. An
address using any other scheme (for example `socks4://` exposed by a VPN client)
is ignored, because neither httpx nor aiohttp accepts such a proxy and nothing
would work with it.

Telethon does not receive the proxy yet. Where Telegram is blocked, reading
private chats and closed channels will therefore not work.

## Architecture

```
workflows/*.yaml   workflow definitions — the files edited most often
core/              engine: YAML loading, templating, executor, scheduler
nodes/             step types available in YAML
integrations/      Claude CLI, Telegram (reading and sending)
web/               panel and JSON API
bot/               bot commands
data/              database, Telegram session, user scripts, logs
```

A workflow is a list of steps. Each step invokes a node and stores its result in
the run context, from which the next step reads it via `{{ steps.<id>.text }}`.

```yaml
name: morning_digest
trigger:
  type: cron
  cron: "0 8 * * *"
  catch_up: true          # missed runs are delivered at start-up
steps:
  - id: news
    node: telegram.read
    params: { chats: ["@meduzalive"], since_hours: 24 }
  - id: digest
    node: claude.prompt
    params:
      model: fast
      prompt: "Summarise:\n{{ steps.news.text }}"
  - id: send
    node: telegram.send
    params: { text: "{{ steps.digest.text }}" }
```

A step also accepts `when:` (conditional execution) and
`continue_on_error: true` (a failing step does not abort the workflow).

Templates expose `steps.*`, `vars.*` (from the workflow `vars` block),
`workflow.name`, `workflow.title`, and `now` — `now.date`, `now.time`,
`now.weekday`, `now.human`.

Message text is written in markdown, not HTML. Everything sent to Telegram
passes through an escaping converter, so raw HTML in a workflow, prompt, or bot
reply reaches the recipient as visible angle brackets.

### Step types

| Node | Description |
|---|---|
| `telegram.web` | reads **public** channels through t.me, without keys or a signed-in account |
| `telegram.read` | reads channels and chats as the account owner, private ones included (`track_cursor` remembers the read position) |
| `telegram.send` | sends text to the owner's bot, splitting long messages |
| `claude.prompt` | text processing without tools — summaries, data extraction |
| `claude.agent` | Claude with tools: Notion, Gmail and Calendar MCP connectors |
| `items.save` | stores items (homework, tasks) deduplicated by `external_id` |
| `items.query` | retrieves open items, optionally filtered by an approaching due date |
| `items.complete` | closes an item |
| `moodle.deadlines` | deadlines from the Moodle calendar |
| `moodle.courses` | list of enrolled courses |
| `moodle.page` | any Moodle page rendered as text |
| `telegram.unread` | unread direct messages and group messages — sender and subject |
| `mail.fetch` | messages from every configured mailbox over IMAP |
| `script.run` | executes a user script from `data/scripts` |
| `http.request` | HTTP request to an arbitrary API |

For the current list, run `python cli.py nodes`.

### Bundled workflows

| File | Description | State |
|---|---|---|
| `morning_digest.yaml` | news, deadlines and tasks in a single 08:00 message | enabled; add your channels |
| `deadlines_evening.yaml` | 21:00 reminder about what is due | enabled |
| `moodle_sync.yaml` | pulls Moodle deadlines every 3 hours | enabled; fill in `.env` |
| `homework_watch.yaml` | reads the course chat every 30 minutes and extracts assignments | disabled; specify the chat |
| `mail_digest.yaml` | mail summary across all mailboxes at 09:00 and 19:00 | enabled; add mailboxes |
| `messages_watch.yaml` | hourly report of direct and group messages | enabled; requires `api_id` |
| `schedule_sync.yaml` | imports a timetable from a Telegram chat into items | enabled; specify the chat |
| `notion_daily.yaml` | evening day summary written to Notion | disabled; specify the page |
| `script_example.yaml` | template for a custom automation | disabled |

Channel names can be looked up with:

```bash
python scripts/list_chats.py university
```

## Moodle

Deadlines are retrieved through one of two paths, selected automatically:

1. **Web services** (`/webservice/rest/server.php`), available when the
   administrator has left the mobile service enabled. The data arrives
   structured — title, course, exact due date, link — and Claude is not involved.
2. **Ordinary site login**, used when web services are disabled. The service
   authenticates through the login form, opens the upcoming events page, strips
   the markup, and passes the text to Claude, which extracts assignments and
   dates.

`python scripts/moodle_check.py` reports which path applies. In the run journal
the same information appears in the `mode` field: `api` or `html`.

Assignments are stored as items with `kind: homework` and the key
`moodle-<id>`, so repeated synchronisation updates existing records instead of
creating duplicates. They then appear in the morning digest and the evening
reminder automatically.

If the class timetable lives on a separate Moodle page, add a step:

```yaml
- id: schedule
  node: moodle.page
  params: { path: "/calendar/view.php?view=month" }
```

Until `.env` is filled in, `moodle_sync` completes successfully and does
nothing; the journal records "Moodle is not configured".

## Mail

Mailboxes are read over IMAP. Any number of them may be configured, across
different providers, using numbered groups in `.env`:

```
MAIL_1_NAME=Personal
MAIL_1_EMAIL=ivan@gmail.com
MAIL_1_PASSWORD=app-password

MAIL_2_NAME=University
MAIL_2_EMAIL=ivan@yandex.ru
MAIL_2_PASSWORD=app-password
```

The IMAP host is derived from the address for gmail, yandex, mail.ru, bk.ru,
outlook, icloud and rambler. For a custom domain, add `MAIL_1_HOST=imap.domain`.

**An application password is required; a regular account password will not
work.** Providers no longer accept ordinary passwords over IMAP:

- Gmail — enable two-factor authentication, then myaccount.google.com/apppasswords
- Yandex — id.yandex.ru → Security → App passwords → Mail
- Mail.ru — id.mail.ru → Security → Passwords for external applications

Mailboxes are opened **read-only**: messages are neither marked as read nor
modified. Each message enters a summary once — the position is remembered.

## Bot commands

A persistent six-button menu covers the common actions: digest, messages, mail,
today, homework, tasks. The equivalent commands:

```
/today         classes and deadlines for today
/hw            homework, with "close" buttons
/tasks         tasks
/mail          collect a mail summary now
/msg           who wrote in direct messages
/list          workflows with run buttons
/run <name>    execute a specific workflow
/add <text>    add a task
/done <id>     close an item
/status        what is configured and what is not
```

Any message that does not begin with a slash is forwarded to Claude as a
question.

## Command-line debugging

```bash
python cli.py list                 # workflows visible to the service
python cli.py nodes                # available step types
python cli.py run morning_digest   # execute once and print the result
python -m pytest                   # test suite
```

YAML edits are picked up by the panel's reload button ("Перечитать YAML");
restarting the service is unnecessary.

## Subscription usage

A `claude.prompt` call without tools costs roughly 4k context tokens instead of
33k: the engine passes the CLI a trimmed system prompt and disables tools and
MCP servers. Steps using `claude.agent` cost more, since tools are required
there. Daily statistics are shown on the usage page ("Расход").

Use `model: fast` (Haiku) for inexpensive steps and `default` (Sonnet) for
summaries and parsing, or name a model explicitly: `model: claude-opus-5`.

## MCP connectors

`claude.agent` uses the connectors attached to the local Claude Code
installation. Verify them with `claude mcp list`.

A connector that exposes only an authorisation step is not connected yet;
authorise it in the claude.ai settings (Settings → Connectors). A working
agentic step is provided in `notion_daily.yaml`.

Tool names for `tools` follow the pattern `mcp__<server>__<tool>`; an entire
server may be allowed at once, for example `mcp__claude_ai_Notion`.

## Security

- Secrets live only in `.env`, which is listed in `.gitignore` and never reaches
  the code.
- The panel listens on `127.0.0.1` and is not reachable from the network.
- The bot responds only to the owner declared in `TELEGRAM_OWNER_ID` and ignores
  everyone else.
- `script.run` executes files exclusively from `data/scripts`.
- The Moodle password is kept in `.env` only; the web service token is cached in
  the local database and refreshed automatically on expiry.
- The Telegram session is stored locally in `data/` and is never transmitted.
