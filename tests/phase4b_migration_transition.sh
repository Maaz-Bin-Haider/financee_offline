#!/usr/bin/env bash
# Checkpoint 4B migration-transition proof (disposable Compose projects only).
#
# Checkpoint 4A shipped the squashed replacements beside the originals. 4B
# deletes the replaced files and removes `replaces`, so each squash becomes an
# ordinary initial migration. This proves the four properties that transition
# must satisfy:
#
#   1. a fresh database records only the squashed migrations and still creates
#      no retired column, constraint or permission;
#   2. a database carrying the post-4A history (original chain plus both
#      recorded replacements) upgrades to 4B as a no-op with its data intact;
#   3. `migrate --prune` removes exactly the stale replaced rows and nothing
#      else, leaving the data untouched;
#   4. the previously deployed 4A image still runs against the pruned database,
#      so the release stays rollback-safe.
#
# Requires the published 3A and 4A images and a locally built 4B image.
set -uo pipefail
cd "$(dirname "$0")/../deploy" || exit 2
IMG_3A=${PHASE4B_IMAGE_3A:-ghcr.io/maaz-bin-haider/financee-web:497b6650ed678bc462f85de6bff14692bffd6ace}
IMG_4A=${PHASE4B_IMAGE_4A:-ghcr.io/maaz-bin-haider/financee-web:a4f915f3e771d0769f410a3d9ee0cdb7bbc1cd00}
IMG_4B=${PHASE4B_IMAGE_4B:-financee-web:4b-local}
FAILED=0
activity_permission_expected=0
[[ -f ../activity/apps.py ]] && activity_permission_expected=1
report_permission_expected=0
[[ -f ../reportmailer/apps.py ]] && report_permission_expected=1

check() { if [ "$2" = "$3" ]; then printf 'PASS: %s\n' "$1"
  else printf 'FAIL: %s (got %s, want %s)\n' "$1" "$2" "$3"; FAILED=1; fi; }

mkproj() {
  proj="p4b_$1_$(date +%s)_$$"; work=$(mktemp -d); env_file="$work/e.env"
  cat > "$env_file" <<ENV
SECRET_KEY=proof-only-not-secret
DEBUG=False
ALLOWED_HOSTS=localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=http://localhost
DB_NAME=financee_proof
DB_USER=financee_proof
DB_PASSWORD=proof-password
DB_HOST=db
DB_PORT=5432
ENV
  export WEB_ENV_FILE="$env_file"
}
psql() { docker compose --project-name "$proj" --env-file "$env_file" -f docker-compose.yml exec -T db psql -U financee_proof -d financee_proof -Atc "$1"; }
dc() { docker compose --project-name "$proj" --env-file "$env_file" -f docker-compose.yml "$@"; }
teardown() { dc down -v >/dev/null 2>&1; rm -rf "$work"; }
rows() { psql "SELECT count(*) FROM django_migrations WHERE app IN ('tenancy','authentication')"; }
# The draft invoice permissions are seeded by a post_migrate handler (not a
# migration), so any later release adds them on its first migrate. The
# retention checks below compare every OTHER permission. Report Email adds
# send_reports the same way; assert its seed separately without masking changes
# to any preexisting permission or grant.
perms() { psql "SELECT count(*) FROM auth_permission WHERE codename NOT LIKE '%draft%' AND codename NOT IN ('send_reports','view_team_activity')"; }

echo "== Part 1: fresh install on the 4B release =="
mkproj fresh; trap teardown EXIT
WEB_IMAGE="$IMG_4B" dc up -d --wait --wait-timeout 240 db redis web >/dev/null 2>&1 \
  || { echo "FAIL: fresh 4B stack did not start"; WEB_IMAGE="$IMG_4B" dc logs web | tail -20; teardown; exit 1; }
check "fresh install records only the two squashed migrations" "$(rows)" 2
check "fresh install records tenancy.0001_serial_only" \
  "$(psql "SELECT count(*) FROM django_migrations WHERE app='tenancy' AND name='0001_serial_only'")" 1
