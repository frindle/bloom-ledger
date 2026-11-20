# Contributing

- Python standard library only on the server and client. No build step, no JS framework.
- Run the tests in a throwaway environment (not on a Mac that is running Darkbloom): `PYTHONPATH=lib python -m pytest ingest -q`.
- The end-to-end smoke test needs Playwright and Chromium: `pip install pytest playwright && playwright install chromium`. Set `SHOTS_DIR=dir` to save screenshots.
- Keep the core working with Darkbloom alone. Integrations (BloomGauge) stay optional and off by default.
- Never commit real addresses, names, tokens or earnings. Tests use fake data.
- Shell scripts must pass `sh -n` and shellcheck. Do not run the Mac install scripts on a machine you care about while testing changes.
- Write plain-language commit messages.
