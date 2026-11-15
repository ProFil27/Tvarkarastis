# Sprint 2 development plan - "Tvarkaraštis"

Source of truth: the team's sprint 2 specification (`ISPK_..._2sprintas_2026-11-14_v01.docx`, chapter "ANTRAS SPRINTAS").
This plan is written for an implementing AI session: it is self-contained, but read the existing code first
(`README.md`, `docs/sprint1_assignments.md`, `app/application/ports.py`, `app/container.py`).

Sprint goal: **editing data and synchronising with Google Calendar.**
User stories US-08 … US-14; functional F-17 … F-31; non-functional N-25 … N-47 (numbering continues sprint 1).

## 0. Current state (verified in the repo)

- Sprint 1 is complete: auth, PDF import (Gemini or Claude via `AI_PROVIDER`), review/confirm, work shifts (add/list/remove),
  AI conflict analysis, week view, notifications, seed data, tests (`python -m pytest`).
- **Nothing from the sprint 2 spec is implemented yet.** (The "multiple AI clients" commit is an extra, unrelated to the spec; keep it.)
- Architecture to keep (N-18/N-19, N-02, N-41): `web -> application -> domain`; `infrastructure` implements `application/ports.py`
  Protocols; SQL only in `infrastructure/persistence/`; wiring only in `app/container.py`; services receive error codes -> Lithuanian text
  only in `web/messages.py`; tests use in-memory fakes in `tests/fakes.py`.
- Existing hook: `ChangeNotifier` (`application/change_notifier.py`). Schedule import and work-shift service call it after a change;
  `ConflictService.run_check` is subscribed in `container.py`. Reuse it for the calendar sync.
- DB enum codes are ASCII Lithuanian (`AKTYVUS`, `ISSPRESTAS`, `PASKAITA`, `PIRMADIENIS` …) mapped to English Python enums. Follow that for all new enums.

## 1. Design decisions (made here, so the implementer does not have to ask)

1. **Work shifts get a concrete date.** F-18 and F-26 require shift `data (YYYY-MM-DD)` and export shifts as single events,
   but sprint 1 stores only `day_of_week`. Add `work_shifts.work_date DATE`; the weekday is derived from it.
   - `domain.entities.WorkShift` gets `work_date: date` and `updated_at`; `weekday` becomes a property of `work_date`.
   - The work-hours form replaces the weekday select with a date input (YYYY-MM-DD, validated). Fields: workplace (1-100 chars), date, start, end.
   - Week view shows a shift only on its own date (week of `work_date`), not every week.
   - Conflict rule (`domain/overlap.py`): overlap only if same weekday **and** `shift.work_date` lies inside the event's schedule validity
     (`valid_from..valid_to`). So `StudyEvent` gets `valid_from`, `valid_to` (optional) and `updated_at`; `list_study_events` fills them.
     Touching intervals are still not conflicts. Update the analyzer's JSON input to include the shift date (F-19: ID, day, date, HH:MM).
   - Migration backfill for existing shifts: set `work_date` to that weekday in the current week (`date_trunc('week', current_date) + index`).
2. **Never lose Google ids when local rows are deleted.** `calendar_events` must not cascade-delete with `study_events`/`work_shifts`
   (replace-schedule and delete-lecture remove those rows, and sync still has to delete the Google event). Use nullable
   `study_event_id`/`work_shift_id` with `ON DELETE SET NULL`; a row with both NULL = orphan -> sync deletes the Google event, then the row. (F-28, F-29, N-32)
3. **Stale conflicts are marked `ISSPRESTAS`, not deleted** (KVK-7). Change `PostgresConflictRepository.replace_active` accordingly
   (and `FakeConflictRepository`). Rows cascade-deleted with their event/shift (FK) simply vanish - acceptable.
4. **Calendar vendor isolation (N-28, N-41, N-42).** KSK = `application/calendar_sync_service.py`, depends only on ports
   `CalendarProvider` (= IGoogleCalendar), `CalendarAccountRepository`, `CalendarEventRepository`, `SyncOperationRepository`, `TokenCipher`.
   GKK = `infrastructure/calendar/google_calendar_client.py` is the **only** file importing `googleapiclient` / `google_auth_oauthlib`.
5. **Optional Google config.** The app must still boot without Google/token settings (tests, graders without keys). "Connect" then shows a clear message.
6. **Tokens:** encrypted with `cryptography.fernet.Fernet` using `TOKEN_ENCRYPTION_KEY` (`TokenCipher` port, impl in `infrastructure/security.py`). Never logged (N-43).
   If decryption fails -> treat as `RECONNECT_REQUIRED`, do not crash.
