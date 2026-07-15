# Notes

A personal Markdown notes app. Keep notes, tag them, search them, pin notes to a date,
and get Telegram reminders when that date becomes due.

Each user has a private workspace. Every note is a Markdown document with a live preview
while editing.

## What Was Added

The test task was to add Telegram reminders based on the existing `note_date` field. I
implemented the feature end to end across the backend, database, background processing,
frontend settings UI, i18n, tests, OpenAPI snapshot, env configuration, and README.

Main additions:

- Telegram account linking from Settings via `/start <link_token>`.
- Optional Telegram deep link via `TELEGRAM_BOT_USERNAME`.
- Toggle for Telegram notifications in Settings.
- User timezone setting for date-based reminder calculation.
- Background Telegram polling and reminder delivery.
- Manual "Send test message" button for quick verification.
- Idempotent reminder delivery with `telegram_reminder_sent_at`.
- Delivery audit table `notification_deliveries` for sent/failed attempts.
- Retry-friendly failed-send tracking on notes.
- EN/RU translations for all new UI strings.

## Product Rule

The existing model stores `note_date` as a date, not a date-time. I kept that contract
instead of changing the note domain model.

Reminder rule:

> A note becomes due when its `note_date` starts in the user's configured timezone.

For example, a note dated `2026-07-15` becomes due on `2026-07-15` in that user's
timezone. New users default to `UTC`.

Archived notes are skipped. Notes without a date are skipped. A successfully delivered
reminder is not sent again.

## Run It

Requirements: Docker with Compose.

```bash
make up
make seed
```

Then open <http://localhost:5173>.

Demo credentials after `make seed`:

- username: `demo`
- password: `demo1234`

Common commands:

```bash
make help
make logs
make test
make lint
make down
make clean
```

## Telegram Setup

Create a bot through `@BotFather`, then run the app with the token:

```bash
export TELEGRAM_BOT_TOKEN=<token from @BotFather>
export TELEGRAM_BOT_USERNAME=<bot username without @> # optional, enables "Open bot"

make up
make seed
```

Verification flow:

1. Open <http://localhost:5173>.
2. Log in as `demo` / `demo1234`.
3. Go to Settings -> Telegram reminders.
4. Open the bot with the deep link or send `/start <link_token>` manually.
5. Enable Telegram notifications and save settings.
6. Click "Send test message".
7. Create or keep a note dated today and wait for the reminder loop.

Expected Telegram messages:

```text
Reminder: Grocery list
Date: <today's date>
```

```text
Telegram reminders are linked. Test message from Notes.
```

## Demo

