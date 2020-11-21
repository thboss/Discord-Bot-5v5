# db.py


import asyncio
import asyncpg
import os

icons_dir = 'assets/maps/icons/'
maps = [_map for _map in os.listdir(icons_dir) if
        _map.endswith('.png') and '-' in _map and os.stat(icons_dir + _map).st_size < 256000]


class DBHelper:
    """ Class to contain database query wrapper functions. """

    def __init__(self, connect_url):
        """ Set attributes. """
        loop = asyncio.get_event_loop()
        self.pool = loop.run_until_complete(asyncpg.create_pool(connect_url))

    async def close(self):
        """"""
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

    async def insert_pugs(self, *pug_ids):
        """ Add a list of pugs into the pugs table and return the ones successfully added. """
        rows = [tuple([pug_id] + [None] * 9 + [None] * len(maps)) for pug_id in pug_ids]
        statement = (
            'INSERT INTO pugs (id)\n'
            '    (SELECT id FROM unnest($1::pugs[]))\n'
            '    ON CONFLICT (id) DO NOTHING\n'
            '    RETURNING id;'
        )

        async with self.pool.acquire() as connection:
            async with connection.transaction():
                inserted = await connection.fetch(statement, rows)

        return self._get_record_attrs(inserted, 'id')

    async def delete_pugs(self, *pug_ids):
        """ Remove a list of pugs from the pugs table and return the ones successfully removed. """
        statement = (
            'DELETE FROM pugs\n'
            '    WHERE id::BIGINT = ANY($1::BIGINT[])\n'
            '    RETURNING id;'
        )

        async with self.pool.acquire() as connection:
            async with connection.transaction():
                deleted = await connection.fetch(statement, pug_ids)

        return self._get_record_attrs(deleted, 'id')

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

    async def get_queued_users(self, guild_id):
        """ Get all the queued users of the guild from the queued_users table. """
        statement = (
            'SELECT user_id FROM queued_users\n'
            '    WHERE guild_id = $1;'
        )

        async with self.pool.acquire() as connection:
            async with connection.transaction():
                queue = await connection.fetch(statement, guild_id)

        return self._get_record_attrs(queue, 'user_id')

    async def insert_queued_users(self, guild_id, *user_ids):
        """ Insert multiple users of a guild into the queued_users table. """
        statement = (
            'INSERT INTO queued_users (guild_id, user_id)\n'
            '    (SELECT * FROM unnest($1::queued_users[]));'
        )

        async with self.pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute(statement, [(guild_id, user_id) for user_id in user_ids])

    async def delete_queued_users(self, guild_id, *user_ids):
        """ Delete multiple users of a guild from the queued_users table. """
        statement = (
            'DELETE FROM queued_users\n'
            '    WHERE guild_id = $1 AND user_id = ANY($2::BIGINT[])\n'
            '    RETURNING user_id;'
        )

        async with self.pool.acquire() as connection:
            async with connection.transaction():
                deleted = await connection.fetch(statement, guild_id, user_ids)

        return self._get_record_attrs(deleted, 'user_id')

    async def delete_all_queued_users(self, guild_id):
        """ Delete all users of a guild from the queued_users table. """
        statement = (
            'DELETE FROM queued_users\n'
            '    WHERE guild_id = $1\n'
            '    RETURNING user_id;'
        )

        async with self.pool.acquire() as connection:
            async with connection.transaction():
                deleted = await connection.fetch(statement, guild_id)

        return self._get_record_attrs(deleted, 'user_id')

    async def get_spect_users(self, guild_id):
        """ Get all the queued users of the guild from the spect_users table. """
        statement = (
            'SELECT user_id FROM spect_users\n'
            '    WHERE guild_id = $1;'
        )

        async with self.pool.acquire() as connection:
            async with connection.transaction():
                queue = await connection.fetch(statement, guild_id)

        return self._get_record_attrs(queue, 'user_id')

    async def insert_spect_users(self, guild_id, *user_ids):
        """ Insert multiple users of a guild into the spect_users table. """
        statement = (
            'INSERT INTO spect_users (guild_id, user_id)\n'
            '    (SELECT * FROM unnest($1::spect_users[]));'
        )

        async with self.pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute(statement, [(guild_id, user_id) for user_id in user_ids])

    async def delete_spect_users(self, guild_id, *user_ids):
        """ Delete multiple users of a guild from the spect_users table. """
        statement = (
            'DELETE FROM spect_users\n'
            '    WHERE guild_id = $1 AND user_id = ANY($2::BIGINT[])\n'
            '    RETURNING user_id;'
        )

        async with self.pool.acquire() as connection:
            async with connection.transaction():
                deleted = await connection.fetch(statement, guild_id, user_ids)

        return self._get_record_attrs(deleted, 'user_id')

    async def delete_all_spect_users(self, guild_id):
        """ Delete all users of a guild from the spect_users table. """
        statement = (
            'DELETE FROM spect_users\n'
            '    WHERE guild_id = $1\n'
            '    RETURNING user_id;'
        )

        async with self.pool.acquire() as connection:
            async with connection.transaction():
                deleted = await connection.fetch(statement, guild_id)

        return self._get_record_attrs(deleted, 'user_id')

    async def get_pug(self, pug_id):
        """ Get a pug's row from the pugs table. """
        return await self._get_row('pugs', pug_id)

    async def update_pug(self, pug_id, **data):
        """ Update a pug's row in the pugs table. """
        return await self._update_row('pugs', pug_id, **data)