7. **Lectures: which schedule?** A manually added lecture goes into the user's latest schedule (by `valid_to`);
   if the user has none, create one (`valid_from = today`, `valid_to = today + SEMESTER_LENGTH_DAYS`). Subject is found-or-created by name inside that schedule;
   changing the subject name on edit re-points to a found-or-created subject (delete subjects left with no events).

8. **Week 1 / week 2 lectures (added requirement, not in the spec docx).** The university PDF has a "Savaitė" column: blank/0 = every week,
   `1` = only on week 1, `2` = only on week 2 (example: Tuesday 14:30-16:05 "Informatikos teisė" is week 2). The sprint 1 code ignores it, which gives
   false conflicts, wrong week views and wrong calendar exports, so it belongs in sprint 2. Rules confirmed with the team:
   - **Week 1 = the Mon-Sun week that contains 1 September**; weeks then alternate 1, 2, 1, 2 ... without restarting. 2026: 31 Aug-6 Sep = week 1, 7-13 Sep = week 2.
   - **Spring semester keeps the same count** (no restart in February); parity is always computed from the September anchor of the academic year.
   - The PDF column "Pogrupis" (subgroup, 0 in the sample) is ignored.
   Details are in section 12 and are referenced from the sections they change. Do this work in step 2b of the order (section 10).

## 2. Database (N-25, N-37, N-39)

Files: `db/migrations/002_sprint2.sql` (for existing DBs), **and** the same structures merged into `db/schema.sql` (fresh Docker DB), seed in `db/seed.sql`.
Add Taskfile task `migrate` (`psql -f db/migrations/002_sprint2.sql`) and mention it in the README. Migration must be re-runnable (`IF NOT EXISTS` / `DO $$` guards for enums).

New enums (ASCII codes, Python names in parentheses):
- `calendar_account_status`: `PRIJUNGTA` (CONNECTED), `NEPRIJUNGTA` (NOT_CONNECTED), `REIKIA_PERPRISIJUNGTI` (RECONNECT_REQUIRED)
- `sync_operation_type`: `EKSPORTAS` (EXPORT), `ATNAUJINIMAS` (UPDATE)
- `sync_status`: `VYKDOMAS` (IN_PROGRESS), `SEKMINGAS` (SUCCESS), `KLAIDA` (ERROR)
- `reminder_type`: `SEMESTRO_PRADZIA` (SEMESTER_START), `MENESIO_PRADZIA` (MONTH_START)
- `notification_type`: `KONFLIKTAS` (CONFLICT), `SISTEMOS_KLAIDA` (SYSTEM_ERROR), `PRIMINIMAS` (REMINDER), `SINCH_KLAIDA` (SYNC_ERROR)
- `week_pattern`: `KIEKVIENA` (EVERY_WEEK), `PIRMA` (WEEK_1), `ANTRA` (WEEK_2) - see section 12

New tables:
- `calendar_accounts(user_id PK/FK UNIQUE, google_email, access_token_enc, refresh_token_enc, token_expires_at, status, consent_given_at, connected_at)`
- `calendar_events(id, user_id FK, study_event_id FK SET NULL, work_shift_id FK SET NULL, google_event_id UNIQUE per user, synced_at, CHECK not both set)`
- `sync_operations(id, user_id FK, type, status, started_at, finished_at, created_count, updated_count, deleted_count, error_code, error_message)`
- `reminder_settings(user_id PK/FK, enabled DEFAULT TRUE, closed_period_start DATE NULL)`

Altered tables:
- `pdf_documents.replace_existing BOOLEAN NOT NULL DEFAULT FALSE`
- `study_events.week_pattern week_pattern NOT NULL DEFAULT 'KIEKVIENA'` (existing rows stay weekly)
- `study_events.updated_at TIMESTAMP NOT NULL DEFAULT now()`, `work_shifts.updated_at` (same), `work_shifts.work_date DATE NOT NULL` (after backfill)
- `notifications.notification_type notification_type NOT NULL DEFAULT 'KONFLIKTAS'`
- `schedules`: spec adds `validFrom/validTo` (already present) and "replaceWith" (no column needed - it is an operation).

Seed (N-39): >= 3 rows in each new table (e.g. users 1-3: reminder_settings; calendar_accounts for 3 users with different statuses;
`calendar_events` x3+, `sync_operations` x3+ incl. one error). Use fake encrypted tokens (app must tolerate them, see decision 6).
Existing shifts in the seed get explicit `work_date` values.

