# leaguebot.py

import discord
from discord.ext import commands
from discord.utils import get

from . import cogs
from . import helpers
from .helpers.utils import Map

import aiohttp
import asyncio
import json
import sys
import traceback
import os
from apscheduler.schedulers.asyncio import AsyncIOScheduler


_CWD = os.path.dirname(os.path.abspath(__file__))
INTENTS_JSON = os.path.join(_CWD, 'intents.json')


class LeagueBot(commands.AutoShardedBot):
    """ Sub-classed AutoShardedBot modified to fit the needs of the application. """

    def __init__(self, discord_token, api_base_url, api_key, db_connect_url):
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
        self.db_connect_url = db_connect_url
        self.all_maps = {}

        # Set constants
        self.color = 0x0086FF
        self.activity = discord.Activity(type=discord.ActivityType.watching, name="CS:GO League")

        # Create session for API
        self.api_helper = helpers.ApiHelper(self.loop, self.api_base_url, self.api_key)

        # Create DB helper to use connection pool
        self.db_helper = helpers.DBHelper(self.db_connect_url)

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

    async def get_pug_data(self, category, data):
        """"""
        guild_data = await self.db_helper.get_pug(category.id)
        try:
            return guild_data[data]
        except KeyError:
            return None

    async def isValidChannel(self, ctx):
        """"""
        try:
            channel_id = await self.get_pug_data(ctx.channel.category, 'text_commands')
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
        url_path = 'https://raw.githubusercontent.com/thboss/CSGO-PUGs-Bot/master/assets/maps/icons/'
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

                    self.all_maps[emoji_dev] = Map(emoji_name,emoji_dev,
                                                     f'<:{emoji_dev}:{emoji.id}>',
                                                     f'{url_path}{icon.replace(" ", "%20")}')

    async def create_ban_role(self, guilds):
        """"""
        for guild in guilds:
            ban_role = await self.db_helper.get_guild(guild.id)
            ban_role_id = ban_role['ban_role']
            if not ban_role_id or not get(guild.roles, id=ban_role_id):
                role = await guild.create_role(name='pugs_banned')
                await self.db_helper.update_guild(guild.id, ban_role=role.id)

    @commands.Cog.listener()
    async def on_ready(self):
        """ Synchronize the guilds the bot is in with the guilds table. """
        await self.db_helper.sync_guilds(*(guild.id for guild in self.guilds))
        print('Creating emojis...')
        await self.create_emojis()
        await self.create_ban_role(self.guilds)
        print('Bot is ready!')

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        """ Insert the newly added guild to the guilds table. """
        await self.db_helper.insert_guilds(guild.id)
        await self.create_emojis()
        await self.create_ban_role([guild])

    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        """ Delete the recently removed guild from the guilds table. """
        await self.db_helper.delete_guilds(guild.id)

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
        await self.api_helper.close()
        await self.db_helper.close()
        self.scheduler.shutdown(wait=False)
