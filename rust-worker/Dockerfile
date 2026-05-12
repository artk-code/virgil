# ------------------------------------------------------------------------------
# Rust worker — release build, slim Debian runtime.
# ------------------------------------------------------------------------------
FROM rust:1.86-bookworm AS builder
WORKDIR /app
COPY Cargo.toml Cargo.lock ./
COPY src ./src
RUN cargo build --release

FROM debian:bookworm-slim
RUN useradd --create-home --shell /usr/sbin/nologin app \
 && apt-get update && apt-get install -y --no-install-recommends ca-certificates \
 && rm -rf /var/lib/apt/lists/*
COPY --from=builder /app/target/release/rust-worker /usr/local/bin/rust-worker
USER app
CMD ["/usr/local/bin/rust-worker"]
