# Scripts Directory

This directory contains deployment and maintenance scripts for NeuroTrade.

## 📜 Available Scripts

### 1. `vps-setup.sh`
**Purpose:** Initial VPS preparation (run once on new server)

**What it does:**
- Installs Docker & Docker Compose
- Installs essential tools (git, curl, wget, etc.)
- Configures UFW firewall
- Enables Fail2Ban for SSH protection
- Creates project directory
- Optionally clones repository
- Sets up swap memory
- Configures Docker log rotation

**Usage:**
```bash
# On fresh VPS (as root)
curl -fsSL https://raw.githubusercontent.com/your-repo/neurotrade/main/scripts/vps-setup.sh | bash

# Or download and run:
wget https://raw.githubusercontent.com/your-repo/neurotrade/main/scripts/vps-setup.sh
chmod +x vps-setup.sh
sudo bash vps-setup.sh
```

**Requirements:**
- Fresh Ubuntu 20.04+ or Debian 11+ VPS
- Root access

---

### 2. `deploy.sh`
**Purpose:** Automated deployment (run for updates)

**What it does:**
- Pulls latest code from Git
- Creates database backup (timestamped)
- Rebuilds Docker containers
- Cleans up old images
- Runs health checks
- Shows deployment summary

**Usage:**
```bash
# Standard deployment
./scripts/deploy.sh

# Skip database backup
./scripts/deploy.sh --skip-backup

# Skip Docker rebuild (just restart)
./scripts/deploy.sh --no-build

# View help
./scripts/deploy.sh --help
```

**Features:**
- ✅ Colored output (green/red/yellow)
- ✅ Automatic backup rotation (keeps last 7)
- ✅ Health checks for all services
- ✅ Rollback instructions on failure
- ✅ Safety confirmations

**Requirements:**
- Existing NeuroTrade installation
- Git repository initialized
- Docker & Docker Compose installed

---

### 3. `setup-ssl.sh`
**Purpose:** SSL certificate setup with Let's Encrypt

**What it does:**
- Installs certbot
- Obtains SSL certificate
- Copies certificates to nginx directory
- Updates nginx configuration
- Sets up auto-renewal cron job

**Usage:**
```bash
sudo ./scripts/setup-ssl.sh yourdomain.com
```

**Requirements:**
- Domain name pointing to VPS IP
- Port 80 open (for verification)
- Root access

**Notes:**
- Certificate auto-renews daily at midnight
- Valid for 90 days
- Free from Let's Encrypt

---

### 4. `setup-basic-auth.sh`
**Purpose:** Create basic authentication for nginx

**What it does:**
- Installs htpasswd tool
- Creates `.htpasswd` file
- Prompts for username/password
- Shows instructions to enable in nginx

**Usage:**
```bash
./scripts/setup-basic-auth.sh
```

**After running:**
1. Edit `nginx/conf.d/neurotrade.conf`
2. Uncomment these lines:
   ```nginx
   auth_basic "NeuroTrade Dashboard";
   auth_basic_user_file /etc/nginx/.htpasswd;
   ```
3. Restart nginx:
   ```bash
   docker-compose -f docker-compose.prod.yml restart nginx
   ```

**Requirements:**
- apache2-utils (installed automatically)

---

## 🔄 Typical Workflow

### First-Time Setup (New VPS)

```bash
# 1. Run VPS setup script (on VPS as root)
curl -fsSL https://your-repo-url/scripts/vps-setup.sh | bash

# 2. Clone repository (if not done by setup script)
cd /opt
git clone https://github.com/your-username/neurotrade.git
cd neurotrade

# 3. Configure environment
cp .env.production.example .env
nano .env  # Edit with your values

# 4. Deploy application
./scripts/deploy.sh

# 5. Setup SSL (if you have a domain)
sudo ./scripts/setup-ssl.sh yourdomain.com

# OR setup basic auth (if no domain)
./scripts/setup-basic-auth.sh
# Then uncomment auth lines in nginx/conf.d/neurotrade.conf
docker-compose -f docker-compose.prod.yml restart nginx
```

### Regular Updates

```bash
# Pull latest changes and deploy
cd /opt/neurotrade
./scripts/deploy.sh
```

---

## 🛠️ Customization

### Modifying `deploy.sh`

**Change backup retention:**
```bash
# In deploy.sh, line ~147
ls -t "$BACKUP_DIR"/neurotrade_backup_*.sql.gz | tail -n +8 | xargs -r rm --
# Change +8 to +(N+1) to keep N backups
```

**Disable health checks:**
```bash
# Comment out in main() function:
# health_check
```

**Add custom steps:**
```bash
# Add before show_summary() in main() function:
custom_step() {
    log_step "Custom Step"
    # Your commands here
}
```

### Modifying `vps-setup.sh`

**Change swap size:**
```bash
# Line ~189
fallocate -l 2G /swapfile
# Change 2G to desired size (e.g., 4G)
```

**Add additional packages:**
```bash
# Add to apt install command around line ~110
apt install -y \
    git \
    curl \
    your-package-here
```

---

## 🐛 Troubleshooting

### Script Permission Denied

```bash
chmod +x scripts/*.sh
```

### Docker Permission Denied

```bash
# Add user to docker group
sudo usermod -aG docker $USER
# Logout and login again
```

### SSL Certificate Failed

```bash
# Check domain DNS
nslookup yourdomain.com

# Check port 80 open
sudo ufw allow 80/tcp

# Check nginx stopped
docker-compose -f docker-compose.prod.yml stop nginx
```

### Backup Failed

```bash
# Check PostgreSQL running
docker ps | grep postgres

# Check disk space
df -h

# Manual backup
docker exec neurotrade_postgres_prod pg_dump -U neurotrade -d neurotrade_db > manual_backup.sql
```

---

## 📝 Notes

- All scripts use color-coded output for clarity
- Errors are non-fatal where possible (with warnings)
- Backups are timestamped and compressed
- Health checks run after deployment
- Scripts are idempotent (safe to re-run)

---

**For full deployment guide, see:** [../DEPLOYMENT.md](../DEPLOYMENT.md)
