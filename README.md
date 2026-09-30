# Discord Send Later

A small Python 3.11+ bot for scheduling private Discord DMs to explicitly selected members. A schedule stores its message once and links one or more selected recipients; the bot never broadcasts to a server or posts scheduled content in a channel.

## Create and invite the bot

1. In the [Discord Developer Portal](https://discord.com/developers/applications), create an application, open **Bot**, and add a bot user.
2. Copy its token into `.env` as `DISCORD_TOKEN`. Keep the token private and regenerate it if exposed.
3. Under **Bot > Privileged Gateway Intents**, enable **Server Members Intent**. The bot uses this to validate/fetch guild members at delivery time. Message Content and Presence intents are not needed; Discord allows bots to read messages sent to them in DMs.
4. Open **OAuth2 > URL Generator**. Select `bot` and `applications.commands`. Grant **Send Messages** (needed in DMs) and **View Channels** for server command availability. The bot does not send scheduled content to channels.
5. Open the generated URL and add the bot to your server.

## Install and run

From the project folder, create a virtual environment and install dependencies:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` with the bot token. `DATABASE_PATH` defaults to `./data/bot.db`; `DEFAULT_TIMEZONE` defaults to `UTC`; `SCHEDULER_POLL_SECONDS` defaults to 15. Start the bot with:

```powershell
python bot.py
```

Slash commands sync on startup. SQLite tables and indexes are created automatically. Keep the database file and back it up; it contains private message bodies and recipient records.

## Commands

- `/settings timezone:America/New_York` stores an IANA timezone for you in the current server. Until set, schedules use UTC and the confirmation calls that out.
- `/schedule` takes a required recipient, message, and local date/time in `YYYY-MM-DD HH:MM` 24-hour format. Up to four additional selected guild members can be provided. Choose an optional repeat rule, and for custom recurrence provide an interval and unit. A recurring schedule can end at a local date/time or after a maximum number of sends. Review the ephemeral confirmation and press **Confirm** to save.
- `/scheduled` lists up to 25 active schedules created by you, with private **Edit** and **Cancel** controls. Each schedule has a numeric ID.
- `/edit schedule_id:...` replaces the message, recipients, first date/time, recurrence, and end condition. Re-enter all details, including at least one recipient.
- `/cancel schedule_id:...` cancels your schedule. The Cancel button in `/scheduled` does the same. Completed delivery history is retained.

Repeat choices are None, every day, every week, every two weeks, every month, or a custom interval in minutes/hours/days/weeks. Monthly recurrence clamps to the last day in shorter months. Calendar recurrences preserve local wall-clock time through daylight saving changes. A missed one-time schedule is sent as soon as the bot comes online; a late recurring run is sent once, then the next future occurrence is calculated.

Recipient fields use Discord's guild member picker, not arbitrary IDs. The same message is sent separately to each selected person. A failed recipient does not stop delivery to others; success or a compact error type is recorded for each delivery. The bot does not log message bodies. Discord can still reject DMs when a recipient blocks the bot, leaves, or disables server DMs.

When a recipient replies to a scheduled DM using Discord's **Reply** action, the bot privately forwards the reply to the schedule creator as `RecipientName (schedule #ID): reply`. A reaction added to the scheduled DM is reported in the same way, such as `RecipientName (schedule #ID): reacted with ✅` (custom emoji are shown by name). The bot tracks the ID of each delivered DM, including each repeat occurrence, so it can attribute reactions and replies. Unthreaded DMs and replies to unrelated messages are ignored. The bot needs the normal DM message and DM reaction gateway events, which are enabled in code; no Message Content privileged intent is needed for DMs.

## Deployment and operations

Run one bot process against one persistent database file. For a later deployment, use a small always-on host, keep the SQLite file on persistent storage, set the environment variables in the host's secret/configuration manager, and configure automatic process restart. Do not run multiple bot instances against the same database: the scheduler uses atomic database claims, but single-instance operation keeps delivery behavior easiest to reason about. Back up the database securely and restrict access because it contains private content.

The scheduler polls SQLite instead of sleeping until a particular timestamp, so pending jobs survive process restarts. Due work is claimed atomically. Delivery to multiple recipients is sequential with a short pause and uses discord.py's normal HTTP rate-limit handling. If the process is interrupted while a claimed message is being delivered, a stale claim is released after ten minutes; an interruption at that exact point can cause a repeated partial delivery. SQLite cannot make Discord DM delivery transactional, so inspect delivery history when recovering from abrupt host failures.

## Checks

Run the included local tests with `python -m unittest discover -v`. They cover one-time and recurring date calculation, monthly clamping, DST conversion, multi-recipient storage, ownership checks, and cancellation. A real Discord token/server is needed to confirm command sync, permissions, and actual DM availability.
