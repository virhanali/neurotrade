#!/bin/bash

################################################################################
# NeuroTrade Basic Auth Setup Script
# Creates .htpasswd file for additional nginx authentication layer
# Usage: ./scripts/setup-basic-auth.sh
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

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HTPASSWD_FILE="$PROJECT_DIR/nginx/.htpasswd"

echo -e "${BLUE}======================================${NC}"
echo -e "${BLUE}  NeuroTrade Basic Auth Setup${NC}"
echo -e "${BLUE}======================================${NC}\n"

# Check if htpasswd is installed
if ! command -v htpasswd >/dev/null 2>&1; then
    log_warning "htpasswd not found. Installing apache2-utils..."

    if command -v apt-get >/dev/null 2>&1; then
        sudo apt-get update && sudo apt-get install -y apache2-utils
    elif command -v yum >/dev/null 2>&1; then
        sudo yum install -y httpd-tools
    elif command -v brew >/dev/null 2>&1; then
        brew install httpd
    else
        log_error "Could not install htpasswd. Please install apache2-utils manually."
        exit 1
    fi
fi

# Get username
read -p "Enter username for basic auth [admin]: " USERNAME
USERNAME=${USERNAME:-admin}

# Create .htpasswd file
log_info "Creating .htpasswd file..."
htpasswd -c "$HTPASSWD_FILE" "$USERNAME"

log_success ".htpasswd file created at: $HTPASSWD_FILE"

# Update nginx config to enable basic auth
log_info "To enable basic auth, uncomment these lines in nginx/conf.d/neurotrade.conf:"
echo -e "${YELLOW}    auth_basic \"NeuroTrade Dashboard\";${NC}"
echo -e "${YELLOW}    auth_basic_user_file /etc/nginx/.htpasswd;${NC}"

log_info "\nThen restart nginx:"
echo -e "${BLUE}    docker-compose -f docker-compose.prod.yml restart nginx${NC}\n"

log_success "Basic auth setup complete!"
