#!/bin/bash
set -e

echo "Setting up MinIO client (mc)..."

# Install curl if not available
if ! command -v curl &> /dev/null; then
    echo "Installing curl..."
    apt-get update && apt-get install -y curl
fi

# Download and install mc
curl -sSf https://dl.min.io/client/mc/release/linux-amd64/mc -o /usr/local/bin/mc
chmod +x /usr/local/bin/mc

# Configure mc
echo "Configuring mc..."
mc config host add local http://localhost:9000 minioadmin minioadmin
mc mb local/gmail-raw || true
mc policy set download local/gmail-raw

echo "✅ MinIO client setup complete"
echo "   Bucket: local/gmail-raw"
echo "   Console: http://localhost:9001"
echo "   API: http://localhost:9000" > /tmp/setup_complete