-- Sprint 2, step 7: reminder settings (F-20, F-21).
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'reminder_type') THEN
        CREATE TYPE reminder_type AS ENUM ('SEMESTRO_PRADZIA', 'MENESIO_PRADZIA');
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS reminder_settings (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    closed_period_start DATE,
    closed_period_type reminder_type
);
