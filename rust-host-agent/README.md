# rust-host-agent (planned VIRGIL endpoint deployment)

This package is the boundary artifact for the VIRGIL endpoint sensor role.

- Initial deployment: Linux host-level service (systemd) or privileged DaemonSet.
- Responsibilities:
  - eBPF-first telemetry collection on Linux hosts.
  - fallback collectors from host logs if eBPF is unavailable.
  - publish normalized events to Redis stream `security_events`.

The compose `rust-worker` remains an unprivileged simulator producer for local
development.
