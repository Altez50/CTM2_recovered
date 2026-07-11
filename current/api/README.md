# CTM API

FastAPI backend for the CTM browser client.

## Features

- JWT authentication with 8-hour access tokens
- SQLite bootstrap and demo seed data
- CRUD endpoints for counterparties, objects, works, persons, and organizations
- Estimate and daily report document workflows
- Document posting and unposting into the work execution register
- Print exports in PDF and Excel-compatible XML formats
- Dashboard summary and health endpoints

## Run

```bash
python -m uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

When `construction.db` does not exist yet, the app creates it automatically and seeds demo accounts:

- `admin / admin`
- `manager / manager`
- `foreman / foreman`