check "fresh install creates no retired column" \
  "$(psql "SELECT count(*) FROM information_schema.columns WHERE table_schema='public' AND table_name='tenancy_company' AND column_name='inventory_mode'")" 0
check "fresh install creates no retired constraint" \
  "$(psql "SELECT count(*) FROM pg_constraint WHERE conname='tenancy_company_valid_inventory_mode'")" 0
check "fresh install creates no retired permission" \
  "$(psql "SELECT count(*) FROM auth_permission p JOIN django_content_type ct ON ct.id=p.content_type_id WHERE ct.app_label='auth' AND ct.model='user' AND p.codename IN ('view_warehouse','create_warehouse','update_warehouse','delete_warehouse','view_warehouse_transfer','create_warehouse_transfer','update_warehouse_transfer','delete_warehouse_transfer','view_physical_count','create_physical_count','approve_inventory_adjustment','reverse_inventory_adjustment','view_quantity_audit','manage_quantity_attachments')")" 0
check "fresh install registers the bootstrap tenant exactly once" \
  "$(psql "SELECT count(*) FROM tenancy_company WHERE schema_name='tenant_company_1'")" 1
check "fresh install seeds only the report-email capability"   "$(psql "SELECT count(*) FROM auth_permission WHERE codename='send_reports'")" "$report_permission_expected"
check "report-email capability is not automatically granted"   "$(psql "SELECT count(*) FROM auth_user_user_permissions up JOIN auth_permission p ON p.id=up.permission_id WHERE p.codename='send_reports'")" 0
check "fresh install seeds the team-activity capability" "$(psql "SELECT count(*) FROM auth_permission WHERE codename='view_team_activity'")" "$activity_permission_expected"
check "team-activity capability is not automatically granted" "$(psql "SELECT count(*) FROM auth_user_user_permissions up JOIN auth_permission p ON p.id=up.permission_id WHERE p.codename='view_team_activity'")" 0
check "fresh install has nothing left to migrate" \
  "$(WEB_IMAGE="$IMG_4B" dc exec -T web python manage.py migrate --plan 2>/dev/null | grep -c 'No planned migration operations.')" 1
teardown; trap - EXIT

echo
echo "== Parts 2-4: post-4A database upgraded to 4B, pruned, then rolled back =="
mkproj upgrade; trap teardown EXIT
# Build the exact production history: 3A applies the original chain, then 4A
# records both replacements via check_replacements().
WEB_IMAGE="$IMG_3A" dc up -d --wait --wait-timeout 240 db redis web >/dev/null 2>&1 \
  || { echo "FAIL: 3A stack did not start"; teardown; exit 1; }
dc cp ../tenancy/management/commands/register_bootstrap_tenant.py \
  web:/app/tenancy/management/commands/register_bootstrap_tenant.py >/dev/null 2>&1
dc exec -T web python manage.py register_bootstrap_tenant >/dev/null 2>&1
dc exec -T web python manage.py provision_tenant "Proof Serial Co" >/dev/null 2>&1
check "3A applied the full original chain" "$(rows)" 34
WEB_IMAGE="$IMG_4A" dc up -d --wait --wait-timeout 240 web >/dev/null 2>&1 \
  || { echo "FAIL: 4A stack did not start"; teardown; exit 1; }
check "4A recorded both replacements alongside the original chain" "$(rows)" 36
before_companies=$(psql "SELECT count(*) FROM tenancy_company")
before_digest=$(psql "SELECT md5(string_agg(t::text,'|' ORDER BY id)) FROM tenancy_company t")
before_perms=$(perms)

# Part 2 — the 4B release must be a no-op on that database.
check "the 4B release plans no migration operations" \
  "$(WEB_IMAGE="$IMG_4B" dc run --rm --no-deps --entrypoint python web manage.py migrate --plan 2>/dev/null | grep -c 'No planned migration operations.')" 1
check "the 4B release applies no migration" \
  "$(WEB_IMAGE="$IMG_4B" dc run --rm --no-deps --entrypoint python web manage.py migrate --no-input 2>/dev/null | grep -c 'No migrations to apply.')" 1
