-- Work shifts that repeat every week are one series (one Google Calendar event, edited and deleted as a whole).
-- Every occurrence stays an ordinary work_shifts row (conflicts and the week view are unchanged); a row that was
-- changed on its own is an "exception" and is left alone when the series is edited.
CREATE TABLE IF NOT EXISTS shift_series (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    workplace_id INTEGER NOT NULL REFERENCES workplaces(id) ON DELETE CASCADE,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    first_date DATE NOT NULL,
    last_date DATE NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT shift_series_time_check CHECK (end_time > start_time),
    CONSTRAINT shift_series_date_check CHECK (last_date >= first_date)
);
CREATE INDEX IF NOT EXISTS idx_shift_series_user_id ON shift_series(user_id);

ALTER TABLE work_shifts ADD COLUMN IF NOT EXISTS series_id INTEGER REFERENCES shift_series(id) ON DELETE CASCADE;
ALTER TABLE work_shifts ADD COLUMN IF NOT EXISTS is_exception BOOLEAN NOT NULL DEFAULT FALSE;
CREATE INDEX IF NOT EXISTS idx_work_shifts_series_id ON work_shifts(series_id);

-- a link may now also point at a whole series
ALTER TABLE calendar_events ADD COLUMN IF NOT EXISTS shift_series_id INTEGER REFERENCES shift_series(id) ON DELETE SET NULL;
ALTER TABLE calendar_events DROP CONSTRAINT IF EXISTS calendar_event_one_source;
ALTER TABLE calendar_events ADD CONSTRAINT calendar_event_one_source
    CHECK (num_nonnulls(study_event_id, work_shift_id, shift_series_id) <= 1);
CREATE UNIQUE INDEX IF NOT EXISTS idx_calendar_events_series ON calendar_events(shift_series_id)
    WHERE shift_series_id IS NOT NULL;
