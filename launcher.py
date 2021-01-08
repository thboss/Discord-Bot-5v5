# launcher.py

from bot.bot import LeagueBot

import argparse
import asyncio
import asyncpg
from dotenv import load_dotenv
import os

load_dotenv() # Load the environment variables in the local .env file

def run_bot():
    """ Parse the config file and run the bot. """
    # Get database object for bot
    db_connect_url = 'postgresql://{POSTGRESQL_USER}:{POSTGRESQL_PASSWORD}@{POSTGRESQL_HOST}:{POSTGRESQL_PORT}/{POSTGRESQL_DB}'
    db_connect_url = db_connect_url.format(**os.environ)

    # Get environment variables
    bot_token = os.environ['DISCORD_BOT_TOKEN']
    api_url = os.environ['CSGO_LEAGUE_API_URL']
    api_key = os.environ['CSGO_LEAGUE_API_KEY']
    donate_url = os.environ['CSGO_LEAGUE_DONATE_URL']

    if api_url.endswith('/'):
        api_url = api_url[:-1]
    # Instantiate bot and run
    bot = LeagueBot(bot_token, api_url, api_key, db_connect_url, donate_url)
    bot.run()


if __name__ == '__main__':
    argparse.ArgumentParser(description='Run the CS:GO League bot')
    run_bot()
