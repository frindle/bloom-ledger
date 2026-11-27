# Changelog

## Unreleased (share-ready)

- First-run `/setup`, `/login`, `/status`; login required for changes by default.
- `doctor` for the server and each Mac, with a fix for every failure.
- Docker compose with a named volume, healthcheck, non-root, amd64 and arm64.
- Mac-hosted server via launchd (`deploy/mac`), guided client installer with uninstall.
- Days, months, periods, "today", the earnings chart and invoice months are now UTC, matching Darkbloom. The time zone setting only applies time-of-use electricity prices. Earnings and power are stored by timestamp and re-cut on the fly, so figures near day edges move by up to the old zone's UTC offset. Nothing stored is rewritten: settings rows (`since`), manual entries and `daily-push.json` keep the calendar day they were saved with, so one made near local midnight can sit a day off the UTC data, and the push on the day of the switch can repeat or skip one day.
- `/v1/status`: `timezone` is now the accounting-day zone (always `UTC`); the zone chosen at setup is in the new `rate_timezone`.
- `DAILY_PUSH_HOUR` is now an hour of the UTC day (it used to be local time), and the push reports the previous UTC day. Set it again if you relied on a local hour.
- Personal defaults removed: time zone, start dates and in-service date are settings; existing installs are migrated automatically and keep their values.
- Pairing accepts hostnames, Tailscale addresses and https.
- Export API is off by default (`BLOOM_ENABLE_EXPORT_API`); existing installs keep it.
- Refreshed light and dark UI that works on phones.
- BloomGauge is an optional integration, off by default.
- End-to-end smoke test and CI.
