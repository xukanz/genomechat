#!/bin/bash
# restart_sandbox.sh - Restart sandbox container with environment variables from .env file

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Check if .env file exists
if [ ! -f .env ]; then
    echo "❌ Error: .env file not found in $SCRIPT_DIR"
    echo "Please create a .env file with your AWS credentials"
    exit 1
fi

# Source the .env file to load environment variables
set -a  # Automatically export all variables
source .env
set +a

echo "🔄 Stopping existing sandbox container..."
docker stop genomechat-sandbox 2>/dev/null || true
docker rm genomechat-sandbox 2>/dev/null || true

echo "🚀 Starting sandbox container with environment variables..."
docker run -d \
  --name genomechat-sandbox \
  -p 8080:8080 \
  -e AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID}" \
  -e AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY}" \
  -e AWS_SESSION_TOKEN="${AWS_SESSION_TOKEN}" \
  -e AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-us-east-1}" \
  -e AWS_DEFAULT_BUCKET="${AWS_DEFAULT_BUCKET}" \
  -e ALLOWED_S3_BUCKETS="${ALLOWED_S3_BUCKETS}" \
  --restart unless-stopped \
  genomechat-sandbox:latest

echo "✅ Sandbox container started successfully!"
echo ""
echo "📋 Container info:"
docker ps --filter "name=genomechat-sandbox" --format "table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}"

echo ""
echo "🔍 Verifying AWS configuration..."
sleep 2
docker logs genomechat-sandbox 2>&1 | grep -E "\[ENV\]|AWS_DEFAULT_BUCKET" | tail -5

echo ""
echo "💡 To view logs: docker logs -f genomechat-sandbox"
