-- Sprint 2, step 8: the user can choose that a newly uploaded schedule replaces the current one (F-22).
ALTER TABLE pdf_documents ADD COLUMN IF NOT EXISTS replace_existing BOOLEAN NOT NULL DEFAULT FALSE;