[Watch/download the Telegram reminder demo](https://raw.githubusercontent.com/Kushovka/notes-app/telegram-reminders/docs/telegram-reminders-demo.mp4)

The demo video shows the Settings page, Telegram linking, reminder delivery, and the
manual test message.

## Implementation Notes

- `GET /api/account/telegram` returns Telegram settings, link token, optional deep link,
  bot configuration status, and timezone.
- `PUT /api/account/telegram` updates notification preference and timezone.
- `POST /api/account/telegram/regenerate-token` rotates the link token.
- `POST /api/account/telegram/test-message` sends a manual test message.
- Telegram linking uses long polling through `getUpdates` and handles `/start
  <link_token>`.
- Reminder delivery runs as a FastAPI background task when `TELEGRAM_BOT_TOKEN` is set.
- Long polling was chosen over webhooks because this test app is expected to run locally
  via Docker Compose without a public HTTPS URL.
- Reminder idempotency is handled with `notes.telegram_reminder_sent_at`.
- Failed sends increment `telegram_reminder_attempts` and store
  `telegram_reminder_last_error`.
- All Telegram attempts are written to `notification_deliveries`, including manual test
  messages and failed reminder attempts.
- `backend/openapi.json` was regenerated after adding the new endpoints.

## Database Changes

New migrations:

- `0003_telegram_reminders.py`
  Adds Telegram settings to users and reminder delivery state to notes.
- `0004_notification_deliveries.py`
  Adds an audit table for Telegram delivery attempts.

Both migrations include `downgrade()`.

## Validation

Verified locally and through Docker:

```bash
make up && make seed && make test && make lint
```

Result:

- Backend tests: 39 passed.
- Backend coverage: 87.28%, above the configured 80% threshold.
- Frontend tests: 9 passed.
- Backend lint and format check: passed.
- Frontend ESLint: passed.
- `make seed` works after the new migrations.

## Tools Used

I used Codex in the desktop app for repository exploration, implementation, test
iteration, and README work.

Why this tool choice: this task is mostly careful brownfield work. Codex is useful here
because it can keep the existing structure in view, make small cross-layer changes, run
the local/Docker checks, and keep product tradeoffs documented while iterating.

## Tech And Libraries Used

I stayed within the existing stack as much as possible:

- Backend: FastAPI, SQLAlchemy, Alembic, Pydantic, Postgres.
- Telegram integration: Telegram Bot API via Python standard library `urllib`, so no
  extra HTTP client dependency was needed for runtime delivery.
- Background work: FastAPI startup/shutdown lifecycle with asyncio tasks.
- Timezones: Python `zoneinfo` plus `tzdata` for reliable IANA timezone data in Docker.
- Frontend: React, Vite, existing app-level API wrapper, existing i18n setup.
- Tests and quality: pytest, pytest-cov, ruff, Vitest, Testing Library, ESLint.
- Demo video: ffmpeg was used to convert the recorded `.MOV` into a small H.264 `.mp4`
  suitable for GitHub/README linking.

## What I Noticed In The Scaffold

The scaffold is compact and easy to enter:

- Backend routers are separated clearly.
- Alembic migrations are small and readable.
- OpenAPI has a snapshot test, which is a good guardrail.
- Frontend already has i18n, so adding EN/RU strings was straightforward.
- The app is intentionally simple, which made the cross-layer feature manageable.

Things I would improve carefully, outside the core test scope:

- Split larger backend modules over time, for example `models/`, `schemas/`, and
  `services/`, once more features appear.
- Introduce a dedicated worker process for background jobs if reminders become
  production-critical.
- Generate frontend API types from OpenAPI before migrating the whole frontend to
  TypeScript.
- Add a small delivery-status/debug view for support and reviewer visibility.

## What I Added Beyond The Minimum

I kept the main scope focused, but added a few practical pieces to make the feature
easier to review and operate:

- Manual Telegram test message from Settings.
- Optional Telegram deep link.
- Delivery audit records in `notification_deliveries`.
- Tests for idempotency and failed-send retry behavior.
- README notes explaining the date/timezone decision and background-job tradeoffs.

## Deliberate Non-Goals

I intentionally did not do a broad folder restructure or a full JavaScript-to-TypeScript
migration in this pass. Both would be reasonable future improvements, but they would add
a lot of unrelated diff to a brownfield test task. I preferred to keep the change focused
on the requested feature, preserve the existing scaffold style, and document the
structural improvements I would do next.

## Next Pass

Given more time, I would:

- Add per-note reminder time, not only date-start reminders.
- Add user-visible delivery status for each dated note.
- Move polling and reminders into a separate worker service.
- Add database-level claiming or a unique delivery key for multi-replica safety.
- Add frontend component tests for the Telegram Settings panel.
- Split growing backend files into `services/`, `schemas/`, and `models/` packages when
  the project has more domain areas.
- Incrementally migrate frontend API contracts to TypeScript from OpenAPI-generated
  types.

## Known Caveats

- Reminders are date-based, not time-of-day based, because the existing model has
  `note_date` as `Date`.
- Long polling is local-review friendly, but a deployed app may prefer Telegram
  webhooks.
- The current idempotency is safe for a single backend process. Multiple backend
  replicas would need row locking or a unique delivery claim around due reminders.
- If `TELEGRAM_BOT_TOKEN` is empty, Telegram settings remain editable but polling and
  delivery do not start.
- `TELEGRAM_BOT_USERNAME` is optional. Without it, users can still copy `/start
  <token>`, but Settings cannot render the deep link.

## Layout

- `backend/` - FastAPI + SQLAlchemy + Alembic, talks to Postgres.
- `frontend/` - React + Vite.
- `docker-compose.yml` - db + backend + frontend.
