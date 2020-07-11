# leaguebot.py

import discord
from discord.ext import commands

from . import cogs
from . import helpers

import aiohttp
import json
import sys
import traceback
import os


class LeagueBot(commands.AutoShardedBot):
    """ Sub-classed AutoShardedBot modified to fit the needs of the application. """

    def __init__(self, discord_token, api_base_url, api_key, str_category, str_role, str_text_queue,
                 str_text_commands, str_text_results, str_voice_lobby, db_pool):
        """ Set attributes and configure bot. """
        # Call parent init
        super().__init__(command_prefix=('q!', 'Q!'), case_insensitive=True)

        # Set argument attributes
        self.discord_token = discord_token
        self.api_base_url = api_base_url
        self.api_key = api_key
        self.str_category = str_category
        self.str_role = str_role
        self.str_text_queue = str_text_queue
        self.str_text_commands = str_text_commands
        self.str_text_results = str_text_results
        self.str_voice_lobby = str_voice_lobby
        self.db_pool = db_pool

        # Set constants
        self.description = 'An easy to use, fully automated system to set up and play CS:GO pickup games'
        self.color = 0x000000
        self.activity = discord.Activity(type=discord.ActivityType.watching, name="#how-to-play")

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
            msg = f'This command disallowed here! Use {commands_channel.mention}'
            embed = self.embed_template(description=msg)
            await ctx.send(embed=embed)
            return False
        return True              

    async def setup_emojis(self):
        """ Upload custom map emojis to guilds. """
        path = 'assets/maps/icons/'
        icons = os.listdir(path)
        data = {}
        emojis = [e.name for e in self.guilds[0].emojis]
        for icon in icons:
            map_name = icon.split('.')[0]
            if map_name not in emojis:
                with open(path + icon, 'rb') as image:
                    emoji = await self.guilds[0].create_custom_emoji(name=map_name, image=image.read())
                    data[map_name] = emoji.id
                with open('maps_data.json', 'w+') as f:
                    json.dump(data, f)

    async def setup_channels(self):
        """ Setup required channels on guilds. """
        for guild in self.guilds:      
            categories = [n.name for n in guild.categories]
            roles = [n.name for n in guild.roles]
            channels = [n.name for n in guild.channels]
            everyone_role = discord.utils.get(guild.roles, name='@everyone')          

            if self.str_category not in categories:
                categ = await guild.create_category_channel(name=self.str_category)
                await self.db_helper.update_guild(guild.id, category=categ.id)

            if self.str_role not in roles:
                role = await guild.create_role(name=self.str_role)            
                await self.db_helper.update_guild(guild.id, role=role.id)

            category = guild.get_channel(await self.get_guild_data(guild, 'category'))
            role = guild.get_role(await self.get_guild_data(guild, 'role'))

            if self.str_text_queue not in channels:
                text_channel_queue = await guild.create_text_channel(name=self.str_text_queue, category=category)
                await text_channel_queue.set_permissions(everyone_role, send_messages=False)
                await self.db_helper.update_guild(guild.id, text_queue=text_channel_queue.id)

            if self.str_text_commands not in channels:
                text_channel_commands = await guild.create_text_channel(name=self.str_text_commands, category=category)
                await self.db_helper.update_guild(guild.id, text_commands=text_channel_commands.id)

            if self.str_text_results not in channels:
                text_channel_results = await guild.create_text_channel(name=self.str_text_results, category=category)
                await text_channel_results.set_permissions(everyone_role, send_messages=False)
                await self.db_helper.update_guild(guild.id, text_results=text_channel_results.id)

            if self.str_voice_lobby not in channels:
                voice_channel_lobby = await guild.create_voice_channel(name=self.str_voice_lobby, category=category, user_limit=10)
                await voice_channel_lobby.set_permissions(role, connect=True)
                await voice_channel_lobby.set_permissions(everyone_role, connect=False)                
                await self.db_helper.update_guild(guild.id, voice_lobby=voice_channel_lobby.id)

    @commands.Cog.listener()
    async def on_ready(self):
        """ Synchronize the guilds the bot is in with the guilds table. """
        await self.db_helper.sync_guilds(*(guild.id for guild in self.guilds))
        await self.setup_channels()
        await self.setup_emojis()

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