## 3. Domain & configuration

- `domain/entities.py`: add enums above, `PdfDocument.replace_existing`, `StudyEvent.updated_at/valid_from/valid_to`, `WorkShift.work_date/updated_at`,
  `Notification.notification_type`, new dataclasses `CalendarAccount`, `CalendarEventLink`, `SyncOperation`, `ReminderSetting`.
- `domain/reminder.py` (pure): `period_start(today, semester_starts) -> (date, ReminderType)` = most recent of semester start or 1st of month;
  semester wins if both fall on the same day.
- `infrastructure/config.py` + `.env.example` + `config.example.ini` + `docker-compose.yml` env passthrough: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`,
  `GOOGLE_REDIRECT_URI` (default `http://127.0.0.1:5000/calendar/callback`), `TOKEN_ENCRYPTION_KEY`, `SEMESTER_START_DATES` (default `09-01,02-01`, MM-DD list). All optional at boot.
- `requirements.txt` (pin versions): `google-api-python-client`, `google-auth-oauthlib`, `cryptography`.
- `domain/rules.py`: `REMINDER_WINDOW_DAYS = 7`, `SYNC_RETRY_DELAYS = (1, 2, 4)`, `CALENDAR_TIMEZONE = "Europe/Vilnius"`.

## 4. Ports to add / change (`application/ports.py`)

