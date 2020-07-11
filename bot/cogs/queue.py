# queue.py

from discord.ext import commands
from discord.errors import NotFound
from discord.utils import get
import asyncio


class QueueCog(commands.Cog):
    """ Cog to manage queues of players among multiple servers. """

    def __init__(self, bot):
        """ Set attributes. """
        self.bot = bot
        self.last_queue_msgs = {}

    @commands.command(brief='get emoji')
    async def emoji(self, ctx):
        e = get(ctx.guild.emojis, name='de_mirage')
        print(e)

    async def queue_embed(self, guild, title=None):
        """ Method to create the queue embed for a guild. """
        queued_ids = await self.bot.db_helper.get_queued_users(guild.id)
        capacity = await self.bot.get_guild_data(guild, 'capacity')

        if title:
            title += f' ({len(queued_ids)}/{capacity})'

        if len(queued_ids) == 0:  # If there are no members in the queue
            queue_str = '_The queue is empty..._'
        else:  # members still in queue
            queue_str = ''.join(f'{num}. <@{member_id}>\n' for num, member_id in enumerate(queued_ids, start=1))

        embed = self.bot.embed_template(title=title, description=queue_str)
        embed.set_footer(text='Players will receive a notification when the queue fills up')
        return embed

    async def update_last_msg(self, ctx, embed):
        """ Send embed message and delete the last one sent. """
        msg = self.last_queue_msgs.get(ctx.guild)
        channel_id = await self.bot.get_guild_data(ctx.guild, 'text_queue')
        text_channel = ctx.guild.get_channel(channel_id)
        index_channel = ctx.guild.channels.index(text_channel)

        if msg is None:
            self.last_queue_msgs[ctx.guild] = await ctx.guild.channels[index_channel].send(embed=embed)
        else:
            try:
                await msg.edit(embed=embed)
            except NotFound:
                self.last_queue_msgs[ctx.guild] = await ctx.guild.channels[index_channel].send(embed=embed)

    @commands.command(brief='Check if account is linked and give linked role')
    async def check(self, ctx):
        if not await self.bot.isValidChannel(ctx):
            return

        if not await self.bot.api_helper.is_linked(ctx.author.id):
            msg = f'{ctx.author.mention} your discord is not linked to steam account, type **!link** to link it'
            embed = self.bot.embed_template(description=msg, color=self.bot.color)
            await ctx.send(embed=embed)
            return

        role_id = await self.bot.get_guild_data(ctx.guild, 'role')
        role = ctx.guild.get_role(role_id)
        await ctx.author.add_roles(role)
        await self.bot.api_helper.update_discord_name(ctx.author)

        channel_id = await self.bot.get_guild_data(ctx.guild, 'voice_lobby')
        voice_lobby = ctx.bot.get_channel(channel_id)
        msg = f'{ctx.author.mention} you got {role.mention} role and access to join **{voice_lobby.name}** ' \
              f'voice channel'
        embed = self.bot.embed_template(description=msg, color=self.bot.color)
        await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        channel_id = await self.bot.get_guild_data(member.guild, 'voice_lobby')
        voice_lobby = member.guild.get_channel(channel_id)
        if before.channel == voice_lobby and after.channel == voice_lobby:
            return

        name = member.nick if member.nick is not None else member.display_name
        match_cog = self.bot.get_cog('MatchCog')

        if after.channel is not None:
            if (after.channel != voice_lobby and before.channel != voice_lobby) or match_cog.moving_players:
                return
            else:
                if not await self.bot.api_helper.is_linked(member.id):  # Message author isn't linked
                    title = f'Unable to add **{name}**: Their account is not linked'
                else:  # Message author is linked
                    awaitables = [
                        self.bot.api_helper.get_player(member.id),
                        self.bot.db_helper.insert_users(member.id),
                        self.bot.db_helper.get_queued_users(member.guild.id),
                        self.bot.db_helper.get_guild(member.guild.id)
                    ]
                    results = await asyncio.gather(*awaitables, loop=self.bot.loop)
                    player = results[0]
                    queue_ids = results[2]
                    capacity = results[3]['capacity']

                    if member.id in queue_ids:  # Author already in queue
                        title = f'Unable to add **{name}**: Already in the queue'
                    elif len(queue_ids) >= capacity:  # Queue full
                        title = f'Unable to add **{name}**: Queue is full'
                    elif not player:  # ApiHelper couldn't get player
                        title = f'Unable to add **{name}**: Cannot verify match status'
                    elif player.in_match:  # member is already in a match
                        title = f'Unable to add **{name}**: They are already in a match'
                    else:  # member can be added
                        await self.bot.db_helper.insert_queued_users(member.guild.id, member.id)
                        queue_ids += [member.id]
                        title = f'**{name}** has been added to the queue'

                        # Check and burst queue if full
                        if len(queue_ids) == capacity:
                            queue_members = [member.guild.get_member(member_id) for member_id in queue_ids]
                            try:
                                all_readied = await match_cog.start_match(member, queue_members)
                            except asyncio.TimeoutError:
                                return

                            if all_readied:
                                await self.bot.db_helper.delete_queued_users(member.guild.id, *queue_ids)

                            return

                embed = await self.queue_embed(member.guild, title)
                # Delete last queue message
                await self.update_last_msg(member, embed)

        if before.channel is not None:
            if before.channel != voice_lobby or match_cog.moving_players:
                return
            else:
                awaitables = [
                    self.bot.db_helper.get_queued_users(member.guild.id),
                    self.bot.db_helper.get_guild(member.guild.id)
                ]
                results = await asyncio.gather(*awaitables, loop=self.bot.loop)
                queue_ids = results[0]
                capacity = results[1]['capacity']                             

                if len(queue_ids) == capacity:
                    if member.id in queue_ids:
                        if member.guild in match_cog.pending_ready_tasks:
                            match_cog.pending_ready_tasks[member.guild].close()
                            match_cog.pending_ready_tasks.pop(member.guild)
                        
                        if member.guild in match_cog.dict_ready_message:
                            await match_cog.dict_ready_message[member.guild].delete()
                        
                removed = await self.bot.db_helper.delete_queued_users(member.guild.id, member.id)

                if member.id in removed:
                    title = f'**{name}** has been removed from the queue'
                else:
                    title = f'**{name}** isn\'t in the queue'
                                  
                embed = await self.queue_embed(member.guild, title)
                # Update queue display message
                await self.update_last_msg(member, embed)

    @commands.command(usage='remove <member mention>',
                      brief='Remove the mentioned member from the queue (must have server kick perms)')
    @commands.has_permissions(kick_members=True)
    async def remove(self, ctx):
        """ Remove the specified member from the queue. """
        if not await self.bot.isValidChannel(ctx):
            return

        try:
            removee = ctx.message.mentions[0]
        except IndexError:
            embed = self.bot.embed_template(title='Mention a player in the command to remove them')
            await ctx.send(embed=embed)
        else:
            removed = await self.bot.db_helper.delete_queued_users(ctx.guild.id, removee.id)
            name = removee.nick if removee.nick is not None else removee.display_name

            if removee.id in removed:
                title = f'**{name}** has been removed from the queue'
            else:
                title = f'**{name}** is not in the queue'

            embed = await self.queue_embed(ctx.guild, title)

            channel_id = await self.bot.get_guild_data(ctx.guild, 'voice_lobby')
            voice_lobby = ctx.bot.get_channel(channel_id)
            if removee in voice_lobby.members:
                await removee.move_to(None)

            # Update queue display message
            await self.update_last_msg(ctx, embed)

    @commands.command(brief='Empty the queue (must have server kick perms)')
    @commands.has_permissions(kick_members=True)
    async def empty(self, ctx):
        """ Reset the guild queue list to empty. """
        if not await self.bot.isValidChannel(ctx):
            return

        await self.bot.db_helper.delete_all_queued_users(ctx.guild.id)
        embed = await self.queue_embed(ctx.guild, 'The queue has been emptied')

        channel_id = await self.bot.get_guild_data(ctx.guild, 'voice_lobby')
        voice_lobby = ctx.bot.get_channel(channel_id)
        for player in voice_lobby.members:
            await player.move_to(None)

        # Update queue display message
        await self.update_last_msg(ctx, embed)

    @remove.error
    @empty.error
    async def remove_error(self, ctx, error):
        """ Respond to a permissions error with an explanation message. """
        if isinstance(error, commands.MissingPermissions):
            await ctx.trigger_typing()
            missing_perm = error.missing_perms[0].replace('_', ' ')
            embed = self.bot.embed_template(title=f'Cannot remove players without {missing_perm} permission!')
            await ctx.send(embed=embed)

    @commands.command(usage='cap [new capacity]',
                      brief='Set the capacity of the queue (Must have admin perms)')
    @commands.has_permissions(administrator=True)
    async def cap(self, ctx, *args):
        """ Set the queue capacity. """
        if not await self.bot.isValidChannel(ctx):
            return

        capacity = await self.bot.get_guild_data(ctx.guild, 'capacity')

        if len(args) == 0:  # No size argument specified
            embed = self.bot.embed_template(title=f'The current queue capacity is {capacity}')
        else:
            new_cap = args[0]

            try:
                new_cap = int(new_cap)
            except ValueError:
                embed = self.bot.embed_template(title=f'{new_cap} is not an integer')
            else:
                if new_cap == capacity:
                    embed = self.bot.embed_template(title=f'Capacity is already set to {capacity}')
                elif new_cap < 2 or new_cap > 100:
                    embed = self.bot.embed_template(title='Capacity is outside of valid range (2-100)')
                else:
                    await self.bot.db_helper.delete_all_queued_users(ctx.guild.id)
                    await self.bot.db_helper.update_guild(ctx.guild.id, capacity=new_cap)
                    embed = self.bot.embed_template(title=f'Queue capacity set to {new_cap}')
                    embed.set_footer(text='The queue has been emptied because of the capacity change')

                    channel_id = await self.bot.get_guild_data(ctx.guild, 'voice_lobby')
                    voice_lobby = ctx.bot.get_channel(channel_id)
                    for player in voice_lobby.members:
                        await player.move_to(None)

                    await voice_lobby.edit(user_limit=new_cap)

        await ctx.send(embed=embed)

    @cap.error
    async def cap_error(self, ctx, error):
        """ Respond to a permissions error with an explanation message. """
        if isinstance(error, commands.MissingPermissions):
            await ctx.trigger_typing()
            missing_perm = error.missing_perms[0].replace('_', ' ')
            embed = self.bot.embed_template(title=f'Cannot change queue capacity without {missing_perm} permission!')
            await ctx.send(embed=embed)
