# CTM quality gate

From a clean checkout, install dependencies and run every mandatory P0 check with:

```bash
python verify.py --install
```

The command creates only temporary test databases and does not connect to a
production or shared database. It runs Python syntax compilation, the backend
`pytest` contracts, Vue type checking and production build, and the Playwright
smoke/layout suite. Later runs can use `python verify.py`; backend-only iteration
can use `python verify.py --skip-e2e`.

The gate also validates the complete trade scenario catalog and runs its 27
implemented CTM cases through pytest. Full trade readiness is a separate gate:
`python runner/trade_harness/suite.py run`. It currently fails explicitly for
123 scenarios without executors. `--implemented-only` verifies the implemented
subset while preserving incomplete coverage in the report. See
`TRADE_ACCOUNTING_SUITE.md` for scope and reference audit commands.

Production deployment additionally requires `CTM_ENV=production`, a unique
`JWT_SECRET_KEY` of at least 32 characters, a unique `SYNC_TOKEN` of at least 24
characters, and `ALLOW_SEED_DATA=false`. The API refuses to start when these
conditions are not met.
