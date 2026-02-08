# Fantasy Baseball Draft Tool - Deployment Guide

## Overview

This guide covers self-hosting the Fantasy Baseball Draft Tool on Vernon (your VPS) at `draft.noahbrown.io` with Docker, nginx reverse proxy, and HTTP Basic Authentication.

## Architecture

```
Internet → nginx (reverse proxy + auth) → Streamlit app (Docker)
           ↓
        SSL/TLS + Basic Auth
```

**Why this approach:**
- ✅ **HTTP Basic Auth** - Simple, no code changes needed, browser-native
- ✅ **nginx reverse proxy** - SSL termination, rate limiting, security headers
- ✅ **Docker** - Clean isolation, easy updates
- ✅ **Lightweight** - Works on 1.9GB RAM VPS

---

## Prerequisites

1. **Domain DNS**: Point `draft.noahbrown.io` A record to Vernon's IP (64.227.82.135)
2. **Ports open**: 80 (HTTP), 443 (HTTPS)
3. **Docker installed** on Vernon

---

## Initial Setup

### 1. Install Docker (if not already installed)

```bash
# On Vernon
sudo apt update
sudo apt install -y docker.io docker-compose
sudo systemctl enable docker
sudo systemctl start docker

# Add your user to docker group (logout/login after)
sudo usermod -aG docker $USER
```

### 2. Clone/Update the Repository

```bash
cd ~/projects/Fantasy-Baseball-Draft-Tool
git pull  # Get latest code including deployment files
```

### 3. Create HTTP Basic Auth Password

```bash
# Install htpasswd utility
sudo apt install -y apache2-utils

# Create password file (replace 'noah' with your username)
htpasswd -c .htpasswd noah

# You'll be prompted to enter a password
# For league members, add more users:
# htpasswd .htpasswd leaguemate1
# htpasswd .htpasswd leaguemate2
```

### 4. Set Up SSL Certificates

**Option A: Let's Encrypt (Recommended for production)**

```bash
# Install certbot
sudo apt install -y certbot

# Get certificate (stop any services on port 80 first)
sudo certbot certonly --standalone -d draft.noahbrown.io

# Certificates will be at: /etc/letsencrypt/live/draft.noahbrown.io/

# Copy to project directory
mkdir -p ssl
sudo cp /etc/letsencrypt/live/draft.noahbrown.io/fullchain.pem ssl/
sudo cp /etc/letsencrypt/live/draft.noahbrown.io/privkey.pem ssl/
sudo chown $USER:$USER ssl/*.pem
chmod 600 ssl/privkey.pem

# Set up auto-renewal
sudo certbot renew --dry-run
```

**Option B: Self-Signed Certificate (Testing only)**

```bash
mkdir -p ssl
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout ssl/privkey.pem \
  -out ssl/fullchain.pem \
  -subj "/CN=draft.noahbrown.io"
```

### 5. Create Data Directory

```bash
# Persistent storage for SQLite database
mkdir -p data
```

---

## Deployment

### Build and Start Services

```bash
# Build the Docker image
docker-compose build

# Start services in background
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f
```

### Verify Deployment

1. **Check health**: `curl http://localhost:8501/_stcore/health`
2. **Access via browser**: https://draft.noahbrown.io
3. **Login** with username/password you set in .htpasswd
4. **Import projections** and start drafting!

---

## Day-to-Day Operations

### View Logs

```bash
# All services
docker-compose logs -f

# Just the app
docker-compose logs -f app

# Last 100 lines
docker-compose logs --tail=100
```

### Restart Services

```bash
# Restart everything
docker-compose restart

# Just the app (after code changes)
docker-compose restart app
```

### Update the Application

```bash
# Pull latest code
git pull

# Rebuild and restart
docker-compose build
docker-compose up -d
```

### Backup Draft Data

