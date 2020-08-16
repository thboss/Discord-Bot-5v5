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
        super().__init__(command_prefix=('q!', 'Q!'), case_insensitive=True)

        # Set argument attributes
        self.discord_token = discord_token
        self.api_base_url = api_base_url
        self.api_key = api_key
        self.str_category = os.environ['DISCORD_LEAGUE_CATEGORY']
        self.str_pug_role = os.environ['DISCORD_LEAGUE_PUG_ROLE']
        self.str_alerts_role = os.environ['DISCORD_LEAGUE_ALERTS_ROLE']
        try:
            self.int_remaining_alerts = int(os.environ['DISCORD_LEAGUE_REMAINING_ALERTS'])
        except ValueError:
            self.int_remaining_alerts = 0
        self.str_text_queue = os.environ['DISCORD_LEAGUE_TEXT_QUEUE']
        self.str_text_commands = os.environ['DISCORD_LEAGUE_TEXT_COMMANDS']
        self.str_text_results = os.environ['DISCORD_LEAGUE_TEXT_RESULT']
        self.str_voice_lobby = os.environ['DISCORD_LEAGUE_VOICE_LOBBY']
        self.language = os.environ['DISCORD_LEAGUE_LANGUAGE']
        self.db_pool = db_pool
        self.all_maps = []

        with open('translations.json', 'r') as f:
            self.translations = json.load(f)

        # Set constants
        self.description = 'An easy to use, fully automated system to set up and play CS:GO pickup games'
        self.color = 0x000000
        self.activity = discord.Activity(type=discord.ActivityType.watching, name="TheBO$$#2967")

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

        # Add cogs
        self.add_cog(cogs.ConsoleCog(self))
        self.add_cog(cogs.HelpCog(self))
        self.add_cog(cogs.AuthCog(self))
        self.add_cog(cogs.QueueCog(self))
        self.add_cog(cogs.MatchCog(self))
        self.add_cog(cogs.StatsCog(self))
    
    def translate(self, text):
        try:
            return self.translations[self.language][text]
        except KeyError:
            return self.translations['en'][text]

    def embed_template(self, **kwargs):
        """ Implement the bot's default-style embed. """
        kwargs['color'] = self.color
        return discord.Embed(**kwargs)

    async def get_guild_data(self, guild, data):
        guild_data = await self.db_helper.get_guild(guild.id)
        return guild_data[data]

    async def isValidChannel(self, ctx):
        channel_id = await self.get_guild_data(ctx.guild, 'text_commands')
        commands_channel = self.get_channel(channel_id)
        if ctx.message.channel != commands_channel:
            return False
        return True              

    async def setup_emojis(self):
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

                self.all_maps.append(Map(emoji_name, emoji_dev, f'<:{emoji_dev}:{emoji.id}>', f'{url_path}{icon.replace(" ", "%20")}'))

    async def setup_channels(self):
        """ Setup required channels on guilds. """
        for guild in self.guilds:      
            categories = [n.name for n in guild.categories]
            roles = [n.name for n in guild.roles]
            channels = [n.name for n in guild.channels]
            everyone_role = get(guild.roles, name='@everyone')          

            if self.str_category in categories:
                categ = get(guild.categories, name=self.str_category)
            else:
                categ = await guild.create_category_channel(name=self.str_category)

            if self.str_pug_role in roles:
                pug_role = get(guild.roles, name=self.str_pug_role)
            else:
                pug_role = await guild.create_role(name=self.str_pug_role)

            if self.str_alerts_role in roles:
                alerts_role = get(guild.roles, name=self.str_alerts_role)
            else:
                alerts_role = await guild.create_role(name=self.str_alerts_role)

            if self.str_text_queue in channels:
                text_channel_queue = get(guild.channels, name=self.str_text_queue)
            else:
                text_channel_queue = await guild.create_text_channel(name=self.str_text_queue, category=categ)

            if self.str_text_commands in channels:
                text_channel_commands = get(guild.channels, name=self.str_text_commands)
            else:
                text_channel_commands = await guild.create_text_channel(name=self.str_text_commands, category=categ)

            if self.str_text_results in channels:
                text_channel_results = get(guild.channels, name=self.str_text_results)
            else:
                text_channel_results = await guild.create_text_channel(name=self.str_text_results, category=categ)

            if self.str_voice_lobby in channels:
                voice_channel_lobby = get(guild.channels, name=self.str_voice_lobby)
            else:
                voice_channel_lobby = await guild.create_voice_channel(name=self.str_voice_lobby,
                                                                       category=categ, user_limit=10)                

            await self.db_helper.update_guild(guild.id, category=categ.id),
            await self.db_helper.update_guild(guild.id, pug_role=pug_role.id),
            await self.db_helper.update_guild(guild.id, alerts_role=alerts_role.id),
            await self.db_helper.update_guild(guild.id, text_queue=text_channel_queue.id),
            await self.db_helper.update_guild(guild.id, text_commands=text_channel_commands.id),
            await self.db_helper.update_guild(guild.id, text_results=text_channel_results.id),
            await self.db_helper.update_guild(guild.id, voice_lobby=voice_channel_lobby.id),
            await text_channel_queue.set_permissions(everyone_role, send_messages=False),
            await text_channel_results.set_permissions(everyone_role, send_messages=False),
            await voice_channel_lobby.set_permissions(everyone_role, connect=False),
            await voice_channel_lobby.set_permissions(pug_role, connect=True)

    @commands.Cog.listener()
    async def on_ready(self):
        """ Synchronize the guilds the bot is in with the guilds table. """
        await self.db_helper.sync_guilds(*(guild.id for guild in self.guilds))
        await self.setup_emojis()
        await self.setup_channels()

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        """ Insert the newly added guild to the guilds table. """
        await self.db_helper.insert_guilds(guild.id)
        await self.setup_channels()

    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
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
        await self.session.close()
        await self.db_pool.close()
