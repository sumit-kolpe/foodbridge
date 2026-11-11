-- FoodBridge - read-only guest account for TAs (Milestone 3 credentials)
-- Run once as the RDS master user, connected to the foodbridge database.
-- Replace the password with a strong one (16+ chars, mixed) before running.

CREATE ROLE fb_guest WITH LOGIN PASSWORD 'REPLACE_WITH_STRONG_PASSWORD';

GRANT CONNECT ON DATABASE foodbridge TO fb_guest;
GRANT USAGE ON SCHEMA public TO fb_guest;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO fb_guest;
-- tables created later (e.g. views, cache tables) are readable too
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO fb_guest;

-- protect the instance from runaway guest queries
ALTER ROLE fb_guest SET statement_timeout = '600s';   -- unoptimized Q10/Q12 can take minutes
ALTER ROLE fb_guest CONNECTION LIMIT 5;

-- check: should list SELECT on all five tables
SELECT table_name, privilege_type
FROM information_schema.role_table_grants
WHERE grantee = 'fb_guest'
ORDER BY table_name;