Change:
- `WorkShiftRepository`: `add(..., work_date, ...)`, `get`, `update(user_id, shift_id, ...) -> WorkShift | None` (own shifts only, N-45; sets `updated_at`).
- `ScheduleRepository`: `get_event(user_id, event_id)`, `add_event(user_id, event) `, `update_event(user_id, event_id, event) -> bool`, `remove_event(user_id, event_id) -> bool`,
  `count_events(user_id)`, `replace_all(user_id, pdf_document_id, valid_from, valid_to, events) -> int` (one transaction: delete the user's old schedules + insert new),
  `last_upload_date(user_id) -> date | None` (latest `schedules.created_at`).
- `PdfDocumentRepository.add(user_id, filename, replace_existing=False)`, `get(pdf_document_id)`.
- `ConflictRepository.replace_active` -> marks stale `ISSPRESTAS` (decision 3).
- `NotificationRepository.add(user_id, conflict_id, message, notification_type=CONFLICT)`.

New:
- `ReminderSettingRepository`: `get(user_id)` (default enabled), `set_enabled`, `set_closed_period(user_id, period_start)`.
- `CalendarAccountRepository`: `get`, `save_connected(user_id, email, access_enc, refresh_enc, expires_at, consent_at)`, `set_status`, `update_tokens`.
- `CalendarEventRepository`: `list_links(user_id)`, `add_link`, `touch_link(synced_at)`, `remove_link`, `has_export(user_id)`.
- `SyncOperationRepository`: `start(user_id, type) -> id`, `finish(id, status, counts, error)`, `last(user_id)`, `last_success(user_id)`.
- `TokenCipher`: `encrypt(str) -> str`, `decrypt(str) -> str`.
- `CalendarProvider` (IGoogleCalendar): `authorization_url(state) -> (url, code_verifier)`, `exchange_code(code, verifier) -> CalendarTokens(access, refresh, expires_at, email)`,
  `create_event(tokens, body) -> google_id`, `update_event(tokens, google_id, body)`, `delete_event(tokens, google_id)`, `refresh(tokens) -> CalendarTokens`.
  Raises `CalendarError(code)`; codes: `UNAVAILABLE`, `AUTH_EXPIRED`, `ACCESS_DENIED`, `INVALID_CODE`, `REJECTED`.

## 5. Application services

1. **Lectures (F-17, TVK-9/10/11)** - new `application/study_event_service.py` (`StudyEventService`): `list_events`, `add_event`, `update_event`, `remove_event`.
   Validation (codes -> `web/messages.py`): subject required, <= 100 chars; type in {PASKAITA, PRATYBOS, LABORATORINIS_DARBAS}; weekday; start/end `HH:MM`, end > start;
   room <= 50 chars (spec says room is required in the UI list - treat as required, error `required`); mandatory bool. Sets `updated_at`. Own events only (N-21/N-45).
   After add/update/remove call `on_change(user_id)`.
2. **Work shifts (F-18, DVK-5/6)** - extend `WorkShiftService`: `update_shift(user_id, shift_id, workplace_name, work_date, start, end)`,
   `get_shift`, date validation (`invalid_date`), workplace <= 100 chars; `add_shift` now takes `work_date`. Both call `on_change`.
3. **Conflicts (F-19, KVK-6/7/8, N-34)** - `ConflictService.run_check`: on `AnalysisFailed`/any error keep old conflicts, add a `SYSTEM_ERROR` notification
   ("Konfliktų paieška nepavyko. Bandykite dar kartą."), never raise. Resolved conflicts -> `ISSPRESTAS`; new -> `AKTYVUS` + notification.
   Make `ChangeNotifier.__call__` catch and log each listener's exception so one failing listener never blocks the others or the saved edit.
4. **Replace schedule (F-22, F-23, TVK-12/13)** - `ScheduleImportService`:
   - `upload_and_recognize(..., replace_existing: bool = False)` stores the flag on the PDF row; existing schedule untouched (F-22).
   - `confirm(user_id, pdf_id, rows, replace_confirmed: bool = False)`: if the PDF has `replace_existing` and there are existing events and `replace_confirmed` is False
     -> raise `ReplaceConfirmationRequired(count)` (nothing saved). If True -> `schedules.replace_all(...)` in one transaction, PDF `PATVIRTINTAS`, `on_change`.
   - `pending_replace_count(user_id)`; `cancel_replace` = keep old schedule, flash "Senasis tvarkaraštis nepakeistas." (PDF status stays recognized/rejected; nothing deleted).
5. **Reminders (F-20, F-21, PK-1..3, N-47)** - `application/reminder_service.py` (`ReminderService(settings_repo, schedules, semester_starts, today)`):
   `get_active_reminder(user_id) -> Reminder | None` (text "Prasidėjo naujas laikotarpis. Įkelkite atnaujintą tvarkaraštį."): show iff enabled, today within the first
   7 calendar days (day 0..6) of the current period, `last_upload_date < period_start`, and `closed_period_start != period_start`.
   `close(user_id)` stores that period start; `disable(user_id)` / `enable(user_id)`; `is_enabled(user_id)`. In-app only, no e-mail.
6. **Calendar sync (F-24..F-31, KSK-1..8, N-26..N-33, N-43..N-46)** - `application/calendar_sync_service.py` (`CalendarSyncService`; inject `sleep` and `now` for tests):
   - `begin_connect(user_id, consent) -> (auth_url, state, verifier)`: consent required (else `consent_required`); state = `secrets.token_urlsafe(32)` (>= 128 bits); route stores state+verifier in the Flask session.
   - `complete_connect(user_id, code, state, expected_state, verifier, error=None)`: `error == "access_denied"` -> "Prieiga nepatvirtinta. Kalendorius neprijungtas."; state mismatch -> "Neteisingas užklausos kodas";
     provider failure -> "Google nepasiekiamas"; on any failure account stays NEPRIJUNGTA, no tokens stored, no token in logs. Success -> encrypted tokens, `PRIJUNGTA`, email, `connected_at`, `consent_given_at`.
   - `export(user_id)` (F-26/F-27): needs `PRIJUNGTA` (else `not_connected` -> button "Prijungti Google Calendar"). Study events -> weekly recurring events with `recurrence: ["RRULE:FREQ=WEEKLY;UNTIL=YYYYMMDDT235959Z"]`
     (until = `valid_to`), first occurrence = first date on/after `valid_from` with the event's weekday; shifts -> single events on `work_date`. Body per Google `Event`: `summary` (<=1024), `location`=room/workplace,
     `description`, `start/end {dateTime, timeZone: "Europe/Vilnius"}` (minute precision, N-29). Record `calendar_events` link **right after each successful create** (commit per item -> resumable, N-32).
     Writes `sync_operations` (EKSPORTAS, counts, times). Message "Eksportuota: N įrašų."
   - `sync(user_id)` (F-28/F-29, manual "Sinchronizuoti dar kartą" and auto): only if `PRIJUNGTA` and an export exists. Diff: no link -> create; link and `updated_at > synced_at` -> update; orphan link -> delete (404 on delete = success);
     otherwise untouched. A row that already has a `google_event_id` is never created again. Only ever touch ids stored in `calendar_events` (N-45). `ATNAUJINIMAS` operation with exact created/updated/deleted counts (N-30).
   - Retry (N-31, GKK-2): inside the **provider adapter**, up to 3 retries after 1 s, 2 s, 4 s on network error / 5xx / 429; then raise `CalendarError("UNAVAILABLE")`. On 401 / `invalid_grant` try one token refresh, then `AUTH_EXPIRED`.
   - Errors (F-31, N-33): operation `KLAIDA` with message; `AUTH_EXPIRED` -> account `REIKIA_PERPRISIJUNGTI`; create `SYNC_ERROR` notification; local data unchanged; never raises into the web layer.
     User texts: "Kalendoriaus tiekėjas nepasiekiamas. Bandykite dar kartą." / "Prisijunkite prie Google Calendar iš naujo."
   - `status(user_id) -> SyncStatusReport` (F-30): account status + email, last successful sync (`YYYY-MM-DD HH:MM`, local time, N-29), last operation result (created/updated/deleted) and error.
   - `on_data_changed(user_id)` = listener for `ChangeNotifier`: runs `sync` silently only when connected and exported; swallows everything.
   - Performance (N-35): <= 200 items within 60 s - reuse one authenticated service object per run; no per-item token refresh.
7. **Week view / notifications**: `WeekViewService` unchanged API except shifts filtered by date; notifications list shows type.

## 6. Infrastructure

- `infrastructure/persistence/`: update `work_shift_repository.py`, `schedule_repository.py`, `conflict_repository.py`, `notification_repository.py`, `pdf_document_repository.py`;
  add `reminder_repository.py`, `calendar_account_repository.py`, `calendar_event_repository.py`, `sync_operation_repository.py`. SQL only here (N-25). Multi-step changes in a single transaction (DPK-10, DPK-13).
- `infrastructure/calendar/google_calendar_client.py` (GKK): OAuth 2.0 authorization-code flow via `google_auth_oauthlib.flow.Flow` (scopes `https://www.googleapis.com/auth/calendar.events`, `openid`, `https://www.googleapis.com/auth/userinfo.email` only - N-44);
  `access_type=offline`, `prompt=consent` so a refresh token is issued; keep PKCE `code_verifier` (returned to KSK and kept in session). Redirect URI from config (N-27, must work on Windows and Linux).
  For plain-http localhost set `OAUTHLIB_INSECURE_TRANSPORT=1` **inside this adapter only when the redirect URI host is 127.0.0.1/localhost**. Map `googleapiclient.errors.HttpError` / network errors -> `CalendarError` codes (GKK-3). Never log tokens.
- `infrastructure/security.py`: add `FernetTokenCipher`.
- `app/container.py`: construct the new repos/services; subscribe `calendar_sync.on_data_changed` to `change_notifier` (after `conflicts.run_check`); add `study_events`, `reminders`, `calendar_sync` to `Services`.

## 7. Web / UI (see also section 13 - new time picker, and section 14 - team-provided HTML; all text Lithuanian; errors next to the field in red; destructive actions need a separate confirmation page)

Nav (`base.html`): tabs **Tvarkaraštis | Paskaitos | Darbo valandos | Kalendorius** (new `Paskaitos` and `Kalendorius`; keep active-tab logic).
Reminder bar partial `_reminder.html` (included in `week_view.html` and `upload.html`): text + buttons "Uždaryti" and "Išjungti priminimus" (POST forms; CSRF is not in sprint scope but keep POST + login_required).

1. **Paskaitos** (`web/study_events/routes.py`, blueprint prefix `/lectures`, template `lectures.html`): table of events + form (dalykas, tipas, diena, pradžia, pabaiga, auditorija, privaloma),
   buttons "Pridėti paskaitą", "Keisti" (loads row into the form: `GET /lectures/<id>/edit`), "Išsaugoti", "Šalinti" (-> confirmation page `lecture_delete.html`, then POST). Flash success messages.
2. **Darbo valandos** (`shifts.html`): date input replaces weekday select; "Keisti" per row (`/work-shifts/<id>/edit`), list shows date + workplace + times.
3. **Tvarkaraščio įkėlimas** (`upload.html`, `review.html`): checkbox "Pakeisti esamą tvarkaraštį" (default off). On review confirm with replace flag -> page `replace_confirm.html`:
   "Bus pašalinta N ankstesnio tvarkaraščio įrašų. Tęsti?" with "Pašalinti ir išsaugoti" / "Atšaukti" (cancel: flash "Senasis tvarkaraštis nepakeistas.", old data intact).
4. **Kalendorius** (`web/calendar/routes.py`, prefix `/calendar`, template `calendar.html`): shows status (colour **and** text: Prijungta / Neprijungta / Reikia prisijungti iš naujo), Google email, last successful sync `YYYY-MM-DD HH:MM`,
   last result (sukurta / atnaujinta / ištrinta), error text, consent checkbox + explanation of which data is sent (subject, type, time, room, workplace; N-46), buttons "Prijungti Google Calendar", "Eksportuoti į Google Calendar",
   "Sinchronizuoti dar kartą", reminders toggle. Routes: `GET /calendar/`, `POST /calendar/connect`, `GET /calendar/callback` (reads `code`, `state`, `error`; compares with session state then clears it), `POST /calendar/export`, `POST /calendar/sync`, `POST /calendar/reminders`.
5. **Week view**: shows shifts by date; link to the Kalendorius page (+ sync status badge); conflicts refresh automatically after edits (already via notifier).
6. `web/messages.py`: add all new codes + the spec messages (reminder, replace count, "Eksportuota: N įrašų.", provider unavailable, reconnect, access not confirmed). `web/filters.py`: datetime filter `YYYY-MM-DD HH:MM`.
7. Register new blueprints in `app/web/__init__.py`; inject the reminder into templates through a context processor (only for logged-in users on week/schedule pages). N-40: a new user must connect + export in <= 5 min without help - keep hints inline.

## 8. Tests (pytest, no network, no real Google)

Extend `tests/fakes.py`: fakes for all new repos, `FakeTokenCipher`, `FakeCalendarProvider` (records create/update/delete calls, configurable `CalendarError`), update existing fakes for new signatures.
Update existing tests broken by the shift date change. New test modules:
- `test_study_events.py` - F-17: add/update/remove, each validation error, listener called, other user's event untouchable.
- `test_work_shift_edit.py` - F-18; plus conflict re-run after edit (F-19) and analyzer failure keeps saved edit + old conflicts + notification (N-34, KVK-8); stale conflicts -> `ISSPRESTAS`.
- `test_reminders.py` - F-20/F-21: first 7 days boundaries (day 0, 6 shown; day 7 not), semester vs month, already uploaded, closed period, disabled/re-enabled, new period reopens.
- `test_replace_schedule.py` - F-22/F-23: flag stored, nothing deleted before confirmation, confirm replaces in one step, cancel keeps old.
- `test_calendar_connect.py` - F-24/F-25: consent required, state check (wrong state, `access_denied`, provider down), tokens stored encrypted, status PRIJUNGTA, no tokens in logs (caplog).
- `test_calendar_sync.py` - F-26..F-31, N-30/N-32: export creates N events + links + operation counts; RRULE/UNTIL and `Europe/Vilnius` body; second sync creates 0 duplicates; edit -> 1 update; delete/replace -> deletes; foreign events never touched;
  retry schedule 1/2/4 s then `UNAVAILABLE` (inject fake sleep); `AUTH_EXPIRED` -> `REIKIA_PERPRISIJUNGTI`; resume after a mid-run failure creates no duplicates; not connected / not exported -> no sync.
- `test_google_client.py` - GKK with a stubbed HTTP layer: error mapping + retry only.
- Route tests in `test_full_flow.py` style: lectures page, calendar page (connected / disconnected / error), replace confirmation flow, reminder bar visibility.
- Keep `flake8`/PEP 8 clean (N-28).

## 9. Docs

README: new components table rows (KSK, GKK, PK, reminders), `task migrate`, new env vars, **Google Cloud setup (N-38)**: create project -> enable Google Calendar API -> OAuth consent screen (External, Testing, add test users)
-> create OAuth client (Web application) with redirect URI `http://127.0.0.1:5000/calendar/callback` -> put id/secret in `.env`; how to generate `TOKEN_ENCRYPTION_KEY`
(`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`). Add `docs/sprint2_assignments.md` only if the team splits the work.

## 10. Suggested implementation order (commit-sized steps; run `python -m pytest` after each)

1. Migration + `schema.sql` + seed; domain enums/entities; config + requirements.
2. WorkShift date change end-to-end (repo, service, form, week view, overlap rule, analyzer input) + fix tests.
2b. Week 1/2 lectures (section 12): `WeekPattern`, `academic_week.py`, overlap rule, recognizer prompt/schema, review column, week view badge. Do this **before** lecture editing and calendar export so both build on it.
2c. New time field macro + JS (section 13) and swap it into `review.html` and `shifts.html`; after that, every new form uses it.
3. Lectures editing (service, repo, routes, templates) wired to `ChangeNotifier`; conflict resolve/ISSPRESTAS + robustness (N-34) + notifier hardening.
4. Work-shift editing (F-18).
5. Reminders (domain rule, service, repo, bar, toggle).
6. Replace-schedule flow (F-22/23) with confirmation page.
7. Calendar: ports, token cipher, repos, `CalendarSyncService` with `FakeCalendarProvider` + tests; then the Google adapter; then Kalendorius page and routes; auto-sync listener.
8. Seed N-39 check, README/N-38, flake8, manual walkthrough in the browser (connect with a test Google account, export, edit a lecture, replace schedule, confirm Google reflects it, kill network -> readable error).

## 12. Week 1 / week 2 lectures - implementation details

**Domain**
- `domain/entities.py`: `WeekPattern` enum (`EVERY_WEEK="KIEKVIENA"`, `WEEK_1="PIRMA"`, `WEEK_2="ANTRA"`); `StudyEvent.week_pattern: WeekPattern = EVERY_WEEK` (default keeps all sprint 1 code/tests valid).
- New pure module `domain/academic_week.py`:
  - `academic_anchor(day) -> date`: Monday of the week containing 1 Sept of the academic year; academic year = `day.year` if `day >= anchor(day.year)` else `day.year - 1`
    (so 31 Aug 2026 is already week 1 of 2026/27, and January 2027 uses the 2026 anchor).
  - `week_number(day) -> 1 | 2`: `((monday_of(day) - anchor).days // 7) % 2 == 0` -> 1, else 2.
  - `pattern_applies(pattern, day) -> bool`: `EVERY_WEEK` always; `WEEK_1`/`WEEK_2` iff `week_number(day)` matches.
  - Unit tests: 2026-08-31 -> 1, 2026-09-01 -> 1, 2026-09-06 -> 1, 2026-09-07 -> 2, 2026-09-14 -> 1, a February 2027 date (continuous count, no restart), 2026-12-31/2027-01-01 across the year boundary.
- `domain/overlap.py`: besides weekday and schedule validity, a study event overlaps a shift only if `pattern_applies(event.week_pattern, shift.work_date)`.
  Add a domain test: week-2 lecture vs shift on a week-1 date -> 0 minutes.

**Recognition (AI agent 1, TVK/AA)**
- `infrastructure/ai/gemini_schedule_recognizer.py` (shared by Claude via the client): prompt + response JSON schema get a `week` field (`null`/`0` -> every week, `1`, `2`); validate it; map to `WeekPattern`.
  Tell the model explicitly: the "Savaitė" column, ignore "Pogrupis". `RecognitionResult.events` carry `week_pattern`. Update `FakeRecognizer`, `tests/test_ai_adapters.py` (valid / missing / invalid week value).
- **Recommended extra:** also let recognition return the schedule's validity range from the PDF heading (e.g. "2026-09-01 -- 2026-12-20") as optional `valid_from`/`valid_to`;
  `confirm` uses them when present, else falls back to today + `SEMESTER_LENGTH_DAYS` (current behaviour). The calendar export's `UNTIL` and the week view depend on a correct end date.
  (`RecognitionResult` gets optional `valid_from`/`valid_to`; the review page shows them as editable date fields, validated YYYY-MM-DD with from < to.)

**Review & lecture editing (F-17)**
- `ReviewRow.week_pattern` (form value `KIEKVIENA`/`PIRMA`/`ANTRA`), a "Savaitė" column in `review.html` (select: "Kiekvieną savaitę", "1 savaitė", "2 savaitė"), validated (`invalid_choice`).
- Lecture add/edit form (`lectures.html`) gets the same select; `StudyEventService` validates it; `lectures` table shows it. Changing the pattern updates `updated_at` (so calendar sync updates the Google event).
- `messages.py`: `("week_pattern", "invalid_choice"): "Pasirinkite savaitę."`.

**Week view (SVK, F-11)**
- `WeekViewService.get_week`: after loading events, keep only those with `pattern_applies(e.week_pattern, <date of that event's weekday in this week>)`; conflicts are filtered to the visible events.
  Add `week_number` to `WeekView` and show "1 savaitė" / "2 savaitė" in the week header (`week_view.html`), plus a small badge on lectures that are not weekly.
- `ConflictService.run_check` needs no change (it uses `overlap_minutes`), but the analyzer's JSON input must include each event's `week` and each shift's `date` (update the prompt; `_verify` keeps trusting only the domain rule).

**Google Calendar export (F-26, N-26)**
- Weekly event: `RRULE:FREQ=WEEKLY;UNTIL=YYYYMMDDT235959Z`. Alternating event: `RRULE:FREQ=WEEKLY;INTERVAL=2;UNTIL=...` (a small, necessary extension of N-26 - mention it in the README).
- First occurrence = first date >= `valid_from` that has the event's weekday **and** (for `WEEK_1`/`WEEK_2`) falls in a week where `pattern_applies` is true; if that date is after `valid_to`, skip the event (count it as 0, do not fail).
- Put the pattern in the event `description` ("1 savaitė" / "2 savaitė") so it is visible in Google Calendar.
- Tests: `WEEK_2` lecture in a schedule starting 2026-09-01 -> `INTERVAL=2` and first start 2026-09-08 (the Tuesday of week 2, 7-13 Sept);
  `WEEK_1` Tuesday -> first start 2026-09-01; weekly -> no `INTERVAL`.

**Seed (`db/seed.sql`)**: user 1's timetable should reflect the "Savaitė" column of the real PDF (`C:\Users\edvin\Downloads\timetable_2026-11-15.pdf`; read with `pdftotext -layout`;
set `week_pattern` accordingly and use its validity range 2026-09-01 .. 2026-12-20). Make sure the seed still yields the same demonstrable conflict(s), recomputed with the week rule.

