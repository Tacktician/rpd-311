-- reports-service schema (database: reports). Applied idempotently on boot by
-- migrate.js. Mirrors CLAUDE.md > Database schemas > reports-service.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

DO $$ BEGIN
  CREATE TYPE incident_type AS ENUM (
    'POTHOLE', 'DOWNED_TREE', 'NOISE_COMPLAINT', 'SUSPICIOUS_PERSON',
    'VANDALISM', 'CAR_BREAK_IN', 'ZOMBIE_SIGHTING', 'UMBRELLA_CORP_ACTIVITY'
  );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  CREATE TYPE severity_level AS ENUM ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  CREATE TYPE report_status AS ENUM (
    'SUBMITTED', 'TRIAGED', 'IN_PROGRESS', 'RESOLVED', 'CLOSED', 'ESCALATED'
  );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS reports (
  report_id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  type              incident_type NOT NULL,
  description       TEXT NOT NULL,
  lat               NUMERIC(9,6) NOT NULL,
  lng               NUMERIC(9,6) NOT NULL,
  address           TEXT,
  severity          severity_level NOT NULL DEFAULT 'MEDIUM',
  status            report_status NOT NULL DEFAULT 'SUBMITTED',
  anonymous         BOOLEAN NOT NULL DEFAULT FALSE,
  reporter_name     TEXT,
  reporter_contact  TEXT,
  triage_reference  UUID,
  resolved_by       TEXT,
  internal_note     TEXT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS attachments (
  attachment_id   UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  report_id       UUID NOT NULL REFERENCES reports(report_id) ON DELETE CASCADE,
  filename        TEXT NOT NULL,
  mime_type       TEXT NOT NULL,
  size_bytes      INTEGER NOT NULL,
  s3_key          TEXT NOT NULL,
  caption         TEXT,
  uploaded_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_reports_type     ON reports(type);
CREATE INDEX IF NOT EXISTS idx_reports_status   ON reports(status);
CREATE INDEX IF NOT EXISTS idx_reports_severity ON reports(severity);
CREATE INDEX IF NOT EXISTS idx_reports_location ON reports(lat, lng);
CREATE INDEX IF NOT EXISTS idx_reports_created  ON reports(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_attachments_report ON attachments(report_id);
