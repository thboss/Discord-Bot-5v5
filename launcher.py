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
    connect_url = 'postgresql://{POSTGRESQL_USER}:{POSTGRESQL_PASSWORD}@{POSTGRESQL_HOST}/{POSTGRESQL_DB}'
    loop = asyncio.get_event_loop()
    db_pool = loop.run_until_complete(asyncpg.create_pool(connect_url.format(**os.environ)))

    # Get environment variables
    bot_token = os.environ['DISCORD_BOT_TOKEN']
    api_url = os.environ['CSGO_LEAGUE_API_URL']
    api_key = os.environ['CSGO_LEAGUE_API_KEY']
    discord_categoty = os.environ['DISCORD_LEAGUE_CATEGORY']
    discord_pug_role = os.environ['DISCORD_LEAGUE_PUG_ROLE']
    discord_alerts_role = os.environ['DISCORD_LEAGUE_ALERTS_ROLE']
    discord_remaining_alerts = os.environ['DISCORD_LEAGUE_REMAINING_ALERTS']
    discord_queue = os.environ['DISCORD_LEAGUE_TEXT_QUEUE']
    discord_commands = os.environ['DISCORD_LEAGUE_TEXT_COMMANDS']
    discord_results = os.environ['DISCORD_LEAGUE_TEXT_RESULT']
    discord_lobby = os.environ['DISCORD_LEAGUE_VOICE_LOBBY']
    discord_language = os.environ['DISCORD_LEAGUE_LANGUAGE']

    if api_url.endswith('/'):
        api_url = api_url[:-1]
    # Instantiate bot and run
    bot = LeagueBot(bot_token, api_url, api_key, discord_categoty, discord_pug_role,
                    discord_alerts_role, discord_remaining_alerts, discord_queue, discord_commands,
                    discord_results, discord_lobby, discord_language, db_pool)
    bot.run()


if __name__ == '__main__':
    run_bot()
