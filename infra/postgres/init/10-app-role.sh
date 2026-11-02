#!/bin/sh
# Creates the least-privilege runtime role the API connects as (D10 H-5). Runs once, on a fresh
# data volume (postgres image entrypoint). Migrations (as POSTGRES_USER, the schema owner) grant it
# SELECT/INSERT/UPDATE on ordinary tables and SELECT/INSERT only on the append-only ones.
# Staging/production create this role in their provisioning, with the password from their secrets.
set -eu
: "${APP_DB_PASSWORD:?APP_DB_PASSWORD must be set}"
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v app_password="$APP_DB_PASSWORD" <<'SQL'
CREATE ROLE insmartfix_app LOGIN NOSUPERUSER NOCREATEROLE NOCREATEDB NOBYPASSRLS
  PASSWORD :'app_password';
SQL
