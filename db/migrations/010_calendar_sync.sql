-- Sprint 2, step 10: links to Google events and the log of synchronisation runs (F-26..F-31, N-25).
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'sync_operation_type') THEN
        CREATE TYPE sync_operation_type AS ENUM ('EKSPORTAS', 'ATNAUJINIMAS');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'sync_status') THEN
        CREATE TYPE sync_status AS ENUM ('VYKDOMAS', 'SEKMINGAS', 'KLAIDA');
    END IF;
END $$;

-- A link survives the deletion of its study event / work shift (both ids become NULL = orphan), so that the
-- next synchronisation can still delete the matching Google event.
CREATE TABLE IF NOT EXISTS calendar_events (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    study_event_id INTEGER REFERENCES study_events(id) ON DELETE SET NULL,
    work_shift_id INTEGER REFERENCES work_shifts(id) ON DELETE SET NULL,
    google_event_id VARCHAR(1024) NOT NULL,
    synced_at TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT calendar_event_one_source CHECK (study_event_id IS NULL OR work_shift_id IS NULL),
    CONSTRAINT calendar_event_unique_google_id UNIQUE (user_id, google_event_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_calendar_events_study_event ON calendar_events(study_event_id) WHERE study_event_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_calendar_events_work_shift ON calendar_events(work_shift_id) WHERE work_shift_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_calendar_events_user_id ON calendar_events(user_id);

CREATE TABLE IF NOT EXISTS sync_operations (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    operation_type sync_operation_type NOT NULL,
    status sync_status NOT NULL DEFAULT 'VYKDOMAS',
    started_at TIMESTAMP NOT NULL DEFAULT now(),
    finished_at TIMESTAMP,
    created_count INTEGER NOT NULL DEFAULT 0,
    updated_count INTEGER NOT NULL DEFAULT 0,
    deleted_count INTEGER NOT NULL DEFAULT 0,
    error_code VARCHAR(40),
    error_message TEXT
);
CREATE INDEX IF NOT EXISTS idx_sync_operations_user_id ON sync_operations(user_id);
