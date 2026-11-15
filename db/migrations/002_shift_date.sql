-- Sprint 2, step 1: work shifts get a concrete date (F-09, F-18, F-26; N-25).
-- Safe to run more than once. Existing shifts are moved to that weekday of the current week.

ALTER TABLE work_shifts ADD COLUMN IF NOT EXISTS work_date DATE;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'work_shifts' AND column_name = 'day_of_week'
    ) THEN
        UPDATE work_shifts SET work_date = date_trunc('week', current_date)::date + (
            CASE day_of_week
                WHEN 'PIRMADIENIS' THEN 0 WHEN 'ANTRADIENIS' THEN 1 WHEN 'TRECIADIENIS' THEN 2
                WHEN 'KETVIRTADIENIS' THEN 3 WHEN 'PENKTADIENIS' THEN 4 WHEN 'SESTADIENIS' THEN 5
                ELSE 6
            END
        ) WHERE work_date IS NULL;
        ALTER TABLE work_shifts DROP COLUMN day_of_week;
    END IF;
END $$;

ALTER TABLE work_shifts ALTER COLUMN work_date SET NOT NULL;
CREATE INDEX IF NOT EXISTS idx_work_shifts_work_date ON work_shifts(work_date);
