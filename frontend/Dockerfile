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
# Yarn resolves the reviewed file:vendor/deepmerge override during dependency installation.
COPY vendor/deepmerge/ ./vendor/deepmerge/
COPY index.js ./index.js
COPY scripts/patch-node-modules.js ./scripts/patch-node-modules.js
COPY scripts/verify-no-release-npm-security.js scripts/verify-deepmerge-security.cjs ./scripts/
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export SSL_CERT_FILE=/run/secrets/proxy_ca PIP_CERT=/run/secrets/proxy_ca NODE_EXTRA_CA_CERTS=/run/secrets/proxy_ca; fi; \
    yarn install --frozen-lockfile --non-interactive --ignore-scripts --network-concurrency 4 --network-timeout 120000 \
    && node ./scripts/patch-node-modules.js \
    && node ./scripts/verify-no-release-npm-security.js \
    && yarn cache clean

# Stage 2: Development
FROM deps AS development
COPY . .
EXPOSE 3000 8081 19000 19001 19002
CMD ["npx", "expo", "start", "--web", "--port", "3000"]

# Stage 3: Web Build
FROM deps AS builder
# Ensure deterministic, noninteractive guarded Expo export in CI and image builds.
ENV CI=1 \
    EXPO_NO_TELEMETRY=1
# Expo inlines public endpoints into the exported browser bundle. These are
# public URLs only; model credentials remain confined to the engine.
# Leave production web endpoints unset by default: the browser must use the
# installed application's same-origin nginx ingress, not the visitor's localhost.
# Explicit build arguments remain supported for deliberately external deployments.
ARG EXPO_PUBLIC_BACKEND_URL=
ARG EXPO_PUBLIC_SKELETON_URL=
ENV EXPO_PUBLIC_BACKEND_URL=$EXPO_PUBLIC_BACKEND_URL \
    EXPO_PUBLIC_SKELETON_URL=$EXPO_PUBLIC_SKELETON_URL
COPY . .
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export SSL_CERT_FILE=/run/secrets/proxy_ca PIP_CERT=/run/secrets/proxy_ca NODE_EXTRA_CA_CERTS=/run/secrets/proxy_ca; fi; \
    node --test scripts/test-guarded-expo-export.cjs \
    && node scripts/guarded-expo-export.cjs \
    && echo "frontend-export-supervision-complete" \
    && test -s /app/dist/index.html \
    && (test -s /app/dist/setup.html || test -s /app/dist/setup/index.html) \
    && echo "frontend-index-and-setup-artifacts-verified"

# Stage 4: Production (Nginx)
# Use the minimal official nginx runtime to reduce the production package/CVE
# surface. Keep the multi-platform index immutable for reproducible rebuilds.
FROM nginx:1.31-alpine-slim@sha256:9c68ad4f28e7dee4b9484a7859bf451da39ef661bcd038ef62e87593fcd91c86 AS production

# The official image starts as root so it can prepare runtime directories.
# Grant the nginx user access to the real /run directory used for nginx.pid,
# then permanently drop privileges for the production process.
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export SSL_CERT_FILE=/run/secrets/proxy_ca PIP_CERT=/run/secrets/proxy_ca NODE_EXTRA_CA_CERTS=/run/secrets/proxy_ca; fi; \
    apk add --no-cache --upgrade "pcre2=10.49-r0" \
    && chown nginx:nginx /run \
    && chown -R nginx:nginx /var/cache/nginx /etc/nginx/conf.d /usr/share/nginx/html
ARG APP_VERSION=dev
ARG VCS_REF=unknown
LABEL org.opencontainers.image.version=$APP_VERSION \
      org.opencontainers.image.revision=$VCS_REF \
      org.opencontainers.image.source=https://github.com/Apeloff1/Skeleton \
      org.opencontainers.image.title=skeleton-frontend
COPY --chown=nginx:nginx nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder --chown=nginx:nginx /app/dist /usr/share/nginx/html

USER nginx

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -Y off -qO- http://127.0.0.1:8080/healthz >/dev/null || exit 1

EXPOSE 8080
CMD ["nginx", "-g", "daemon off;"]
