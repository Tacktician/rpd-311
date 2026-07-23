-- Creates the three RPD 311 databases in the single local Postgres container.
-- In EKS these are separate databases on a shared RDS instance; locally they
-- share one container. Runs once on first startup (empty data volume).
--
-- Table schemas are owned by each service (see CLAUDE.md > Database schemas) and
-- are applied by the service on boot / via its own migrations — not here.

CREATE DATABASE reports;
CREATE DATABASE triage;
CREATE DATABASE status;
