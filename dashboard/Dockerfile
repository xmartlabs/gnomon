# syntax=docker/dockerfile:1
FROM node:22-bookworm-slim AS builder
WORKDIR /app
# better-sqlite3 compiles a native addon; the toolchain stays in the builder.
RUN apt-get update && apt-get install -y --no-install-recommends python3 make g++ \
    && rm -rf /var/lib/apt/lists/*
RUN corepack enable
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY . .
# `pnpm build` passes --webpack: Next 16 defaults to Turbopack, which emits no
# .next/standalone at all (see next.config.ts).
RUN pnpm build

FROM node:22-bookworm-slim AS runner
WORKDIR /app
ENV NODE_ENV=production DATA_DIR=/data PORT=3000 HOSTNAME=0.0.0.0
# The standalone bundle carries its own node_modules but NOT the static assets.
# They must be in place before the server boots — it reads the static manifest
# once at startup, and a later copy leaves every client chunk 404ing, which
# looks like a working page whose buttons silently do nothing.
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/scripts/docker-entrypoint.sh ./docker-entrypoint.sh
RUN mkdir -p /data && chown node:node /data
USER node
VOLUME /data
EXPOSE 3000
# TEAM_TOKEN is enforced at container start by the entrypoint, NOT at build
# time — the builder has no runtime secrets.
ENTRYPOINT ["./docker-entrypoint.sh"]
