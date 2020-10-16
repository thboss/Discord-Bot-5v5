# launcher.py

from bot.bot import LeagueBot

import asyncio
import asyncpg
from dotenv import load_dotenv
import os

load_dotenv() # Load the environment variables in the local .env file

def run_bot():
    """ Parse the config file and run the bot. """
    # Get database object for bot
    user = '{POSTGRESQL_USER}' if '{POSTGRESQL_USER}' else 'csgoleague'
    password = '{POSTGRESQL_PASSWORD}' if '{POSTGRESQL_PASSWORD}' else 'yourpassword'
    host = '{POSTGRESQL_HOST}' if '{POSTGRESQL_HOST}' else '127.0.0.1'
    port = '{POSTGRESQL_PORT}' if '{POSTGRESQL_PORT}' else '5432'
    db = '{POSTGRESQL_DB}' if '{POSTGRESQL_DB}' else 'csgoleague'
    connect_url = f'postgresql://{user}:{password}@{host}:{port}/{db}'
    loop = asyncio.get_event_loop()
    db_pool = loop.run_until_complete(asyncpg.create_pool(connect_url.format(**os.environ)))

    # Get environment variables
    bot_token = os.environ['DISCORD_BOT_TOKEN']
    api_url = os.environ['CSGO_LEAGUE_API_URL']
    api_key = os.environ['CSGO_LEAGUE_API_KEY']

    if api_url.endswith('/'):
        api_url = api_url[:-1]
    # Instantiate bot and run
    bot = LeagueBot(bot_token, api_url, api_key, db_pool)
    bot.run()


if __name__ == '__main__':
    run_bot()
