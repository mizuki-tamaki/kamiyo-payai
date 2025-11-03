# Database Migrations

This directory contains Alembic migrations for the x402 Payment Gateway database schema.

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Configure database URL in `.env`:
```bash
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/kamiyo
```

## Common Commands

### Apply migrations (upgrade to latest)
```bash
alembic upgrade head
```

### Revert last migration
```bash
alembic downgrade -1
```

### Create new migration (auto-generate)
```bash
alembic revision --autogenerate -m "description of changes"
```

### Create new migration (manual)
```bash
alembic revision -m "description of changes"
```

### Show current revision
```bash
alembic current
```

### Show migration history
```bash
alembic history
```

### Show SQL without applying
```bash
alembic upgrade head --sql
```

## Migration Files

- `001_initial_x402_tables.py` - Initial schema for x402 payments, tokens, usage, and analytics

## Best Practices

1. Always review auto-generated migrations before applying
2. Test migrations on a development database first
3. Never edit applied migrations - create new ones instead
4. Include both upgrade() and downgrade() functions
5. Use descriptive migration messages

## Production Deployment

```bash
# 1. Backup database
pg_dump kamiyo > backup_$(date +%Y%m%d_%H%M%S).sql

# 2. Apply migrations
alembic upgrade head

# 3. Verify
alembic current
```

## Troubleshooting

### "Can't locate revision identified by 'xxx'"
The database alembic_version table might be out of sync. Check current version:
```bash
psql kamiyo -c "SELECT * FROM alembic_version;"
```

### Reset to clean state (development only!)
```bash
alembic downgrade base
alembic upgrade head
```

### Force set version (use with caution!)
```bash
alembic stamp head
```
