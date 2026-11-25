-- Read-only login for Power BI. Run once in the Neon SQL Editor, AFTER `python -m scripts.portfolio --load`
-- (the portfolio views must exist before they can be granted).
-- 1. Replace the password below with a long random one (Neon rejects weak passwords for SQL-created roles)
--    and keep it in your password manager. Never commit it.
-- 2. Check the database name: it is the part after the last "/" in your connection string (often neondb).

CREATE ROLE powerbi_reader WITH LOGIN PASSWORD 'REPLACE-WITH-A-LONG-RANDOM-PASSWORD';

GRANT CONNECT ON DATABASE neondb TO powerbi_reader;
GRANT USAGE ON SCHEMA public TO powerbi_reader;

-- Views only: the reader cannot see the memo and email text, cannot read the raw tables and cannot write.
GRANT SELECT ON v_controller_decisions, v_controller_findings,
               v_portfolio_projects, v_portfolio_statements, v_portfolio_findings TO powerbi_reader;

-- Check (should list exactly the five views):
-- SELECT table_name FROM information_schema.role_table_grants WHERE grantee = 'powerbi_reader';

-- The app and the portfolio loader recreate views with CREATE OR REPLACE and replace rows with DELETE,
-- so these grants survive app restarts and portfolio reloads.
