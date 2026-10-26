#!/usr/bin/env bash
# =============================================================================
# run_tests.sh — run the full functional test battery against the LOCAL stack.
# -----------------------------------------------------------------------------
# Usage (from your project root, the folder that contains tests/ and manage.py):
#
#     ./tests/run_tests.sh            # copy tests into the container + run both
#     ./tests/run_tests.sh --reset    # also wipe + re-provision tenants first
#
# It figures out where your compose file lives (root or ./deploy), copies the
# tests/ folder INTO the running web container (so you don't have to rebuild the
# image), then runs both harnesses inside that container — which already has
# Django, psycopg2 and the DB credentials (DB_HOST=db, etc.).
# =============================================================================
set -euo pipefail

# --- locate repo root (this script lives in <root>/tests/) -------------------
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# --- locate the compose file -------------------------------------------------
CF="${COMPOSE_FILE:-}"
if [[ -z "$CF" ]]; then
  for cand in "$ROOT/docker-compose.yml" "$ROOT/deploy/docker-compose.yml" \
              "$ROOT/compose.yaml" "$ROOT/deploy/compose.yaml"; do
    [[ -f "$cand" ]] && { CF="$cand"; break; }
  done
fi
if [[ -z "$CF" || ! -f "$CF" ]]; then
  echo "ERROR: could not find a docker-compose file."
  echo "       Set COMPOSE_FILE=/path/to/docker-compose.yml and re-run."
  exit 1
fi
CF_DIR="$(cd "$(dirname "$CF")" && pwd)"
echo "==> Using compose file: $CF"

# Run compose from the compose file's directory so its relative volume paths
# (e.g. ../build_multitenant_db.sql) resolve exactly as in your normal workflow.
dc() { ( cd "$CF_DIR" && docker compose -f "$CF" "$@" ); }

# --- pick the web service/container ------------------------------------------
WEB_SVC="${WEB_SERVICE:-web}"
if ! dc ps --services 2>/dev/null | grep -qx "$WEB_SVC"; then
  echo "ERROR: service '$WEB_SVC' not found in compose. Services available:"
  dc ps --services || true
  echo "       Set WEB_SERVICE=<name> and re-run."
  exit 1
fi

# --- copy tests/ into the container at /app/tests (no rebuild needed) ---------
echo "==> Copying tests/ into the $WEB_SVC container at /app/tests"
dc exec -T "$WEB_SVC" sh -c 'rm -rf /app/tests' >/dev/null 2>&1 || true
dc cp "$ROOT/tests" "$WEB_SVC:/app/tests"

# --- optional reset ----------------------------------------------------------
if [[ "${1:-}" == "--reset" ]]; then
  echo "==> --reset: DROPPING and re-provisioning every tenant schema."
  echo "    This ERASES all data in the tenant schemas (masters, invoices, ledgers)."
  echo "    Shared 'public' data (users, company list) is kept. Ctrl-C now to abort."
  sleep 3
  dc exec -T "$WEB_SVC" python manage.py shell <<'PY'
from django.db import connection
from tenancy.models import Company
from tenancy.provisioning import provision_schema
from tenancy.utils import validate_schema_name
for c in Company.objects.all():
    s = c.schema_name
    validate_schema_name(s)
    with connection.cursor() as cur:
        cur.execute(f'DROP SCHEMA IF EXISTS "{s}" CASCADE')
    provision_schema(s, force=True)
    print("re-provisioned", s)
PY
fi

echo
echo "############################################################"
echo "# 1/2  DB-LEVEL HARNESS (every entry type + every report)  #"
echo "############################################################"
dc exec -T "$WEB_SVC" python tests/test_system.py

echo
echo "############################################################"
echo "# 2/2  HTTP VIEW-LAYER HARNESS (real endpoints)            #"
echo "############################################################"
dc exec -T "$WEB_SVC" python tests/test_http.py

echo
echo "==> Done. Review any FAIL lines above."