**Acceptance checks**
- A week-2 lecture does not appear in a week-1 week and vice versa; two shifts on the same weekday conflict only with the lectures whose pattern matches that date.
- Uploading the sample PDF yields the right week values on the review page (manually verify the Tuesday 14:30 rows: week 1 vs week 2 variants).
- Exported alternating lectures appear in Google Calendar every second week starting in the right week.

## 13. Replace the time picker (UX fix, applies to every time field)

Problem: the native `<input type="time">` (used in `templates/review.html` start/end cells and `templates/shifts.html` start/end) needs a click on the clock icon and feels laggy.
Replace it everywhere with one shared, faster control, and use it in the new pages too (lectures form, shift edit form):
- Build **one reusable Jinja macro** (e.g. `templates/_time_field.html`, `time_field(name, value, error)`) plus a small vanilla-JS file `static/js/time_field.js` (no heavy library; CSP/offline friendly, works with the existing style.css).
- Behaviour: a plain text input with `inputmode="numeric"`, placeholder `HH:MM`, `maxlength=5`, `pattern="([01]\d|2[0-3]):[0-5]\d"`. Typing `930` or `0930` auto-formats to `09:30`;
  the colon is inserted automatically; invalid hour/minute are highlighted. Arrow Up/Down change minutes in 5-min steps (Shift = hours). Optional: clicking/focusing opens a small
  dropdown of suggested times (e.g. every 5 or 15 min from 07:00 to 21:00, scrollable, keyboard-navigable) so the user can pick instead of typing. No clock icon is required to reach any of it.
