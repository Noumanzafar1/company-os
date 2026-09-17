# Policy history

The immutable policy definitions live in `../migrations/versions/0001_foundation.sql` and are applied only by Alembic. Changes require a new migration, never a second SQL deployment path. `company_auth` is a NOLOGIN, NOBYPASSRLS function role with narrowly granted identity access. It is not a runtime credential or table owner.
