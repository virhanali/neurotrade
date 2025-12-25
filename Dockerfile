# Build stage
FROM golang:1.23-alpine AS builder

WORKDIR /app

# Install build dependencies
RUN apk add --no-cache git ca-certificates tzdata

# Copy go mod files first (layer caching)
COPY go.mod go.sum* ./
RUN go mod download && go mod verify

# Copy source code
COPY . .

# Build the application with optimizations
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build \
    -a -installsuffix cgo \
    -ldflags="-w -s -X main.BuildTime=$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    -o main ./cmd/app

# Production stage
FROM alpine:3.19 AS production

WORKDIR /app

# Install runtime dependencies
RUN apk --no-cache add ca-certificates tzdata curl wget && \
    addgroup -g 1000 appuser && \
    adduser -D -u 1000 -G appuser appuser

# Copy binary and assets from builder
COPY --from=builder /app/main .
COPY --from=builder /app/configs ./configs
COPY --from=builder /app/web ./web

# Create logs directory
RUN mkdir -p /app/logs && \
    chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8080

# Run the application
CMD ["./main"]
