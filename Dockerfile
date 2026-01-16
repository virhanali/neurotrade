# syntax=docker/dockerfile:1

# Stage 1: Build Frontend
FROM node:20-alpine AS frontend-builder
WORKDIR /app

# Install dependencies with cache
COPY neurotrade/package*.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci --legacy-peer-deps || npm install --legacy-peer-deps

# Build source
COPY neurotrade ./
RUN npm run build

# Stage 2: Build Backend
FROM golang:1.23-alpine AS builder

WORKDIR /app

# Install build dependencies
RUN apk add --no-cache git ca-certificates tzdata

# Copy go mod files first (layer caching)
COPY go.mod go.sum* ./

# Download modules with cache
RUN --mount=type=cache,target=/go/pkg/mod \
    go mod download && go mod verify

# Copy source code
COPY . .

# Build the application with optimizations and cache
RUN --mount=type=cache,target=/go/pkg/mod \
    --mount=type=cache,target=/root/.cache/go-build \
    CGO_ENABLED=0 GOOS=linux go build \
    -a -installsuffix cgo \
    -ldflags="-w -s -X main.BuildTime=$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    -o main ./cmd/app

# Stage 3: Production Image
FROM alpine:3.19 AS production

WORKDIR /app

# Install runtime dependencies
RUN apk --no-cache add ca-certificates tzdata curl wget && \
    addgroup -g 1000 appuser && \
    adduser -D -u 1000 -G appuser appuser

# Copy binary and assets from builder
COPY --from=builder /app/main .
COPY --from=builder /app/configs ./configs
# Copy frontend build from frontend-builder
COPY --from=frontend-builder /app/dist ./web/dist

# Create logs directory
RUN mkdir -p /app/logs && \
    chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8080

# Run the application
CMD ["./main"]
