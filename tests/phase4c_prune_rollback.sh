#!/usr/bin/env bash
# Checkpoint 4C: prove the prune's reversibility is real, not bookkeeping.
#
# Pruning removes the rollback path because Django drops a replacement from
# applied_migrations when the migrations it replaces are absent. This proves the
# archive restores that capability: after a prune the deployed 4A image is
# refused, and after a restore it starts cleanly again.
#
# Disposable projects only.
set -uo pipefail
cd "$(dirname "$0")/../deploy" || exit 2
IMG_3A=${PHASE4C_IMAGE_3A:-ghcr.io/maaz-bin-haider/financee-web:497b6650ed678bc462f85de6bff14692bffd6ace}
IMG_4A=${PHASE4C_IMAGE_4A:-ghcr.io/maaz-bin-haider/financee-web:a4f915f3e771d0769f410a3d9ee0cdb7bbc1cd00}
IMG_4B=${PHASE4C_IMAGE_4B:-financee-web:4b-local}
FAILED=0
check() { if [ "$2" = "$3" ]; then printf 'PASS: %s\n' "$1"
  else printf 'FAIL: %s (got %s, want %s)\n' "$1" "$2" "$3"; FAILED=1; fi; }

proj="p4c_rb_$(date +%s)_$$"; work=$(mktemp -d); ef="$work/e.env"
cat > "$ef" <<ENV
SECRET_KEY=x
DEBUG=False
ALLOWED_HOSTS=localhost
CSRF_TRUSTED_ORIGINS=http://localhost
DB_NAME=p
DB_USER=p
DB_PASSWORD=p
DB_HOST=db
DB_PORT=5432
ENV
export WEB_ENV_FILE="$ef"
dc() { docker compose --project-name "$proj" --env-file "$ef" -f docker-compose.yml "$@"; }
psql() { dc exec -T db psql -U p -d p -Atc "$1"; }
trap 'dc down -v >/dev/null 2>&1; rm -rf "$work"' EXIT

# Reproduce production's history: 3A applies the chain, 4A records the replacements.
WEB_IMAGE="$IMG_3A" dc up -d --wait --wait-timeout 240 db redis web >/dev/null 2>&1 || exit 1
dc cp ../tenancy/management/commands/register_bootstrap_tenant.py \
  web:/app/tenancy/management/commands/register_bootstrap_tenant.py >/dev/null 2>&1
dc exec -T web python manage.py register_bootstrap_tenant >/dev/null 2>&1
WEB_IMAGE="$IMG_4A" dc up -d --wait --wait-timeout 240 web >/dev/null 2>&1 || exit 1
WEB_IMAGE="$IMG_4B" dc up -d --force-recreate --wait --wait-timeout 240 web >/dev/null 2>&1 || exit 1
dc cp ../tenancy/management/commands/serial_only_phase4c_prune.py \
  web:/app/tenancy/management/commands/serial_only_phase4c_prune.py >/dev/null 2>&1

run4c() { dc exec -T web python manage.py serial_only_phase4c_prune "$@"; }
sha() { run4c --action inspect | python3 -c 'import json,sys;print(json.load(sys.stdin)["state_sha256"])'; }
backup() { date -u +db-backup-%Y%m%dT%H%M%SZ; }
rollback_4a() {
  # Exit status is the honest signal: a partially-applied rollback still fails,
  # and grepping its output is fragile.
  if WEB_IMAGE="$IMG_4A" dc run --rm --no-deps --entrypoint python web \
       manage.py migrate --no-input >/dev/null 2>&1; then echo ok; else echo refused; fi
}

check "before pruning, the 4A rollback target starts cleanly" "$(rollback_4a)" ok
run4c --action apply --expected "$(sha)" \
  --confirmation PRUNE-REPLACED-MIGRATION-RECORDS --backup-release "$(backup)" >/dev/null 2>&1
check "the prune left only the replacement records" \
  "$(psql "SELECT count(*) FROM django_migrations WHERE app IN ('tenancy','authentication')")" 2
# A rollback against a pruned database does not fail cleanly: the
# authentication replacement re-applies and re-records before the tenancy one
# dies on CREATE TABLE, leaving a half-applied history. Record both facts.
check "after pruning, the 4A rollback target is refused" "$(rollback_4a)" refused
check "the refused rollback left the history damaged, not merely unchanged" \
  "$(psql "SELECT count(*) FROM django_migrations WHERE app IN ('tenancy','authentication')")" 28
run4c --action restore --expected "$(sha)" \
  --confirmation RESTORE-REPLACED-MIGRATION-RECORDS --backup-release "$(backup)" >/dev/null 2>&1
check "the restore repairs the damaged history exactly" \
  "$(psql "SELECT count(*) FROM django_migrations WHERE app IN ('tenancy','authentication')")" 36
check "after restoring, the 4A rollback target starts cleanly again" "$(rollback_4a)" ok

echo
if [ "$FAILED" -eq 0 ]; then echo "PHASE4C_PRUNE_ROLLBACK=PASS"; else echo "PHASE4C_PRUNE_ROLLBACK=FAIL"; fi
exit "$FAILED"
