# ============================================================================
# Tutolage Frontend Dockerfile (Expo)
# ============================================================================

# Stage 1: Dependencies
FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json yarn.lock* ./
RUN yarn install --frozen-lockfile || yarn install

# Stage 2: Development
FROM node:20-alpine AS development
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
EXPOSE 3000 8081 19000 19001 19002
CMD ["npx", "expo", "start", "--web", "--port", "3000"]

# Stage 3: Web Build
FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npx expo export --platform web || true

# Stage 4: Production (Nginx)
FROM nginx:alpine AS production
COPY --from=builder /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
