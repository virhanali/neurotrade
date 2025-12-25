#!/bin/bash

################################################################################
# NeuroTrade SSL Setup Script (Let's Encrypt)
# Usage: sudo ./scripts/setup-ssl.sh yourdomain.com
################################################################################

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }

# Check if domain provided
if [ -z "$1" ]; then
    log_error "Usage: $0 <your-domain.com>"
    log_info "Example: $0 neurotrade.yourdomain.com"
    exit 1
fi

DOMAIN=$1
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SSL_DIR="$PROJECT_DIR/nginx/ssl"

log_info "Setting up SSL for domain: $DOMAIN"

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    log_error "Please run as root (sudo $0 $DOMAIN)"
    exit 1
fi

# Install certbot
log_info "Installing certbot..."
if command -v apt-get >/dev/null 2>&1; then
    apt-get update
    apt-get install -y certbot
elif command -v yum >/dev/null 2>&1; then
    yum install -y certbot
else
    log_error "Unsupported package manager. Please install certbot manually."
    exit 1
fi

# Stop nginx temporarily
log_info "Stopping nginx container..."
docker-compose -f "$PROJECT_DIR/docker-compose.prod.yml" stop nginx || true

# Obtain certificate
log_info "Obtaining SSL certificate from Let's Encrypt..."
certbot certonly --standalone \
    -d "$DOMAIN" \
    --non-interactive \
    --agree-tos \
    --email admin@$DOMAIN \
    --preferred-challenges http

# Copy certificates to project
log_info "Copying certificates to project..."
mkdir -p "$SSL_DIR"
cp /etc/letsencrypt/live/$DOMAIN/fullchain.pem "$SSL_DIR/fullchain.pem"
cp /etc/letsencrypt/live/$DOMAIN/privkey.pem "$SSL_DIR/privkey.pem"
chmod 644 "$SSL_DIR/fullchain.pem"
chmod 600 "$SSL_DIR/privkey.pem"

# Update nginx config with domain
log_info "Updating nginx configuration..."
sed -i "s/server_name _;/server_name $DOMAIN;/g" "$PROJECT_DIR/nginx/conf.d/neurotrade.conf"

# Restart nginx
log_info "Restarting nginx..."
docker-compose -f "$PROJECT_DIR/docker-compose.prod.yml" up -d nginx

log_success "SSL certificate installed successfully!"
log_info "Certificate will auto-renew via certbot"
log_info "Your site is now available at: https://$DOMAIN"

# Setup auto-renewal
log_info "Setting up auto-renewal cron job..."
(crontab -l 2>/dev/null; echo "0 0 * * * certbot renew --quiet && docker-compose -f $PROJECT_DIR/docker-compose.prod.yml restart nginx") | crontab -

log_success "Auto-renewal configured (runs daily at midnight)"
