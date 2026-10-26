#!/usr/bin/env bash
# Prove production helper restores supported workers, stops unsupported workers
# on rollback, and fails a candidate whose heartbeat/image health is wrong.
set -euo pipefail
scratch=$(mktemp -d)
trap 'rm -rf "$scratch"' EXIT
cat >"$scratch/docker" <<'FAKE'
#!/usr/bin/env bash
printf '%s\n' "WEB_IMAGE=${WEB_IMAGE:-} $*" >>"$WORKER_TEST_LOG"
case "$*" in
  *"run --rm --network none --entrypoint python old-image "*) exit 1;;
  *"ps -q report_worker") echo worker;;
  *"ps -q web") echo web;;
  "inspect -f {{.Image}} "*) echo sha256:matching;;
  "inspect -f {{.State.Health.Status}} "*) echo "${WORKER_TEST_HEALTH:-healthy}";;
esac
FAKE
chmod +x "$scratch/docker"
export PATH="$scratch:$PATH" WORKER_TEST_LOG="$scratch/docker.log"
WEB_IMAGE=new-image bash deploy/report_worker_control.sh start
grep -Fq 'up -d --no-deps --wait --wait-timeout 150 report_worker' "$WORKER_TEST_LOG"
: >"$WORKER_TEST_LOG"
WEB_IMAGE=old-image bash deploy/report_worker_control.sh restore
grep -Fq 'stop report_worker' "$WORKER_TEST_LOG"
if grep -Fq 'up -d' "$WORKER_TEST_LOG"; then exit 1; fi
if WEB_IMAGE=new-image WORKER_TEST_HEALTH=unhealthy bash deploy/report_worker_control.sh start; then exit 1; fi
printf '%s\n' 'PASS: matching worker start, old-image rollback stop, and unhealthy-worker rejection'

# A standalone pull deployment must also roll back if worker health fails
# AFTER HTTP health passed, rather than leaving the new web image installed.
cat >"$scratch/docker" <<'FAKE'
#!/usr/bin/env bash
printf '%s\n' "WEB_IMAGE=${WEB_IMAGE:-} $*" >>"$WORKER_TEST_LOG"
case "$*" in
  "compose -f docker-compose.yml ps -q web") echo old-container;;
  "compose -f docker-compose.yml ps -q report_worker") echo worker;;
  "inspect -f {{.Image}} "*) echo sha256:previous-image;;
  "inspect -f {{.State.Health.Status}} worker") echo unhealthy;;
  "info --format {{.DockerRootDir}}") echo /tmp;;
  "compose -f docker-compose.yml exec -T web python manage.py help release_preflight") exit 1;;
  *"run --rm --network none --entrypoint python sha256:previous-image "*) exit 1;;
esac
FAKE
cat >"$scratch/curl" <<'FAKE'
#!/usr/bin/env bash
exit 0
FAKE
chmod +x "$scratch/curl"
: >"$WORKER_TEST_LOG"
if WEB_IMAGE=candidate-image DEPLOY_HEALTH_ATTEMPTS=1 DEPLOY_HEALTH_INTERVAL_SECONDS=0 \
   bash deploy/deploy_pull.sh >"$scratch/deploy.log" 2>&1; then exit 1; fi
grep -Fq 'WEB_IMAGE=sha256:previous-image compose -f docker-compose.yml up -d --no-deps web' "$WORKER_TEST_LOG"
if grep -Eq 'WEB_IMAGE=sha256:previous-image compose.*up.*report_worker' "$WORKER_TEST_LOG"; then exit 1; fi
printf '%s\n' 'PASS: worker-health failure after successful HTTP check rolls back web and stops unsupported worker'
