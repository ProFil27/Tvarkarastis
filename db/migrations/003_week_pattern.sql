-- Sprint 2, step 2: lectures that take place only on week 1 or week 2 (see domain/academic_week.py).
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'week_pattern') THEN
        CREATE TYPE week_pattern AS ENUM ('KIEKVIENA', 'PIRMA', 'ANTRA');
    END IF;
END $$;

ALTER TABLE study_events ADD COLUMN IF NOT EXISTS week_pattern week_pattern NOT NULL DEFAULT 'KIEKVIENA';
