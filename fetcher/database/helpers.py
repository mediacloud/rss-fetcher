import sqlalchemy as sa

feeds_table = sa.sql.table('feeds',
                           sa.sql.column('mc_feeds_id', sa.BigInteger),
                           sa.sql.column('mc_media_id', sa.String),
                           sa.sql.column('name', sa.String),
                           sa.sql.column('url', sa.String),
                           sa.sql.column('type', sa.String),
                           sa.sql.column('active', sa.Boolean),
                           sa.sql.column('import_round', sa.Integer)
                           )