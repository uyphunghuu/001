#!/bin/bash
set -e

echo "📦 Installing MinIO client (mc)..."

# Install MC via curl
curl -sSf https://dl.min.io/client/mc/release/linux-amd64/mc -o /usr/local/bin/mc
chmod +x /usr/local/bin/mc

# Configure MC to connect to local MinIO
echo "⚙️ Configuring MC..."
mc config host add local http://localhost:9000 minioadmin minioadmin

# Create bronze bucket if it doesn't exist
echo "🗄️ Creating bronze bucket: gmail-raw"
mc mb local/gmail-raw || true

# Set policy for bronze bucket
echo "🔐 Setting bucket policy..."
mc policy set download local/gmail-raw

echo "✅ MinIO client setup complete"
echo "   Bucket: local/gmail-raw"
echo "   Console: http://localhost:9001"
echo "   API: http://localhost:9000"