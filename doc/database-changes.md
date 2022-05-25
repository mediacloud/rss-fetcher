Changing the Database
=====================

This uses [alembic](https://alembic.sqlalchemy.org/en/latest/index.html) for managing database schema revisions in
code. This is handled via migrations, each of which makes one or more changes to the schema.

### Creating a Migration

1. `alembic revision -m "create new table"`
2. Open the file it says it generated (in `fetcher/database/versions/`) and fill in the `upgrade` and `downgrade`
   methods. See their [operations reference](https://alembic.sqlalchemy.org/en/latest/ops.html#ops) for examples of 
   table, column, and index operations.

### Running Migrations

Run `alembic upgrade head` to bring you database up to date by running all the migrations it hasn't run yet.
