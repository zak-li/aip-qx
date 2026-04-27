# Database migrations (Alembic)

Schema migrations for the RWA platform Postgres database.

## Setup

```bash
pip install -r requirements.txt
```

## Generating the initial revision

The repo currently has hand-written `database/sql/0[1-7]_*.sql` seeds but no
Alembic baseline. To bootstrap:

1. Apply the SQL seeds against an empty database (so the schema matches the
   ORM models in `backend/features/*/models.py`).
2. Stamp the database as if it were already at the head of an empty Alembic
   tree:

   ```bash
   alembic stamp head
   ```

3. Generate the first real migration on top of any future model change:

   ```bash
   alembic revision --autogenerate -m "describe change"
   alembic upgrade head
   ```

## Configuration

Connection details come from `backend.config.settings.database_url` (env var
`DATABASE_URL`). `alembic.ini` does **not** contain credentials.

## Models registered for autogenerate

`env.py` imports the model modules below — adding a new feature with its own
models means adding the import there too:

- `backend.features.assets.models`
- `backend.features.auth.models`
- `backend.features.compliance.models`
- `backend.features.transactions.models`
- `backend.features.tribunal.models`
- `backend.features.zkp.models`
