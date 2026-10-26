#!/usr/bin/env bash
# Simulate a failed deploy health check and prove the previous image is used.
set -euo pipefail
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
log="$tmp/docker.log"

cat >"$tmp/docker" <<'EOF'
#!/usr/bin/env bash
echo "WEB_IMAGE=${WEB_IMAGE:-} $*" >>"${PHASE27_FAKE_LOG}"
case "$*" in
  "compose -f docker-compose.yml ps -q web") echo old-container ;;
  "inspect -f {{.Image}} old-container") echo sha256:previous-image ;;
  "info --format {{.DockerRootDir}}") echo /tmp ;;
  "compose -f docker-compose.yml exec -T web python manage.py help release_preflight") exit 1 ;;
  *) exit 0 ;;
esac
EOF
cat >"$tmp/curl" <<'EOF'
#!/usr/bin/env bash
exit 1
EOF
chmod +x "$tmp/docker" "$tmp/curl"

set +e
(
  cd deploy
  PATH="$tmp:$PATH" PHASE27_FAKE_LOG="$log" \
    WEB_IMAGE=example.invalid/financee:new \
    DEPLOY_HEALTH_ATTEMPTS=1 DEPLOY_HEALTH_INTERVAL_SECONDS=0 \
    bash deploy_pull.sh
) >/dev/null 2>&1
status=$?
set -e

[[ $status -ne 0 ]]
grep -q "compose -f docker-compose.yml up -d --no-deps web" "$log"
grep -q "sha256:previous-image" "$log"
echo "PASS: failed health check selects and recreates the previous web image"
