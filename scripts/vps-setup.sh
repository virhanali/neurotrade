#!/bin/bash

################################################################################
# NeuroTrade VPS Initial Setup Script
# Run this on a fresh Ubuntu VPS to prepare for deployment
# Usage: curl -fsSL https://raw.githubusercontent.com/your-repo/neurotrade/main/scripts/vps-setup.sh | bash
# Or: wget -qO- https://raw.githubusercontent.com/your-repo/neurotrade/main/scripts/vps-setup.sh | bash
################################################################################

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_step() { echo -e "\n${CYAN}=== $1 ===${NC}\n"; }

echo -e "${CYAN}"
cat << "EOF"
╔══════════════════════════════════════════════════╗
║        NeuroTrade VPS Setup Script              ║
║        Automated Server Configuration            ║
╚══════════════════════════════════════════════════╝
EOF
echo -e "${NC}"

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    log_error "Please run as root (sudo bash vps-setup.sh)"
    exit 1
fi

# Detect OS
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS=$NAME
    VER=$VERSION_ID
else
    log_error "Cannot detect OS. This script supports Ubuntu/Debian only."
    exit 1
fi

log_info "Detected OS: $OS $VER"

if [[ ! "$OS" =~ "Ubuntu" ]] && [[ ! "$OS" =~ "Debian" ]]; then
    log_error "This script only supports Ubuntu or Debian"
    exit 1
fi

# Step 1: Update system
log_step "Step 1: Updating System Packages"
apt update && apt upgrade -y
log_success "System updated"

# Step 2: Install Docker
log_step "Step 2: Installing Docker"
if command -v docker >/dev/null 2>&1; then
    log_info "Docker already installed: $(docker --version)"
else
    log_info "Installing Docker..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sh get-docker.sh
    rm get-docker.sh
    systemctl enable docker
    systemctl start docker
    log_success "Docker installed: $(docker --version)"
fi

# Step 3: Install Docker Compose
log_step "Step 3: Installing Docker Compose"
if docker compose version >/dev/null 2>&1; then
    log_info "Docker Compose already installed: $(docker compose version)"
else
    apt install -y docker-compose
    log_success "Docker Compose installed: $(docker-compose --version)"
fi

# Step 4: Install essential tools
log_step "Step 4: Installing Essential Tools"
apt install -y \
    git \
    curl \
    wget \
    vim \
    nano \
    htop \
    ufw \
    fail2ban \
    apache2-utils \
    certbot \
    postgresql-client

log_success "Essential tools installed"

# Step 5: Configure Firewall
log_step "Step 5: Configuring Firewall (UFW)"
log_warning "This will enable UFW and allow SSH, HTTP, HTTPS"
read -p "Continue? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    # Allow SSH first (critical!)
    ufw allow 22/tcp
    log_success "SSH allowed (port 22)"

    # Allow HTTP/HTTPS
    ufw allow 80/tcp
    ufw allow 443/tcp
    log_success "HTTP/HTTPS allowed (ports 80, 443)"

    # Enable UFW
    echo "y" | ufw enable
    log_success "UFW enabled"

    # Show status
    ufw status verbose
else
    log_warning "Skipped firewall configuration"
fi

# Step 6: Configure Fail2Ban
log_step "Step 6: Configuring Fail2Ban (SSH Protection)"
if systemctl is-active --quiet fail2ban; then
    log_info "Fail2Ban already running"
else
    systemctl enable fail2ban
    systemctl start fail2ban
    log_success "Fail2Ban enabled"
fi

# Step 7: Create project directory
log_step "Step 7: Creating Project Directory"
PROJECT_DIR="/opt/neurotrade"
if [ -d "$PROJECT_DIR" ]; then
    log_warning "Directory $PROJECT_DIR already exists"
else
    mkdir -p "$PROJECT_DIR"
    log_success "Created directory: $PROJECT_DIR"
fi

# Step 8: Optional - Clone repository
log_step "Step 8: Clone Repository (Optional)"
read -p "Do you want to clone the NeuroTrade repository now? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    read -p "Enter your GitHub repository URL: " REPO_URL
    if [ -n "$REPO_URL" ]; then
        cd /opt
        if [ -d "$PROJECT_DIR/.git" ]; then
            log_warning "Repository already cloned"
        else
            git clone "$REPO_URL" neurotrade
            log_success "Repository cloned to $PROJECT_DIR"
        fi
    else
        log_warning "No URL provided, skipping clone"
    fi
else
    log_info "Skipped repository clone"
    log_info "You can clone later with:"
    echo -e "${BLUE}    cd /opt && git clone <your-repo-url> neurotrade${NC}"
fi

# Step 9: Setup swap (if needed)
log_step "Step 9: Checking Swap Memory"
SWAP=$(free -m | awk '/^Swap:/ {print $2}')
if [ "$SWAP" -eq 0 ]; then
    log_warning "No swap detected. Creating 2GB swap file..."
    read -p "Create swap? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        fallocate -l 2G /swapfile
        chmod 600 /swapfile
        mkswap /swapfile
        swapon /swapfile
        echo "/swapfile none swap sw 0 0" >> /etc/fstab
        log_success "2GB swap created"
    fi
else
    log_success "Swap already configured: ${SWAP}MB"
fi

# Step 10: Setup Docker log rotation
log_step "Step 10: Configuring Docker Log Rotation"
cat > /etc/docker/daemon.json <<EOF
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
EOF
systemctl restart docker
log_success "Docker log rotation configured"

# Summary
log_step "Setup Complete!"

echo -e "${GREEN}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║          VPS Setup Completed Successfully        ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════╝${NC}\n"

echo -e "${CYAN}Installed Components:${NC}"
echo -e "  ✓ Docker: $(docker --version | cut -d' ' -f3)"
echo -e "  ✓ Docker Compose: $(docker-compose --version | cut -d' ' -f3)"
echo -e "  ✓ Git: $(git --version | cut -d' ' -f3)"
echo -e "  ✓ UFW Firewall: Enabled"
echo -e "  ✓ Fail2Ban: Enabled"

echo -e "\n${CYAN}Project Directory:${NC} $PROJECT_DIR"

echo -e "\n${YELLOW}Next Steps:${NC}"
if [ -d "$PROJECT_DIR/.git" ]; then
    echo -e "  1. Configure environment: ${BLUE}cd $PROJECT_DIR && cp .env.production.example .env${NC}"
    echo -e "  2. Edit .env file: ${BLUE}nano $PROJECT_DIR/.env${NC}"
    echo -e "  3. Deploy: ${BLUE}cd $PROJECT_DIR && ./scripts/deploy.sh${NC}"
else
    echo -e "  1. Clone repository: ${BLUE}cd /opt && git clone <your-repo-url> neurotrade${NC}"
    echo -e "  2. Configure environment: ${BLUE}cd $PROJECT_DIR && cp .env.production.example .env${NC}"
    echo -e "  3. Edit .env file: ${BLUE}nano $PROJECT_DIR/.env${NC}"
    echo -e "  4. Deploy: ${BLUE}cd $PROJECT_DIR && ./scripts/deploy.sh${NC}"
fi

echo -e "\n${YELLOW}Security Reminders:${NC}"
echo -e "  • Change default passwords"
echo -e "  • Generate new JWT secret (${BLUE}openssl rand -base64 32${NC})"
echo -e "  • Setup SSL certificate (${BLUE}./scripts/setup-ssl.sh yourdomain.com${NC})"
echo -e "  • Or enable basic auth (${BLUE}./scripts/setup-basic-auth.sh${NC})"

echo -e "\n${GREEN}VPS is ready for deployment! 🚀${NC}\n"
