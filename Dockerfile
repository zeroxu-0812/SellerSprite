FROM node:20-bookworm-slim AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM rust:1-bookworm AS backend-builder
WORKDIR /app
COPY backend/Cargo.toml backend/Cargo.lock ./backend/
RUN mkdir -p backend/src && echo 'fn main() {}' > backend/src/main.rs && cargo build --release --manifest-path backend/Cargo.toml
COPY backend/ ./backend/
RUN cargo build --release --manifest-path backend/Cargo.toml

FROM debian:bookworm-slim AS runtime
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates python3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
RUN useradd --create-home --shell /usr/sbin/nologin appuser

COPY --from=backend-builder /app/backend/target/release/sellersprite-backend /app/sellersprite-backend
COPY --from=frontend-builder /app/frontend/dist /app/frontend/dist
COPY config.json refresh_tokens.py sellersprite_signing.py ./

RUN mkdir -p /app/output \
    && chown -R appuser:appuser /app

USER appuser
ENV SELLERSPRITE_BIND=0.0.0.0:8787
EXPOSE 8787
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8787/api/health', timeout=3).read()"

CMD ["/app/sellersprite-backend"]
