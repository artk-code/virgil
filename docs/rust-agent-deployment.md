# Rust Agent Deployment Boundary

Phase 1 splits Rust responsibilities into two roles so eBPF can run safely on
Linux hosts while the compose stack remains unprivileged.

## 1) Host security sensor (`rust-host-agent`, planned)

- Deployment target: Linux host (systemd service) or Kubernetes DaemonSet.
- Privileges: host-level capabilities needed for eBPF attach/collect.
- Data sources:
  - Primary: eBPF hooks and kernel telemetry.
  - Fallback: host logs when eBPF is unavailable or restricted.
- Output: publish normalized events to Redis stream `security_events`.
- `source_type`:
  - `ebpf` for kernel-derived telemetry
  - `logs` for fallback collectors

## 2) Container simulation producer (`rust-worker`, current repo service)

- Deployment target: Docker Compose app network.
- Privileges: unprivileged container only.
- Purpose: generate synthetic but contract-compliant events for local
  development, API integration tests, and ETL testing.
- Output: publish `source_type=simulator` events to `security_events`.

## Why this split

- eBPF generally requires host/kernel capabilities that should not be granted to
  the default application container.
- Decoupling host capture from compose app services keeps local dev simple while
  preserving a realistic downstream pipeline (Redis -> Python -> Postgres).
