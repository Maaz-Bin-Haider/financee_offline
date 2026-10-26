#!/usr/bin/env bash
# Read-only Phase 26 telemetry capture for the EC2 host during a T7 run.
set -euo pipefail

echo "timestamp=$(date --iso-8601=seconds)"
echo "architecture=$(uname -m)"
echo "kernel=$(uname -r)"
echo "uptime=$(uptime)"
echo "cpu_count=$(nproc)"
free -h
df -h /
vmstat 1 5
docker stats --no-stream
docker inspect -f '{{.Name}} restarts={{.RestartCount}} oom={{.State.OOMKilled}} status={{.State.Status}}' \
  deploy-db-1 deploy-web-1 deploy-redis-1 deploy-nginx-1

# When the AWS CLI and instance-role permission are available, record the
# burst-credit metrics that a local constrained run cannot reproduce.
if command -v aws >/dev/null 2>&1; then
  token=$(curl -fsS -X PUT -H 'X-aws-ec2-metadata-token-ttl-seconds: 60' \
    http://169.254.169.254/latest/api/token || true)
  instance_id=$(curl -fsS -H "X-aws-ec2-metadata-token: $token" \
    http://169.254.169.254/latest/meta-data/instance-id || true)
  region=$(curl -fsS -H "X-aws-ec2-metadata-token: $token" \
    http://169.254.169.254/latest/meta-data/placement/region || true)
  if [[ -n "$instance_id" && -n "$region" ]]; then
    start=$(date -u -d '20 minutes ago' +%FT%TZ)
    end=$(date -u +%FT%TZ)
    for metric in CPUUtilization CPUCreditBalance CPUSurplusCreditBalance; do
      aws cloudwatch get-metric-statistics \
        --region "$region" --namespace AWS/EC2 --metric-name "$metric" \
        --dimensions "Name=InstanceId,Value=$instance_id" \
        --start-time "$start" --end-time "$end" --period 60 \
        --statistics Average Maximum
    done
  fi
fi