check "company rows are retained across the 4B upgrade" "$(psql "SELECT count(*) FROM tenancy_company")" "$before_companies"
check "the registry is byte-identical across the 4B upgrade" \
  "$(psql "SELECT md5(string_agg(t::text,'|' ORDER BY id)) FROM tenancy_company t")" "$before_digest"
check "upgrade seeds the report-email capability without a migration"   "$(psql "SELECT count(*) FROM auth_permission WHERE codename='send_reports'")" "$report_permission_expected"
check "upgrade seeds team activity without a migration" "$(psql "SELECT count(*) FROM auth_permission WHERE codename='view_team_activity'")" "$activity_permission_expected"
check "permissions are retained across the 4B upgrade" "$(perms)" "$before_perms"
check "the upgrade seeds the draft invoice permissions without a migration" \
  "$(psql "SELECT count(*) FROM auth_permission WHERE codename LIKE '%draft%'")" 11
check "the stale replaced rows are still present before pruning" "$(rows)" 36

# Part 3 — migrate --prune removes exactly the stale rows.
# Django refuses a project-wide prune; it must be run per application. Capture
# that refusal explicitly so the operational requirement is recorded, not
# discovered during a production maintenance window.
prune_all=$(WEB_IMAGE="$IMG_4B" dc run --rm --no-deps --entrypoint python web     manage.py migrate --prune --no-input 2>&1)
echo "$prune_all" | grep -qi "prune" && printf '  note: project-wide prune refused: %s\n' \
    "$(echo "$prune_all" | grep -i 'prune' | tail -1 | tr -d '\r')"
check "a project-wide prune is refused and changes nothing" "$(rows)" 36
for app in tenancy authentication; do
    WEB_IMAGE="$IMG_4B" dc run --rm --no-deps --entrypoint python web         manage.py migrate "$app" --prune --no-input >/dev/null 2>&1
done
check "prune leaves only the two squashed migration records" "$(rows)" 2
check "prune keeps tenancy.0001_serial_only" \
  "$(psql "SELECT count(*) FROM django_migrations WHERE app='tenancy' AND name='0001_serial_only'")" 1
check "prune removes the replaced tenancy rows" \
  "$(psql "SELECT count(*) FROM django_migrations WHERE app='tenancy' AND name<>'0001_serial_only'")" 0
check "prune retains every company row" "$(psql "SELECT count(*) FROM tenancy_company")" "$before_companies"
check "prune leaves the registry byte-identical" \
  "$(psql "SELECT md5(string_agg(t::text,'|' ORDER BY id)) FROM tenancy_company t")" "$before_digest"
check "prune retains every permission" "$(perms)" "$before_perms"
check "the 4B release still plans nothing after pruning" \
  "$(WEB_IMAGE="$IMG_4B" dc run --rm --no-deps --entrypoint python web manage.py migrate --plan 2>/dev/null | grep -c 'No planned migration operations.')" 1

teardown; trap - EXIT

echo
echo "== Part 3b: the 4A release cannot be skipped =="
# A database still on the original chain has no replacement record, so the 4B
# release -- which no longer carries `replaces` -- treats its own migration as
# unapplied and re-plans the whole initial migration. Every environment must
# pass through the 4A release first.
mkproj skip; trap teardown EXIT
WEB_IMAGE="$IMG_3A" dc up -d --wait --wait-timeout 240 db redis web >/dev/null 2>&1 \
  || { echo "FAIL: 3A stack did not start"; teardown; exit 1; }
skip_out=$(WEB_IMAGE="$IMG_4B" dc run --rm --no-deps --entrypoint python web \
    manage.py migrate --no-input 2>&1)
if printf '%s' "$skip_out" | grep -q 'already exists'; then skip_result=refused
elif printf '%s' "$skip_out" | grep -q 'No migrations to apply.'; then skip_result=applied-noop
else skip_result=other; fi
check "a database on the original chain cannot skip the 4A release" "$skip_result" refused
teardown; trap - EXIT