```bash
# Backup SQLite database
cp data/draft.db backups/draft-$(date +%Y%m%d).db

# Or automated backup script
echo "0 2 * * * cp ~/projects/Fantasy-Baseball-Draft-Tool/data/draft.db ~/backups/draft-\$(date +\%Y\%m\%d).db" | crontab -
```

### Stop Services

```bash
# Stop but keep containers
docker-compose stop

# Stop and remove containers
docker-compose down

# Stop and remove everything including volumes
docker-compose down -v
```

---

## Troubleshooting

### App won't start

```bash
# Check logs
docker-compose logs app

# Common issues:
# - Missing requirements.txt dependencies
# - Port 8501 already in use
# - Permissions on data/ directory
```

### Can't access via browser

```bash
# Check nginx is running
docker-compose ps nginx

# Check nginx logs
docker-compose logs nginx

# Verify port 443 is open
sudo ufw status
```

### Authentication not working

```bash
# Verify .htpasswd file exists and is mounted
docker-compose exec nginx cat /etc/nginx/.htpasswd

# Test password
htpasswd -v .htpasswd noah
```

### SSL certificate issues

```bash
# Check certificate expiry
openssl x509 -in ssl/fullchain.pem -noout -dates

# Renew Let's Encrypt cert
sudo certbot renew
sudo cp /etc/letsencrypt/live/draft.noahbrown.io/*.pem ssl/
docker-compose restart nginx
```

---

## Security Considerations

**Current Setup:**
- ✅ HTTPS only (HTTP redirects to HTTPS)
- ✅ HTTP Basic Auth (username/password)
- ✅ Non-root user in container
- ✅ Rate limiting (10 req/s per IP)
- ✅ Security headers (XSS, clickjacking protection)
- ✅ Isolated Docker network

**Limitations:**
- ⚠️ Basic Auth credentials sent with every request (secure over HTTPS)
- ⚠️ No session management or user roles
- ⚠️ Database is single SQLite file (not concurrent-safe across multiple instances)

**Recommendations:**
- 🔐 Use strong passwords (20+ characters)
- 🔐 Don't share .htpasswd file publicly
- 🔐 Rotate passwords periodically
- 🔐 Monitor nginx access logs for suspicious activity
- 🔐 Keep SSL certificates renewed
- 🔐 Regular backups of data/draft.db

---

## Resource Usage

**Expected on 1.9GB RAM VPS:**
- Streamlit app: ~256-512MB
- nginx: ~10-20MB
- Docker overhead: ~50MB
- **Total: ~350-600MB** (leaves 1.3GB for system)

Monitor with:
```bash
docker stats
```

If memory is tight:
- Reduce `deploy.resources.limits.memory` in docker-compose.yml
- Consider upgrading to 2GB+ VPS for smoother experience

---

## Adding League Members

To give access to league mates:

```bash
# Add new user
htpasswd .htpasswd leaguemate1

# Restart nginx to pick up changes
docker-compose restart nginx

# Share credentials securely (not via plain text!)
```

**Important:** Each user will see the SAME draft data. This is a single-league tool, not multi-tenant.

---

## Maintenance Schedule

**Weekly:**
- Check logs for errors: `docker-compose logs --tail=100`
- Backup database: `cp data/draft.db backups/`

**Monthly:**
- Review nginx access logs for unusual activity
- Check SSL cert expiry: `openssl x509 -in ssl/fullchain.pem -noout -dates`
- Update Docker images: `docker-compose pull && docker-compose up -d`

**Before Draft Day:**
- Test deployment: https://draft.noahbrown.io
- Import latest projections
- Verify all league members can login
- Backup existing data if any

---

## Uninstall

```bash
# Stop and remove containers
docker-compose down -v

# Remove images
docker rmi fantasy-baseball-draft-tool_app

# Clean up files (CAUTION: removes data!)
rm -rf data/ ssl/ .htpasswd
```

---

## Support

For issues with:
- **The app itself**: Check the main repository README
- **Deployment**: Review this guide and check logs
- **Vernon VPS**: Verify firewall rules, DNS, and system resources
