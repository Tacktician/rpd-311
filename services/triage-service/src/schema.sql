-- triage-service schema (database: triage). Applied idempotently on boot by
-- db.migrate(). Mirrors CLAUDE.md > Database schemas > triage-service.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

DO $$ BEGIN
  CREATE TYPE assignment_status AS ENUM (
    'PENDING', 'ACKNOWLEDGED', 'COMPLETED', 'CANCELLED', 'ESCALATED'
  );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  CREATE TYPE department AS ENUM (
    'PUBLIC_WORKS', 'RPD_NON_EMERGENCY', 'RPD_EMERGENCY', 'SANITATION', 'STARS_UNIT'
  );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  CREATE TYPE severity_level AS ENUM ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS assignments (
  assignment_id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  report_id               UUID NOT NULL UNIQUE,
  assigned_severity       severity_level NOT NULL,
  classification_reason   TEXT,
  immediate_escalation    BOOLEAN NOT NULL DEFAULT FALSE,
  status                  assignment_status NOT NULL DEFAULT 'PENDING',
  acknowledged_by         TEXT,
  acknowledged_at         TIMESTAMPTZ,
  triaged_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS assignment_departments (
  id              SERIAL PRIMARY KEY,
  assignment_id   UUID NOT NULL REFERENCES assignments(assignment_id) ON DELETE CASCADE,
  department      department NOT NULL,
  is_primary      BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS routing_log (
  id              SERIAL PRIMARY KEY,
  assignment_id   UUID NOT NULL REFERENCES assignments(assignment_id),
  event           TEXT NOT NULL,
  detail          TEXT,
  logged_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_assignments_report    ON assignments(report_id);
CREATE INDEX IF NOT EXISTS idx_assignments_status    ON assignments(status);
CREATE INDEX IF NOT EXISTS idx_assignments_severity  ON assignments(assigned_severity);
CREATE INDEX IF NOT EXISTS idx_dept_assignment       ON assignment_departments(assignment_id);
CREATE INDEX IF NOT EXISTS idx_dept_department       ON assignment_departments(department);
