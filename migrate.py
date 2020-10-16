# migrate.py

from dotenv import load_dotenv
from os import environ
import sys
from yoyo import get_backend, read_migrations


def migrate(direction):
    """ Apply Yoyo migrations for a given PostgreSQL database. """
    load_dotenv()
    user = '{POSTGRESQL_USER}' if '{POSTGRESQL_USER}' else 'csgoleague'
    password = '{POSTGRESQL_PASSWORD}' if '{POSTGRESQL_PASSWORD}' else 'yourpassword'
    host = '{POSTGRESQL_HOST}' if '{POSTGRESQL_HOST}' else '127.0.0.1'
    port = '{POSTGRESQL_PORT}' if '{POSTGRESQL_PORT}' else '5432'
    db = '{POSTGRESQL_DB}' if '{POSTGRESQL_DB}' else 'csgoleague'
    connect_url = f'postgresql://{user}:{password}@{host}:{port}/{db}'
    backend = get_backend(connect_url.format(**environ))
    migrations = read_migrations('./migrations')
    print('Applying migrations:\n' + '\n'.join(migration.id for migration in migrations))

    with backend.lock():
        if direction == 'up':
            backend.apply_migrations(backend.to_apply(migrations))
        elif direction == 'down':
            backend.rollback_migrations(backend.to_rollback(migrations))
        else:
            raise ValueError('Direction argument must be "up" or "down"')


if __name__ == '__main__':
    migrate(sys.argv[1])
