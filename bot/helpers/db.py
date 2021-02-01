# db.py


import asyncio
import asyncpg
import os
import logging

icons_dir = 'assets/maps/icons/'
maps = [_map for _map in os.listdir(icons_dir) if
        _map.endswith('.png') and '-' in _map and os.stat(icons_dir + _map).st_size < 256000]


class DBHelper:
    """ Class to contain database query wrapper functions. """

    def __init__(self, connect_url):
        """ Set attributes. """
        loop = asyncio.get_event_loop()
        self.logger = logging.getLogger('csgoleague.db')
        self.logger.info('Creating database connection pool')
        self.pool = loop.run_until_complete(asyncpg.create_pool(connect_url))

    async def close(self):
        """"""
        self.logger.info('Closing database connection pool')
        await self.pool.close()

    @staticmethod
    def _get_record_attrs(records, key):
        """ Get key list of attributes from list of Record objects. """
        return list(map(lambda r: r[key], records))

    async def _get_row(self, table, row_id):
        """ Generic method to get table row by object id. """
        statement = (
            f'SELECT * FROM {table}\n'
            '    WHERE id = $1'
        )

        async with self.pool.acquire() as connection:
            async with connection.transaction():
                row = await connection.fetchrow(statement, row_id)
        try:
            return {col: val for col, val in row.items()}
        except AttributeError:
            return {}

    async def _update_row(self, table, row_id, **data):
        """ Generic method to update table row by object id. """
        cols = list(data.keys())
        col_vals = ',\n    '.join(f'{col} = ${num}' for num, col in enumerate(cols, start=2))
        ret_vals = ',\n    '.join(cols)
        statement = (
            f'UPDATE {table}\n'
            f'    SET {col_vals}\n'
            '    WHERE id = $1\n'
            f'    RETURNING {ret_vals};'
        )

        async with self.pool.acquire() as connection:
            async with connection.transaction():
                updated_vals = await connection.fetch(statement, row_id, *[data[col] for col in cols])

        return {col: val for rec in updated_vals for col, val in rec.items()}

    async def insert_guilds(self, *guild_ids):
        """ Add a list of guilds into the guilds table and return the ones successfully added. """
        rows = [(guild_id, None, None, None) for guild_id in guild_ids]
        statement = (
            'INSERT INTO guilds (id)\n'
            '    (SELECT id FROM unnest($1::guilds[]))\n'
            '    ON CONFLICT (id) DO NOTHING\n'
            '    RETURNING id;'
        )

        async with self.pool.acquire() as connection:
            async with connection.transaction():
                inserted = await connection.fetch(statement, rows)

        return self._get_record_attrs(inserted, 'id')

    async def delete_guilds(self, *guild_ids):
        """ Remove a list of guilds from the guilds table and return the ones successfully removed. """
        statement = (
            'DELETE FROM guilds\n'
            '    WHERE id::BIGINT = ANY($1::BIGINT[])\n'
            '    RETURNING id;'
        )

        async with self.pool.acquire() as connection:
            async with connection.transaction():
                deleted = await connection.fetch(statement, guild_ids)

        return self._get_record_attrs(deleted, 'id')

    async def sync_guilds(self, *guild_ids):
        """ Synchronizes the guilds table with the guilds in the bot. """
        insert_rows = [(guild_id, None, None, None) for guild_id in guild_ids]
        insert_statement = (
            'INSERT INTO guilds (id)\n'
            '    (SELECT id FROM unnest($1::guilds[]))\n'
            '    ON CONFLICT (id) DO NOTHING\n'
            '    RETURNING id;'
        )
        delete_statement = (
            'DELETE FROM guilds\n'
            '    WHERE id::BIGINT != ALL($1::BIGINT[])\n'
            '    RETURNING id;'
        )

        async with self.pool.acquire() as connection:
            async with connection.transaction():
                inserted = await connection.fetch(insert_statement, insert_rows)
                deleted = await connection.fetch(delete_statement, guild_ids)

        return self._get_record_attrs(inserted, 'id'), self._get_record_attrs(deleted, 'id')

    async def insert_leagues(self, *league_ids):
        """ Add a list of pugs into the pugs table and return the ones successfully added. """
        rows = [tuple([league_id] + [None] * 7 + [None] * len(maps)) for league_id in league_ids]
        statement = (
            'INSERT INTO leagues (id)\n'
            '    (SELECT id FROM unnest($1::leagues[]))\n'
            '    ON CONFLICT (id) DO NOTHING\n'
            '    RETURNING id;'
        )

        async with self.pool.acquire() as connection:
            async with connection.transaction():
                inserted = await connection.fetch(statement, rows)

        return self._get_record_attrs(inserted, 'id')

    async def delete_leagues(self, *league_ids):
        """ Remove a list of pugs from the pugs table and return the ones successfully removed. """
        statement = (
            'DELETE FROM leagues\n'
            '    WHERE id::BIGINT = ANY($1::BIGINT[])\n'
            '    RETURNING id;'
        )

        async with self.pool.acquire() as connection:
            async with connection.transaction():
                deleted = await connection.fetch(statement, league_ids)

        return self._get_record_attrs(deleted, 'id')

    async def get_guild_leagues(self, guild_id):
        """ Get all leagues of the guild from the guild_leagues table. """
        statement = (
            'SELECT league_id FROM guild_leagues\n'
            '    WHERE guild_id = $1;'
        )

        async with self.pool.acquire() as connection:
            async with connection.transaction():
                leagues = await connection.fetch(statement, guild_id)

        return self._get_record_attrs(leagues, 'league_id')

    async def insert_guild_leagues(self, guild_id, *league_ids):
        """ Insert multiple leagues of a guild into the guild_leagues table. """
        statement = (
            'INSERT INTO guild_leagues (guild_id, league_id)\n'
            '    (SELECT * FROM unnest($1::guild_leagues[]));'
        )

        async with self.pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute(statement, [(guild_id, league_id) for league_id in league_ids])

    async def delete_guild_leagues(self, guild_id, *league_ids):
        """ Delete multiple leagues of a guild from the guild_leagues table. """
        statement = (
            'DELETE FROM guild_leagues\n'
            '    WHERE guild_id = $1 AND league_id = ANY($2::BIGINT[])\n'
            '    RETURNING league_id;'
        )

        async with self.pool.acquire() as connection:
            async with connection.transaction():
                deleted = await connection.fetch(statement, guild_id, league_ids)

        return self._get_record_attrs(deleted, 'league_id')

    async def clear_guild_leagues(self, guild_id):
        """ Delete all leagues of a guild from the guild_leagues table. """
        statement = (
            'DELETE FROM guild_leagues\n'
            '    WHERE guild_id = $1\n'
            '    RETURNING league_id;'
        )

        async with self.pool.acquire() as connection:
            async with connection.transaction():
                deleted = await connection.fetch(statement, guild_id)

        return self._get_record_attrs(deleted, 'league_id')

    async def insert_users(self, *user_ids):
        """ Insert multiple users into the users table. """
        rows = [(user_id,) for user_id in user_ids]
        statement = (
            'INSERT INTO users (id)\n'
            '    (SELECT id FROM unnest($1::users[]))\n'
            '    ON CONFLICT (id) DO NOTHING\n'
            '    RETURNING id;'
        )

        async with self.pool.acquire() as connection:
            async with connection.transaction():
                inserted = await connection.fetch(statement, rows)

        return self._get_record_attrs(inserted, 'id')

    async def delete_users(self, *user_ids):
        """ Delete multiple users from the users table. """
        statement = (
            'DELETE FROM users\n'
            '    WHERE id::BIGINT = ANY($1::BIGINT[])\n'
            '    RETURNING id;'
        )

        async with self.pool.acquire() as connection:
            async with connection.transaction():
                deleted = await connection.fetch(statement, user_ids)

        return self._get_record_attrs(deleted, 'id')

    async def get_queued_users(self, league_id):
        """ Get all the queued users of the guild from the queued_users table. """
        statement = (
            'SELECT user_id FROM queued_users\n'
            '    WHERE league_id = $1;'
        )

        async with self.pool.acquire() as connection:
            async with connection.transaction():
                queue = await connection.fetch(statement, league_id)

        return self._get_record_attrs(queue, 'user_id')

    async def insert_queued_users(self, league_id, *user_ids):
        """ Insert multiple users of a guild into the queued_users table. """
        statement = (
            'INSERT INTO queued_users (league_id, user_id)\n'
            '    (SELECT * FROM unnest($1::queued_users[]));'
        )

        async with self.pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute(statement, [(league_id, user_id) for user_id in user_ids])

    async def delete_queued_users(self, league_id, *user_ids):
        """ Delete multiple users of a guild from the queued_users table. """
        statement = (
            'DELETE FROM queued_users\n'
            '    WHERE league_id = $1 AND user_id = ANY($2::BIGINT[])\n'
            '    RETURNING user_id;'
        )

        async with self.pool.acquire() as connection:
            async with connection.transaction():
                deleted = await connection.fetch(statement, league_id, user_ids)

        return self._get_record_attrs(deleted, 'user_id')

    async def clear_queued_users(self, league_id):
        """ Delete all users of a guild from the queued_users table. """
        statement = (
            'DELETE FROM queued_users\n'
            '    WHERE league_id = $1\n'
            '    RETURNING user_id;'
        )

        async with self.pool.acquire() as connection:
            async with connection.transaction():
                deleted = await connection.fetch(statement, league_id)

        return self._get_record_attrs(deleted, 'user_id')

    async def get_spect_users(self, league_id):
        """ Get all the queued users of the guild from the spect_users table. """
        statement = (
            'SELECT user_id FROM spect_users\n'
            '    WHERE league_id = $1;'
        )

        async with self.pool.acquire() as connection:
            async with connection.transaction():
                queue = await connection.fetch(statement, league_id)

        return self._get_record_attrs(queue, 'user_id')

    async def insert_spect_users(self, league_id, *user_ids):
        """ Insert multiple users of a guild into the spect_users table. """
        statement = (
            'INSERT INTO spect_users (league_id, user_id)\n'
            '    (SELECT * FROM unnest($1::spect_users[]));'
        )

        async with self.pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute(statement, [(league_id, user_id) for user_id in user_ids])

    async def delete_spect_users(self, league_id, *user_ids):
        """ Delete multiple users of a guild from the spect_users table. """
        statement = (
            'DELETE FROM spect_users\n'
            '    WHERE league_id = $1 AND user_id = ANY($2::BIGINT[])\n'
            '    RETURNING user_id;'
        )

        async with self.pool.acquire() as connection:
            async with connection.transaction():
                deleted = await connection.fetch(statement, league_id, user_ids)

        return self._get_record_attrs(deleted, 'user_id')

    async def get_banned_users(self, guild_id):
        """ Get all the banned users of the guild from the banned_users table. """
        select_statement = (
            'SELECT * FROM banned_users\n'
            '    WHERE guild_id = $1;'
        )

        async with self.pool.acquire() as connection:
            async with connection.transaction():
                queue = await connection.fetch(select_statement, guild_id)

        return dict(zip(self._get_record_attrs(queue, 'user_id'), self._get_record_attrs(queue, 'unban_time')))

    async def get_unbanned_users(self, guild_id):
        """ Get all the banned users of the guild from the banned_users table. """
        delete_statement = (
            'DELETE FROM banned_users\n'
            '    WHERE guild_id = $1 AND CURRENT_TIMESTAMP > unban_time\n'
            '    RETURNING user_id;'
        )

        async with self.pool.acquire() as connection:
            async with connection.transaction():
                deleted = await connection.fetch(delete_statement, guild_id)

        return self._get_record_attrs(deleted, 'user_id')

    async def insert_banned_users(self, guild_id, *user_ids, unban_time=None):
        """ Insert multiple users of a guild into the banned_users table"""
        statement = (
            'INSERT INTO banned_users (guild_id, user_id, unban_time)\n'
            '    VALUES($1, $2, $3)\n'
            '    ON CONFLICT (guild_id, user_id) DO UPDATE\n'
            '    SET unban_time = EXCLUDED.unban_time;'
        )

        insert_rows = [(guild_id, user_id, unban_time) for user_id in user_ids]

        async with self.pool.acquire() as connection:
            async with connection.transaction():
                await connection.executemany(statement, insert_rows)

    async def delete_banned_users(self, guild_id, *user_ids):
        """ Delete multiple users of a guild from the banned_users table. """
        statement = (
            'DELETE FROM banned_users\n'
            '    WHERE guild_id = $1 AND user_id = ANY($2::BIGINT[])\n'
            '    RETURNING user_id;'
        )

        async with self.pool.acquire() as connection:
            async with connection.transaction():
                deleted = await connection.fetch(statement, guild_id, user_ids)

        return self._get_record_attrs(deleted, 'user_id')

    async def get_league(self, league_id):
        """ Get a pug's row from the pugs table. """
        return await self._get_row('leagues', league_id)

    async def update_league(self, league_id, **data):
        """ Update a pug's row in the pugs table. """
        return await self._update_row('leagues', league_id, **data)

    async def get_guild(self, guild_id):
        """ Get a pug's row from the pugs table. """
        return await self._get_row('guilds', guild_id)

    async def update_guild(self, guild_id, **data):
        """ Update a pug's row in the pugs table. """
        return await self._update_row('guilds', guild_id, **data)