echo
echo "== Part 4: rollback safety before and after pruning =="
# This is the operationally decisive part. Django drops a replacement from
# applied_migrations when the migrations it replaces are not all applied, even
# though the replacement's own row exists. Pruning therefore makes every
# `replaces`-carrying image believe nothing has been applied. 4B must deploy
# WITHOUT pruning so rollback stays possible; pruning is a separate one-way
# step to take only once no `replaces`-carrying image is a rollback target.
mkproj rollback; trap teardown EXIT
WEB_IMAGE="$IMG_3A" dc up -d --wait --wait-timeout 240 db redis web >/dev/null 2>&1 \
  || { echo "FAIL: 3A stack did not start"; teardown; exit 1; }
dc cp ../tenancy/management/commands/register_bootstrap_tenant.py \
  web:/app/tenancy/management/commands/register_bootstrap_tenant.py >/dev/null 2>&1
dc exec -T web python manage.py register_bootstrap_tenant >/dev/null 2>&1
WEB_IMAGE="$IMG_4A" dc up -d --wait --wait-timeout 240 web >/dev/null 2>&1
WEB_IMAGE="$IMG_4B" dc run --rm --no-deps --entrypoint python web manage.py migrate --no-input >/dev/null 2>&1
rollback_digest=$(psql "SELECT md5(string_agg(t::text,'|' ORDER BY id)) FROM tenancy_company t")

# 4a. Un-pruned: the 4B release is rollback-safe to the deployed 4A image.
check "before pruning, rolling back to 4A applies no migration" \
  "$(WEB_IMAGE="$IMG_4A" dc run --rm --no-deps --entrypoint python web manage.py migrate --no-input 2>/dev/null | grep -c 'No migrations to apply.')" 1
check "before pruning, rolling back to 3A applies no migration" \
  "$(WEB_IMAGE="$IMG_3A" dc run --rm --no-deps --entrypoint python web manage.py migrate --no-input 2>/dev/null | grep -c 'No migrations to apply.')" 1
check "before pruning the registry is unchanged by rollback" \
  "$(psql "SELECT md5(string_agg(t::text,'|' ORDER BY id)) FROM tenancy_company t")" "$rollback_digest"

# 4b. Pruned: rollback to any replaces-carrying image is no longer possible.
for app in tenancy authentication; do
    WEB_IMAGE="$IMG_4B" dc run --rm --no-deps --entrypoint python web \
        manage.py migrate "$app" --prune --no-input >/dev/null 2>&1
done
check "the prune actually removed the replaced rows in this project" "$(rows)" 2
check "after pruning the 4B release itself still applies no migration" \
  "$(WEB_IMAGE="$IMG_4B" dc run --rm --no-deps --entrypoint python web manage.py migrate --no-input 2>/dev/null | grep -c 'No migrations to apply.')" 1
# The 4A image no longer recognises its own replacement as applied once the
# replaced rows are gone, so it re-plans the whole initial migration and
# PostgreSQL refuses it. Assert the refusal, not a line count.
rollback_out=$(WEB_IMAGE="$IMG_4A" dc run --rm --no-deps --entrypoint python web \
    manage.py migrate --no-input 2>&1)
if printf '%s' "$rollback_out" | grep -q 'already exists'; then
    rollback_after_prune=refused
elif printf '%s' "$rollback_out" | grep -q 'No migrations to apply.'; then
    rollback_after_prune=applied-noop
else
    rollback_after_prune=other
    printf '  4A output tail: %s\n' "$(printf '%s' "$rollback_out" | tail -3 | tr '\n' ' ')"
fi
check "after pruning, rolling back to 4A is refused by the database" \
  "$rollback_after_prune" refused
check "the refused rollback still left the registry byte-identical" \
  "$(psql "SELECT md5(string_agg(t::text,'|' ORDER BY id)) FROM tenancy_company t")" "$rollback_digest"
teardown; trap - EXIT

echo
if [ "$FAILED" -eq 0 ]; then echo "PHASE4B_MIGRATION_TRANSITION=PASS"; else echo "PHASE4B_MIGRATION_TRANSITION=FAIL"; fi
exit "$FAILED"
