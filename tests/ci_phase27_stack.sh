#!/usr/bin/env bash
set -euo pipefail

gate="${1:?gate required: serial|creation-freeze|runtime-removal|metadata-inventory|compatibility|isolation|arm64|full}"
case "$gate" in
  serial|creation-freeze|runtime-removal|metadata-inventory|compatibility|isolation|arm64|full) ;;
  *) echo "unknown gate: $gate" >&2; exit 2 ;;
esac
# Never attach tests or their destructive cleanup to the default deploy project.
test_project="phase27_${gate//-/_}_$(date +%s)_$$"
work_dir=$(mktemp -d)
export WEB_ENV_FILE="$work_dir/test.env"
compose=(docker compose --project-name "$test_project"
  --env-file "$WEB_ENV_FILE" -f deploy/docker-compose.yml)
artifact_dir="${GITHUB_WORKSPACE:-.}/phase27-artifacts/$gate"
mkdir -p "$artifact_dir"

cleanup() {
  "${compose[@]}" logs --no-color >"$artifact_dir/stack.log" 2>&1 || true
  "${compose[@]}" ps --format json >"$artifact_dir/containers.json" 2>&1 || true
  "${compose[@]}" down -v >/dev/null 2>&1 || true
  rm -f "$WEB_ENV_FILE"
  rmdir "$work_dir"
}
trap cleanup EXIT

cat > "$WEB_ENV_FILE" <<'EOF'
SECRET_KEY=phase27-ci-only-not-secret
DEBUG=False
ALLOWED_HOSTS=localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=http://localhost
DB_NAME=financee
DB_USER=financee
DB_PASSWORD=ci-postgres-password
DB_HOST=db
DB_PORT=5432
REPORT_EMAIL_ENABLED=False
EOF

if [[ "$gate" != "arm64" ]]; then
  "${compose[@]}" build web
fi
"${compose[@]}" up -d
cid=$("${compose[@]}" ps -q web)
for _ in $(seq 1 90); do
  status=$(docker inspect -f '{{.State.Health.Status}}' "$cid")
  [[ "$status" == "healthy" ]] && break
  sleep 5
done
[[ "$(docker inspect -f '{{.State.Health.Status}}' "$cid")" == "healthy" ]]
"${compose[@]}" cp tests web:/app/

case "$gate" in
  serial)
    "${compose[@]}" exec -T web python manage.py check
    "${compose[@]}" exec -T web python manage.py makemigrations --check --dry-run
    "${compose[@]}" exec -T web python tests/phase24_serial_matrix.py
    "${compose[@]}" exec -T web python manage.py serial_only_phase0_audit \
      --include-continuity --strict-serial \
      >"$artifact_dir/phase0-single-serial-audit.json"
    "${compose[@]}" exec -T web python manage.py provision_tenant \
      "Phase 0 Audit Second Serial"
    if ! "${compose[@]}" exec -T web python manage.py serial_only_phase0_audit \
        --include-continuity --strict-serial \
        >"$artifact_dir/phase0-serial-only-audit.json"; then
      python3 tests/phase0_serial_only_discovery_contracts.py \
        --assert-known-ci-drift \
        "$artifact_dir/phase0-serial-only-audit.json"
    fi
    ;;
  creation-freeze) "${compose[@]}" exec -T web python tests/phase1_serial_only_creation.py ;;
  runtime-removal) "${compose[@]}" exec -T web python tests/phase2_serial_runtime_removal.py ;;
  metadata-inventory)
    "${compose[@]}" exec -T -e PHASE3_TEST_DISPOSABLE=1 web \
      python tests/phase3_metadata_inventory.py
    # Prove the stdin-only audit works in the actual deployed Phase 2 image,
    # where the new management command is not installed. No entrypoint runs.
    docker run --rm -i --read-only --tmpfs /tmp \
      --network "${test_project}_default" --env-file "$WEB_ENV_FILE" \
      -e 'PGOPTIONS=-c default_transaction_read_only=on' --entrypoint python \
      ghcr.io/maaz-bin-haider/financee-web:e44737f1f740fa936e853a3d6bbbd068a1b6d89d \
      - --strict < tenancy/management/commands/serial_only_phase3_audit.py \
      >"$artifact_dir/phase3-deployed-image-inventory.json"
    ;;
  isolation) "${compose[@]}" exec -T web python tests/phase25_four_company_isolation.py ;;
  compatibility)
    # Checkpoint 4B: the old-image half retired with the Phase 2 image it
    # pinned. That image declares inventory_mode as a concrete ORM field and
    # cannot run against a 4B database at all, and it is now two rollback
    # generations old. Rollback compatibility is proven instead by
    # tests/phase4b_migration_transition.sh against the actual rollback target.
    "${compose[@]}" exec -T -e PHASE3A_TEST_DISPOSABLE=1 web python tests/phase3a_compatibility.py \
      | tee "$artifact_dir/phase3a-compatibility.log"
    ;;
  arm64)
    "${compose[@]}" exec -T web python tests/phase27_arm64_smoke.py
    "${compose[@]}" exec -T web python tests/phase2_serial_runtime_removal.py
    "${compose[@]}" exec -T -e PHASE3A_TEST_DISPOSABLE=1 web python tests/phase3a_compatibility.py \
      | tee "$artifact_dir/phase3a-compatibility.log"
    "${compose[@]}" exec -T web python manage.py release_preflight
    ;;
  full)
    "${compose[@]}" exec -T \
      -e DJANGO_SUPERUSER_USERNAME=admin \
      -e DJANGO_SUPERUSER_PASSWORD=ci-admin-password \
      -e DJANGO_SUPERUSER_EMAIL=admin@example.com \
      web python manage.py createsuperuser --noinput
    "${compose[@]}" exec -T web python manage.py provision_tenant "CI Company Two"
    "${compose[@]}" exec -T web python tests/ci_bootstrap.py
    "${compose[@]}" exec -T web python tests/suite/run_all.py
    ;;
  *) echo "unknown gate: $gate" >&2; exit 2 ;;
esac
