# rust-host-agent (planned host deployment)

This package is the Phase 1 boundary artifact for the Linux host sensor role.

- Intended deployment: host-level service (systemd) or privileged DaemonSet.
- Responsibilities:
  - eBPF-first telemetry collection on Linux hosts.
  - fallback collectors from host logs if eBPF is unavailable.
  - publish normalized events to Redis stream `security_events`.

The compose `rust-worker` remains an unprivileged simulator producer for local
development.
