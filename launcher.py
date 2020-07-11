# launcher.py

from bot.bot import LeagueBot

import asyncio
import asyncpg
from dotenv import load_dotenv
from operator import itemgetter
from os import environ


def run_bot():
    """ Parse the config file and run the bot. """
    # Load the environment variables in the local .env file
    load_dotenv()

    # Get database object for bot
    connect_url = 'postgresql://{POSTGRESQL_USER}:{POSTGRESQL_PASSWORD}@{POSTGRESQL_HOST}/{POSTGRESQL_DB}'
    loop = asyncio.get_event_loop()
    db_pool = loop.run_until_complete(asyncpg.create_pool(connect_url.format(**environ)))

    # Instantiate bot and run
    env_varnames = ['DISCORD_BOT_TOKEN', 'CSGO_LEAGUE_API_URL', 'CSGO_LEAGUE_API_KEY', 'DISCORD_LEAGUE_CATEGORY',
                    'DISCORD_LEAGUE_ROLE', 'DISCORD_LEAGUE_TEXT_QUEUE', 'DISCORD_LEAGUE_TEXT_COMMANDS',
                    'DISCORD_LEAGUE_TEXT_RESULT', 'DISCORD_LEAGUE_VOICE_LOBBY']
    bot = LeagueBot(*itemgetter(*env_varnames)(environ), db_pool=db_pool)
    bot.run()


if __name__ == '__main__':
    run_bot()
