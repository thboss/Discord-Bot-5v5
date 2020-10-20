# leaguebot.py

import discord
from discord.ext import commands
from discord.utils import get

from . import cogs
from . import helpers

import aiohttp
import asyncio
import json
import sys
import traceback
import os
from apscheduler.schedulers.asyncio import AsyncIOScheduler


_CWD = os.path.dirname(os.path.abspath(__file__))
INTENTS_JSON = os.path.join(_CWD, 'intents.json')


class Map:
    """ A group of attributes representing a map. """

    def __init__(self, name, dev_name, emoji, image_url):
        """ Set attributes. """
        self.name = name
        self.dev_name = dev_name
        self.emoji = emoji
        self.image_url = image_url


class LeagueBot(commands.AutoShardedBot):
    """ Sub-classed AutoShardedBot modified to fit the needs of the application. """

    def __init__(self, discord_token, api_base_url, api_key, db_pool):
        """ Set attributes and configure bot. """
        # Call parent init
        with open(INTENTS_JSON) as f:
            intents_attrs = json.load(f)

        intents = discord.Intents(**intents_attrs)
        super().__init__(command_prefix=('q!', 'Q!'), case_insensitive=True, intents=intents)

        # Set argument attributes
        self.discord_token = discord_token
        self.api_base_url = api_base_url
        self.api_key = api_key
        self.db_pool = db_pool
        self.all_maps = []

        # Set constants
        self.color = 0x0086FF
        self.activity = discord.Activity(type=discord.ActivityType.watching, name="CS:GO League")

        # Create session for API
        self.session = aiohttp.ClientSession(loop=self.loop, json_serialize=lambda x: json.dumps(x, ensure_ascii=False),
                                             raise_for_status=True)
        self.api_helper = helpers.ApiHelper(self.session, self.api_base_url, self.api_key)

        # Create DB helper to use connection pool
        self.db_helper = helpers.DBHelper(self.db_pool)

        # Initialize set of errors to ignore
        self.ignore_error_types = set()

        # Add check to not respond to DM'd commands
        self.add_check(lambda ctx: ctx.guild is not None)
        self.ignore_error_types.add(commands.errors.CheckFailure)

        # Trigger typing before every command
        self.before_invoke(commands.Context.trigger_typing)

        self.scheduler = AsyncIOScheduler()
        self.scheduler.start()

        # Add cogs
        self.add_cog(cogs.ConsoleCog(self))
        self.add_cog(cogs.HelpCog(self))
        self.add_cog(cogs.QueueCog(self))
        self.add_cog(cogs.MatchCog(self))
        self.add_cog(cogs.CommandsCog(self))

    def embed_template(self, **kwargs):
        """ Implement the bot's default-style embed. """
        kwargs['color'] = self.color
        return discord.Embed(**kwargs)

    async def get_league_data(self, category, data):
        guild_data = await self.db_helper.get_league(category.id)
        try:
            return guild_data[data]
        except KeyError:
            return None

    async def isValidChannel(self, ctx):
        try:
            channel_id = await self.get_league_data(ctx.channel.category, 'text_commands')
        except AttributeError:
            channel_id = None
        commands_channel = self.get_channel(channel_id)
        if ctx.message.channel != commands_channel:
            embed = self.embed_template(title='Invalid channel')
            await ctx.send(embed=embed)
            return False
        return True

    async def create_emojis(self):
        """ Upload custom map emojis to guilds. """
        url_path = 'https://raw.githubusercontent.com/thboss/Discord-Bot-5v5/master/assets/maps/icons/'
        icons_dic = 'assets/maps/icons/'
        icons = os.listdir(icons_dic)
        emojis = [e.name for e in self.guilds[0].emojis]

        for icon in icons:
            if icon.endswith('.png') and '-' in icon and os.stat(icons_dic + icon).st_size < 256000:
                emoji_name = icon.split('-')[0]
                emoji_dev = icon.split('-')[1].split('.')[0]
                if emoji_dev not in emojis:
                    with open(icons_dic + icon, 'rb') as image:
                        emoji = await self.guilds[0].create_custom_emoji(name=emoji_dev, image=image.read())
                else:
                    emoji = get(self.guilds[0].emojis, name=emoji_dev)

                self.all_maps.append(
                    Map(emoji_name, emoji_dev, f'<:{emoji_dev}:{emoji.id}>', f'{url_path}{icon.replace(" ", "%20")}'))

    @commands.Cog.listener()
    async def on_ready(self):
        """ Synchronize the guilds the bot is in with the guilds table. """
        print('Creating emojis...')
        await self.db_helper.sync_guilds(*(guild.id for guild in self.guilds))
        await self.create_emojis()
        print('Bot is ready!')

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        """ Send help message when a mis-entered command is received. """
        if type(error) not in self.ignore_error_types:
            print('Ignoring exception in command {}:'.format(ctx.command), file=sys.stderr)
            traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)

    def run(self):
        """ Override parent run to automatically include Discord token. """
        super().run(self.discord_token)

    async def close(self):
        """ Override parent close to close the API session also. """
        await super().close()
        await self.session.close()
        await self.db_pool.close()
