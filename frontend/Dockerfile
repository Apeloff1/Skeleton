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
RUN yarn install --frozen-lockfile --non-interactive

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
FROM nginx:alpine@sha256:72ba65eb42c10344912a84ff42408db7d34f2feb642204570ab8fc5ffd29f1d3 AS production
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://127.0.0.1/healthz >/dev/null || exit 1

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
