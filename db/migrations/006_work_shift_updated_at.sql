-- Sprint 2, step 6: change time of work shifts (F-18); the calendar sync uses it to find changed shifts.
ALTER TABLE work_shifts ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NOT NULL DEFAULT now();
