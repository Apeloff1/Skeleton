# ============================================================================
# Tutolage Frontend Dockerfile (Expo)
# ============================================================================

ARG NODE_VERSION=24

# Pin official multi-platform image indexes so rebuilds cannot silently drift.
# Refresh these digests deliberately alongside dependency/security review.
# Stage 1: Dependencies
FROM node:${NODE_VERSION}-alpine@sha256:50c8e8ca1d27439048670df5883f32d57cf81cff6233222c893fd0d9884cbd81 AS deps
WORKDIR /app
COPY package.json yarn.lock* ./
COPY index.js ./index.js
COPY scripts/patch-node-modules.js ./scripts/patch-node-modules.js
RUN yarn install --frozen-lockfile --non-interactive --ignore-scripts \
    && node ./scripts/patch-node-modules.js

# Stage 2: Development
FROM node:${NODE_VERSION}-alpine@sha256:50c8e8ca1d27439048670df5883f32d57cf81cff6233222c893fd0d9884cbd81 AS development
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
EXPOSE 3000 8081 19000 19001 19002
CMD ["npx", "expo", "start", "--web", "--port", "3000"]

# Stage 3: Web Build
FROM node:${NODE_VERSION}-alpine@sha256:50c8e8ca1d27439048670df5883f32d57cf81cff6233222c893fd0d9884cbd81 AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN yarn export:web

# Stage 4: Production (Nginx)
# Use the minimal official nginx runtime to reduce the production package/CVE
# surface. Keep the multi-platform index immutable for reproducible rebuilds.
FROM nginx:1.31-alpine-slim@sha256:17d54e4e48ae6b564266ffd4a688b1bced79e57e59a7f08929e0059672ed3501 AS production

# The official image starts as root so it can prepare runtime directories.
# Grant the nginx user access to the real /run directory used for nginx.pid,
# then permanently drop privileges for the production process.
RUN chown nginx:nginx /run \
    && chown -R nginx:nginx /var/cache/nginx /etc/nginx/conf.d /usr/share/nginx/html
COPY --chown=nginx:nginx nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder --chown=nginx:nginx /app/dist /usr/share/nginx/html

USER nginx

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://127.0.0.1:8080/healthz >/dev/null || exit 1

EXPOSE 8080
CMD ["nginx", "-g", "daemon off;"]