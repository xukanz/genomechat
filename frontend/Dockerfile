# Frontend Dockerfile
# Multi-stage build for React application with Nginx

# Stage 1: Build React application
FROM node:18-alpine AS builder

WORKDIR /app

# Build argument for API URL (configurable at build time)
ARG VITE_API_URL=http://localhost:8000

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm ci --production=false

# Copy source code
COPY . .

# Build production bundle with API URL
ENV VITE_API_URL=${VITE_API_URL}
RUN npm run build

# Stage 2: Production server with Nginx
FROM nginx:alpine

# Install Node.js for config injection script (lightweight, only needed at runtime)
RUN apk add --no-cache nodejs

# Copy custom nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy built files from builder stage
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy config injection script
COPY inject-config.js /usr/local/bin/inject-config.js
RUN chmod +x /usr/local/bin/inject-config.js

# Create entrypoint script
# Note: Don't use 'set -e' to ensure nginx starts even if injection script fails
RUN echo '#!/bin/sh' > /docker-entrypoint.sh && \
    echo '# Run config injection (non-blocking - nginx will start even if this fails)' >> /docker-entrypoint.sh && \
    echo '/usr/local/bin/inject-config.js || true' >> /docker-entrypoint.sh && \
    echo '# Start nginx' >> /docker-entrypoint.sh && \
    echo 'exec nginx -g "daemon off;"' >> /docker-entrypoint.sh && \
    chmod +x /docker-entrypoint.sh

# Expose port
EXPOSE 80

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
  CMD wget --quiet --tries=1 --spider http://localhost/health || exit 1

# Use custom entrypoint
ENTRYPOINT ["/docker-entrypoint.sh"]
