#!/bin/bash
set -e

echo "🏈 Fantasy Baseball Draft Tool - Deployment Script"
echo ""

# Check if running as root
if [ "$EUID" -eq 0 ]; then 
   echo "⚠️  Please don't run as root (use your regular user account)"
   exit 1
fi

# Check Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker not found. Install with:"
    echo "   sudo apt install -y docker.io docker-compose"
    exit 1
fi

# Check if .htpasswd exists
if [ ! -f .htpasswd ]; then
    echo "❌ .htpasswd not found. Create it with:"
    echo "   htpasswd -c .htpasswd your_username"
    echo "   (Install htpasswd: sudo apt install apache2-utils)"
    exit 1
fi

# Check if SSL certs exist
if [ ! -f ssl/fullchain.pem ] || [ ! -f ssl/privkey.pem ]; then
    echo "⚠️  SSL certificates not found in ssl/"
    echo ""
    read -p "Use self-signed certificate for testing? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        mkdir -p ssl
        openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
          -keyout ssl/privkey.pem \
          -out ssl/fullchain.pem \
          -subj "/CN=draft.noahbrown.io" \
          2>/dev/null
        echo "✅ Created self-signed certificate"
    else
        echo "❌ SSL certificates required. See DEPLOYMENT.md for setup instructions."
        exit 1
    fi
fi

# Create data directory
mkdir -p data

# Build and start
echo ""
echo "🔨 Building Docker image..."
docker-compose build

echo ""
echo "🚀 Starting services..."
docker-compose up -d

echo ""
echo "⏳ Waiting for services to be healthy..."
sleep 5

# Check health
if docker-compose ps | grep -q "Up"; then
    echo ""
    echo "✅ Deployment successful!"
    echo ""
    echo "📍 Access your app at: https://draft.noahbrown.io"
    echo "🔐 Login with credentials from .htpasswd"
    echo ""
    echo "📋 Useful commands:"
    echo "   docker-compose logs -f    # View logs"
    echo "   docker-compose restart    # Restart services"
    echo "   docker-compose down       # Stop services"
else
    echo ""
    echo "⚠️  Services may not be healthy. Check logs:"
    echo "   docker-compose logs"
fi