- The value submitted stays `HH:MM` (24 h) in the same field names, so **server code and validation (`validate_time_range`) do not change**; keep server-side validation as the source of truth.
- The review table has many rows: initialise the script once with event delegation (not per-row listeners) to avoid lag.
- Accessibility: label association, `aria-invalid` on errors, red error text next to the field (existing `invalid` class).
- Manual check: add a shift and edit a lecture using keyboard only; review table with 12+ rows stays responsive.

## 14. Team-provided HTML for the new pages

The team has ready-made HTML for the sprint 2 pages (lectures editing, calendar, upload with reminder, etc.). The implementer must receive these files together with this plan
and use them as the **visual/markup source of truth**: convert them into Jinja templates extending `base.html` (keep their layout, class names and CSS; merge new styles into `static/css/style.css`
without breaking the sprint 1 pages), replace hard-coded sample data with the template variables from sections 5-7, wire the forms to the routes (POST + `login_required`), and show validation
errors next to fields. Where a team HTML conflicts with this plan (field names, missing time select, no week column), keep the HTML's look and adapt the markup minimally; list any such deviations in the final summary.
Put the originals in `docs/ui/` (do not edit them) for reference.

## 11. Out of scope (sprint 3 / not requested)

Free-time blocks, AI recommendations, comparison, disconnecting the account / deleting data (US-15..US-20), e-mail notifications (N-47 forbids), other calendar providers (only keep the seam, N-42).
Do not commit or push unless asked; the team commits from their own accounts (see README "Darbo eiga komandai").
