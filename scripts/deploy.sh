#!/bin/bash

################################################################################
# NeuroTrade Production Deployment Script
# Description: Automated deployment with safety checks and rollback capability
# Usage: ./scripts/deploy.sh [--skip-backup] [--no-build]
################################################################################

set -e  # Exit on error

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Configuration
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="$PROJECT_DIR/backups"
COMPOSE_FILE="docker-compose.prod.yml"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
SKIP_BACKUP=false
NO_BUILD=false

# Parse command line arguments
for arg in "$@"; do
  case $arg in
    --skip-backup)
      SKIP_BACKUP=true
      shift
      ;;
    --no-build)
      NO_BUILD=true
      shift
      ;;
    --help)
      echo "Usage: $0 [OPTIONS]"
      echo ""
      echo "Options:"
      echo "  --skip-backup    Skip database backup"
      echo "  --no-build       Skip Docker image rebuild"
      echo "  --help           Show this help message"
      exit 0
      ;;
  esac
done

################################################################################
# Helper Functions
################################################################################

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_step() {
    echo -e "\n${CYAN}===================================================${NC}"
    echo -e "${CYAN}$1${NC}"
    echo -e "${CYAN}===================================================${NC}\n"
}

# Check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check prerequisites
check_prerequisites() {
    log_step "Checking Prerequisites"

    if ! command_exists docker; then
        log_error "Docker is not installed. Please install Docker first."
        exit 1
    fi

    if ! command_exists docker-compose && ! docker compose version >/dev/null 2>&1; then
        log_error "Docker Compose is not installed. Please install Docker Compose first."
        exit 1
    fi

    # Check if .env file exists
    if [ ! -f "$PROJECT_DIR/.env" ]; then
        log_error ".env file not found. Please create it from .env.example"
        exit 1
    fi

    log_success "All prerequisites met"
}

# Check if running with necessary permissions
check_permissions() {
    if [ ! -w "$PROJECT_DIR" ]; then
        log_error "No write permission in project directory: $PROJECT_DIR"
        log_info "Try running with sudo or fix directory permissions"
        exit 1
    fi
}

################################################################################
# Main Deployment Steps
################################################################################

# Step 1: Git Pull
pull_latest_code() {
    log_step "Step 1: Pulling Latest Code from Git"

    cd "$PROJECT_DIR"

    # Check if it's a git repository
    if [ ! -d ".git" ]; then
        log_warning "Not a git repository. Skipping git pull."
        return
    fi

    # Check for uncommitted changes
    if ! git diff-index --quiet HEAD --; then
        log_warning "You have uncommitted changes:"
        git status --short
        read -p "Continue anyway? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_error "Deployment aborted by user"
            exit 1
        fi
    fi

    # Store current commit for rollback
    CURRENT_COMMIT=$(git rev-parse HEAD)
    log_info "Current commit: $CURRENT_COMMIT"

    # Pull latest changes
    log_info "Pulling from origin/main..."
    if git pull origin main; then
        NEW_COMMIT=$(git rev-parse HEAD)
        log_success "Code updated successfully"
        log_info "New commit: $NEW_COMMIT"

        if [ "$CURRENT_COMMIT" == "$NEW_COMMIT" ]; then
            log_info "Already up to date (no new commits)"
        fi
    else
        log_error "Git pull failed"
        exit 1
    fi
}

# Step 2: Backup Database
backup_database() {
    if [ "$SKIP_BACKUP" = true ]; then
        log_warning "Skipping database backup (--skip-backup flag)"
        return
    fi

    log_step "Step 2: Backing Up Database"

    # Create backup directory
    mkdir -p "$BACKUP_DIR"

    # Check if postgres container is running
    if ! docker ps | grep -q "neurotrade_postgres_prod"; then
        log_warning "PostgreSQL container not running. Skipping backup."
        return
    fi

    # Backup filename
    BACKUP_FILE="$BACKUP_DIR/neurotrade_backup_$TIMESTAMP.sql"

    log_info "Creating database backup: $BACKUP_FILE"

    # Get database credentials from .env
    source "$PROJECT_DIR/.env"
    POSTGRES_USER=${POSTGRES_USER:-neurotrade}
    POSTGRES_DB=${POSTGRES_DB:-neurotrade_db}

    # Create backup (signals table + users for safety)
    if docker exec neurotrade_postgres_prod pg_dump \
        -U "$POSTGRES_USER" \
        -d "$POSTGRES_DB" \
        --table=signals \
        --table=users \
        --table=paper_positions \
        --table=strategy_presets \
        --clean --if-exists \
        > "$BACKUP_FILE"; then

        log_success "Database backup created: $(basename $BACKUP_FILE)"

        # Compress backup
        gzip "$BACKUP_FILE"
        log_success "Backup compressed: $(basename $BACKUP_FILE).gz"

        # Keep only last 7 backups
        log_info "Cleaning old backups (keeping last 7)..."
        ls -t "$BACKUP_DIR"/neurotrade_backup_*.sql.gz 2>/dev/null | tail -n +8 | xargs -r rm --
        log_success "Old backups cleaned"
    else
        log_error "Database backup failed"
        read -p "Continue deployment without backup? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_error "Deployment aborted"
            exit 1
        fi
    fi
}

