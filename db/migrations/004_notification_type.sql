-- Sprint 2, step 4: notification types (conflict / system error / reminder / sync error).
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'notification_type') THEN
        CREATE TYPE notification_type AS ENUM ('KONFLIKTAS', 'SISTEMOS_KLAIDA', 'PRIMINIMAS', 'SINCH_KLAIDA');
    END IF;
END $$;

ALTER TABLE notifications ADD COLUMN IF NOT EXISTS notification_type notification_type NOT NULL DEFAULT 'KONFLIKTAS';
