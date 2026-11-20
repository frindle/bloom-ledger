# Changelog

## Unreleased (share-ready)

- First-run `/setup`, `/login`, `/status`; login required for changes by default.
- `doctor` for the server and each Mac, with a fix for every failure.
- Docker compose with a named volume, healthcheck, non-root, amd64 and arm64.
- Mac-hosted server via launchd (`deploy/mac`), guided client installer with uninstall.
- Personal defaults removed: time zone, start dates and in-service date are settings; existing installs are migrated automatically and keep their values.
- Pairing accepts hostnames, Tailscale addresses and https.
- Export API is off by default (`BLOOM_ENABLE_EXPORT_API`); existing installs keep it.
- Refreshed light and dark UI that works on phones.
- BloomGauge is an optional integration, off by default.
- End-to-end smoke test and CI.