# Step 3: Docker Rebuild
rebuild_containers() {
    log_step "Step 3: Rebuilding Docker Containers"

    cd "$PROJECT_DIR"

    if [ "$NO_BUILD" = true ]; then
        log_warning "Skipping Docker rebuild (--no-build flag)"
        log_info "Restarting containers without rebuild..."
        docker-compose -f "$COMPOSE_FILE" up -d
    else
        log_info "Stopping running containers..."
        docker-compose -f "$COMPOSE_FILE" down

        log_info "Building and starting containers..."
        if docker-compose -f "$COMPOSE_FILE" up -d --build; then
            log_success "Containers rebuilt and started successfully"
        else
            log_error "Docker build failed"
            log_error "Attempting to restore previous state..."
            docker-compose -f "$COMPOSE_FILE" up -d
            exit 1
        fi
    fi
}

# Step 4: Prune Unused Resources
cleanup_docker() {
    log_step "Step 4: Cleaning Up Docker Resources"

    log_info "Pruning unused Docker images..."
    if docker image prune -f; then
        log_success "Unused images removed"
    else
        log_warning "Image pruning failed (non-critical)"
    fi

    log_info "Pruning dangling volumes..."
    if docker volume prune -f; then
        log_success "Dangling volumes removed"
    else
        log_warning "Volume pruning failed (non-critical)"
    fi

    # Show disk usage
    log_info "Current Docker disk usage:"
    docker system df
}

# Step 5: Health Check
health_check() {
    log_step "Step 5: Running Health Checks"

    log_info "Waiting for services to start (30 seconds)..."
    sleep 30

    log_info "Container status:"
    docker-compose -f "$COMPOSE_FILE" ps

    echo ""
    log_info "Checking service health..."

    # Check PostgreSQL
    if docker exec neurotrade_postgres_prod pg_isready -U neurotrade >/dev/null 2>&1; then
        log_success "✓ PostgreSQL is healthy"
    else
        log_error "✗ PostgreSQL is not responding"
    fi

    # Check Redis
    if docker exec neurotrade_redis_prod redis-cli ping | grep -q PONG; then
        log_success "✓ Redis is healthy"
    else
        log_error "✗ Redis is not responding"
    fi

    # Check Go App
    if curl -sf http://localhost:8080/api/admin/system/health >/dev/null 2>&1; then
        log_success "✓ Go Application is healthy"
    else
        log_warning "✗ Go Application health check failed (might still be starting)"
    fi

    # Check Python Engine
    if curl -sf http://localhost:8000/health >/dev/null 2>&1; then
        log_success "✓ Python Engine is healthy"
    else
        log_warning "✗ Python Engine health check failed (might still be starting)"
    fi

    echo ""
    log_info "Recent application logs:"
    docker logs --tail 20 neurotrade_go_app_prod
}

# Show deployment summary
show_summary() {
    log_step "Deployment Summary"

    echo -e "${GREEN}╔══════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║          Deployment Completed Successfully       ║${NC}"
    echo -e "${GREEN}╚══════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${CYAN}Timestamp:${NC} $TIMESTAMP"
    echo -e "${CYAN}Project Directory:${NC} $PROJECT_DIR"

    if [ -n "$NEW_COMMIT" ]; then
        echo -e "${CYAN}Git Commit:${NC} $NEW_COMMIT"
    fi

    if [ -f "$BACKUP_FILE.gz" ]; then
        echo -e "${CYAN}Backup:${NC} $(basename $BACKUP_FILE).gz"
    fi

    echo ""
    echo -e "${YELLOW}Next Steps:${NC}"
    echo -e "  1. Verify dashboard: ${BLUE}http://your-vps-ip${NC}"
    echo -e "  2. Check logs: ${BLUE}docker logs -f neurotrade_go_app_prod${NC}"
    echo -e "  3. Monitor Telegram for signals"
    echo ""
    echo -e "${YELLOW}Useful Commands:${NC}"
    echo -e "  • View logs: ${BLUE}docker-compose -f $COMPOSE_FILE logs -f${NC}"
    echo -e "  • Restart app: ${BLUE}docker-compose -f $COMPOSE_FILE restart go-app${NC}"
    echo -e "  • Stop all: ${BLUE}docker-compose -f $COMPOSE_FILE down${NC}"
    echo ""
}

################################################################################
# Main Execution
################################################################################

main() {
    log_step "NeuroTrade Production Deployment"
    log_info "Started at: $(date)"

    check_prerequisites
    check_permissions
    pull_latest_code
    backup_database
    rebuild_containers
    cleanup_docker
    health_check
    show_summary

    log_success "Deployment script completed successfully! 🚀"
}

# Run main function
main "$@"
