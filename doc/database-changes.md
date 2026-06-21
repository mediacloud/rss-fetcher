Changing the Database
=====================

This uses [alembic](https://alembic.sqlalchemy.org/en/latest/index.html) for managing database schema revisions in
code. This is handled via migrations, each of which makes one or more changes to the schema.

### Creating a Migration

1. Modify `fetcher/database/models.py`; add or remove tables, columns and indices
2. Make sure `DATABASE_URL` is set (if have a Dokku instance; you can run `export DATABASE_URL=$(./dokku-scripts/dburl.sh $(whoami)-rss-fetcher)`)
3. Run `venv/bin/alembic revision --autogenerate -m 'DESCRIPTION HERE'` (*)
4. Inspect the new migration file; edit it IF NECESSARY (**)
5. Test running the migration to see if it works in forward and reverse (see section below)
6. `git add` the new migration file and commit it along with changes that use changed models

[Phil: This is my preferred way: treat models.py as ground truth, and
to have alembic autogenerate migrations by looking at the database and
the models.py file. Your mileage may vary, and you might prefer hand
generating empty migrations.  I find backing out migrations tedious,
but avoids the requirement to manually keep models.py and the
migration file in sync].

(*) You can ignore messages like:
```
INFO  [alembic.ddl.postgresql] Detected sequence named 'TABLE_id_seq' as owned by integer column 'TABLE(id)', assuming SERIAL and omitting
```

(**) The migration file will be named `database/versions/YYYYMMDD_HHMM_DESCRIPTION_HERE`

NOTE!  The migration files effect the state of the database, while
(once you've run autogenerate) the `models.py` file effects ONLY how
SQLAlchemy sees the database.  THEY CAN GET OUT OF SYNC (ie; if you
decide to change things and edit only the migration), so one way to
keep things consistent/sane is to tweak only `models.py` (when
possible), reverse the old migration and remove the file, and
autogenerate a new migration file!  This is harder when you need to
manually add migration instructions (to populate new fields from old
ones).

### Testing Migrations

Migrations should be tested in forward and reverse before submitting a
Pull Request!

Staging and Production databases are updated by running alembic on app startup in a Docker
container and
[In Space, No One Can Hear You Scream](https://www.imdb.com/title/tt0078748/)!

To test migrations:

* test upgrade: `venv/bin/alembic upgrade head` to bring your database up to date.
* test downgrade: `venv/bin/alembic downgrade OLD` (*)
* Repeat as needed.

If you need to change the models file, and regenerate a migration, or
are about to change a migration you have already run, downgrade FIRST,
to get back to known/clean state.

(*) where DOWN_REVISION appears in the output from the upgrade message
```
Running upgrade PLUGH -> XYZZY: DESCRIPTION HERE
```
It also appears as `down_revision = 'PLUGH'` in the migration file.

Using a specific revision is safer than `downgrade -1` (you can pop
off too many revisions, causing loss of data)!!  Both the `upgrade`
and `downgrade` commands take a hash to get the state to a specific
revision.

You can inspect the state of a table by running `psql my-rss-fetcher` (for a
local database) or `ssh -t dokku@$(hostname) postgres:connect
my-rss-fetcher` and typing `\d TABLE` to inspect the table column and
index definitions after each {up,down}grade; type `\q` or CTRL/D to quit psql

If the downgrade fails, you may need to restore the state of the database by hand!

If you need to make a change in a column that you've already modified,
best to run the reverse migration before touching `models.py`

You can ALWAYS remove the new migration file (`git rm` it if you've
run `git add`) and autogenerate a new one (so long as your database is
in a clean (pre-migration) state).

### More Alembic Commands

`venv/bin/alembic history` shows existing migration files newest to oldest
(NOT the state of the database, does not need `DATABASE_URL` to be set).

`venv/bin/alembic history -i` shows migrations with the current state
state of the database marked with `(current)`
