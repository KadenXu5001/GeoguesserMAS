# syntax=docker/dockerfile:1

# ---- Frontend build: compiles the Vite app, keeps devDependencies out of later stages ----
FROM node:22-bookworm-slim AS web-build
WORKDIR /app/web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# ---- Production Node dependencies only (no devDependencies) ----
FROM node:22-bookworm-slim AS web-prod-deps
WORKDIR /app/web
COPY web/package.json web/package-lock.json ./
RUN npm ci --omit=dev

# ---- Runtime ----
FROM node:22-bookworm-slim AS runtime
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-venv \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system app \
    && useradd --system --gid app --home /app --shell /usr/sbin/nologin app

WORKDIR /app

COPY requirements.txt ./
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY scripts/ ./scripts/
COPY data/ ./data/
COPY main.py ./
COPY web/server.js web/package.json ./web/
COPY --from=web-prod-deps /app/web/node_modules ./web/node_modules
COPY --from=web-build /app/web/dist ./web/dist

ENV PYTHON=/opt/venv/bin/python \
    PYTHONUNBUFFERED=1 \
    NODE_ENV=production \
    PORT=3000

RUN chown -R app:app /app
USER app

EXPOSE 3000
CMD ["node", "web/server.js"]
