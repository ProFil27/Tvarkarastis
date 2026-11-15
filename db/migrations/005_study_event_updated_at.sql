-- Sprint 2, step 5: change time of study events (F-17); the calendar sync uses it to find changed events.
ALTER TABLE study_events ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NOT NULL DEFAULT now();
