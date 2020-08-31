# queue.py

from discord.ext import commands
from discord.utils import get
from discord.errors import NotFound
from collections import defaultdict
import asyncio


class QueueCog(commands.Cog):
    """ Cog to manage queues of players among multiple servers. """

    def __init__(self, bot):
        """ Set attributes. """
        self.bot = bot
        self.last_queue_msgs = {}
        self.block_lobby = {}
        self.block_lobby = defaultdict(lambda: False, self.block_lobby)

    async def queue_embed(self, guild, title=None):
        """ Method to create the queue embed for a guild. """
        queued_ids = await self.bot.db_helper.get_queued_users(guild.id)
        capacity = await self.bot.get_guild_data(guild, 'capacity')
        profiles = [await self.bot.api_helper.get_player(member_id) for member_id in queued_ids]

        if title:
            title += f' ({len(queued_ids)}/{capacity})'

        if len(queued_ids) == 0:  # If there are no members in the queue
            queue_str = f'_{self.bot.translate("queue-is-empty")}_'
        else:  # members still in queue
            queue_str = ''.join(f'{num}. [{guild.get_member(member_id).display_name}]({profiles[num-1].league_profile})\n' for num, member_id in enumerate(queued_ids, start=1))

        embed = self.bot.embed_template(title=title, description=queue_str)
        embed.set_footer(text=self.bot.translate('receive-notification'))
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
                if len(msg.embeds) < 1:
                    await msg.delete()
                    self.last_queue_msgs[ctx.guild] = await ctx.guild.channels[index_channel].send(embed=embed)
                else:
                    await msg.edit(embed=embed)
            except NotFound:
                self.last_queue_msgs[ctx.guild] = await ctx.guild.channels[index_channel].send(embed=embed)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        vc_id = await self.bot.get_guild_data(member.guild, 'voice_lobby')
        voice_lobby = member.guild.get_channel(vc_id)
        if before.channel == voice_lobby and after.channel == voice_lobby:
            return

        match_cog = self.bot.get_cog('MatchCog')

        if after.channel is not None:
            if (after.channel != voice_lobby and before.channel != voice_lobby) or self.block_lobby[member.guild]:
                return

            if not await self.bot.api_helper.is_linked(member.id):  # Message author isn't linked
                title = self.bot.translate('account-not-linked').format(member.display_name)
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
                    title = self.bot.translate('already-in-queue').format(member.display_name)
                elif len(queue_ids) >= capacity:  # Queue full
                    title = self.bot.translate('queue-is-full').format(member.display_name)
                elif not player:  # ApiHelper couldn't get player
                    title = self.bot.translate('cannot-verify-match').format(member.display_name)
                elif player.in_match:  # member is already in a match
                    title = self.bot.translate('already-in-match').format(member.display_name)
                else:  # member can be added
                    await self.bot.db_helper.insert_queued_users(member.guild.id, member.id)
                    queue_ids += [member.id]
                    title = self.bot.translate('added-to-queue').format(member.display_name)

                    if capacity - len(queue_ids) == self.bot.int_remaining_alerts and self.bot.int_remaining_alerts != 0:
                        channel_id = await self.bot.get_guild_data(member.guild, 'text_queue')
                        text_channel = member.guild.get_channel(channel_id)
                        index_channel = member.guild.channels.index(text_channel)
                        alert_role_id = await self.bot.get_guild_data(member.guild, 'alerts_role')
                        alert_role = member.guild.get_role(alert_role_id)
                        await member.guild.channels[index_channel].send(f'{alert_role.mention} +{capacity - len(queue_ids)}')

                    # Check and burst queue if full
                    if len(queue_ids) == capacity:
                        self.block_lobby[member.guild] = True
                        pug_role_id = await self.bot.get_guild_data(member.guild, 'pug_role')
                        pug_role = member.guild.get_role(pug_role_id)
                        await voice_lobby.set_permissions(pug_role, connect=False)
                        queue_members = [member.guild.get_member(member_id) for member_id in queue_ids]
                        all_readied = await match_cog.start_match(member, queue_members)

                        if all_readied:
                            await self.bot.db_helper.delete_queued_users(member.guild.id, *queue_ids)

                        self.block_lobby[member.guild] = False
                        await voice_lobby.set_permissions(pug_role, connect=True)
                        title = self.bot.translate('players-in-queue')
                        embed = await self.queue_embed(member.guild, title)
                        await self.update_last_msg(member, embed) 
                        return

            embed = await self.queue_embed(member.guild, title)
            # Delete last queue message
            await self.update_last_msg(member, embed)

        if before.channel is not None:
            if before.channel != voice_lobby or self.block_lobby[member.guild]:
                return
                    
            removed = await self.bot.db_helper.delete_queued_users(member.guild.id, member.id)

            if member.id in removed:
                title = self.bot.translate('removed-from-queue').format(member.display_name)
            else:
                title = self.bot.translate('not-in-queue').format(member.display_name)
                                
            embed = await self.queue_embed(member.guild, title)
            # Update queue display message
            await self.update_last_msg(member, embed)

    @commands.command(brief='Check if account is linked and give linked role')
    async def check(self, ctx):
        if not await self.bot.isValidChannel(ctx):
            return

        if not await self.bot.api_helper.is_linked(ctx.author.id):
            msg = self.bot.translate('discord-not-linked').format(ctx.author.mention)
            embed = self.bot.embed_template(description=msg, color=self.bot.color)
            await ctx.send(embed=embed)
            return

        role_id = await self.bot.get_guild_data(ctx.guild, 'pug_role')
        role = ctx.guild.get_role(role_id)
        await ctx.author.add_roles(role)
        await self.bot.api_helper.update_discord_name(ctx.author)

        msg = self.bot.translate('discord-get-role').format(ctx.author.mention, role.mention)
        embed = self.bot.embed_template(description=msg, color=self.bot.color)
        await ctx.send(embed=embed)

    @commands.command(usage='alerts <on|off>',
                      brief='Send alerts about remaining to fill up the queue')
    async def alerts(self, ctx, *args):
        if not await self.bot.isValidChannel(ctx):
            return

        if len(args) == 0:
            msg = f'{self.bot.translate("invalid-usage")}: `{self.bot.command_prefix[0]}alerts <on|off>`'
        else:
            role_id = await self.bot.get_guild_data(ctx.guild, 'alerts_role')
            role = ctx.guild.get_role(role_id)

            if args[0].lower() == 'on':
                await ctx.author.add_roles(role)
                msg = self.bot.translate('added-alerts').format(ctx.author.display_name)
            elif args[0].lower() == 'off':
                await ctx.author.remove_roles(role)
                msg = self.bot.translate('removed-alerts').format(ctx.author.display_name)
            else:
                msg = f'{self.bot.translate("invalid-usage")}: `{self.bot.command_prefix[0]}alerts <on|off>`'

        embed = self.bot.embed_template(title=msg, color=self.bot.color)
        await ctx.send(embed=embed)            

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
            embed = self.bot.embed_template(title=self.bot.translate('mention-to-remove'))
            await ctx.send(embed=embed)
        else:
            removed = await self.bot.db_helper.delete_queued_users(ctx.guild.id, removee.id)

            if removee.id in removed:
                title = self.bot.translate('removed-from-queue').format(removee.display_name)
            else:
                title = self.bot.translate('removed-not-in-queue').format(removee.display_name)

            embed = await self.queue_embed(ctx.guild, title)

            channel_id = await self.bot.get_guild_data(ctx.guild, 'voice_lobby')
            voice_lobby = ctx.bot.get_channel(channel_id)
            if removee in voice_lobby.members:
                await removee.move_to(None)

            _embed = self.bot.embed_template(title=title)
            await ctx.send(embed=_embed)
            # Update queue display message
            await self.update_last_msg(ctx, embed)

    @commands.command(brief='Empty the queue (must have server kick perms)')
    @commands.has_permissions(kick_members=True)
    async def empty(self, ctx):
        """ Reset the guild queue list to empty. """
        if not await self.bot.isValidChannel(ctx):
            return

        self.block_lobby[ctx.guild] = True
        await self.bot.db_helper.delete_all_queued_users(ctx.guild.id)
        msg = self.bot.translate('queue-emptied')
        embed = await self.queue_embed(ctx.guild, msg)

        channel_id = await self.bot.get_guild_data(ctx.guild, 'voice_lobby')
        voice_lobby = ctx.bot.get_channel(channel_id)

        for player in voice_lobby.members:
            await player.move_to(None)

        self.block_lobby[ctx.guild] = False
        _embed = self.bot.embed_template(title=msg)
        await ctx.send(embed=_embed)
        # Update queue display message
        await self.update_last_msg(ctx, embed)

    @remove.error
    @empty.error
    async def remove_error(self, ctx, error):
        """ Respond to a permissions error with an explanation message. """
        if isinstance(error, commands.MissingPermissions):
            await ctx.trigger_typing()
            missing_perm = error.missing_perms[0].replace('_', ' ')
            embed = self.bot.embed_template(title=self.bot.translate('remove-perm').format(missing_perm))
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
            embed = self.bot.embed_template(title=self.bot.translate('current-capacity').format(capacity))
        else:
            new_cap = args[0]

            try:
                new_cap = int(new_cap)
            except ValueError:
                embed = self.bot.embed_template(title=self.bot.translate('capacity-not-integer').format(new_cap))
            else:
                if new_cap == capacity:
                    embed = self.bot.embed_template(title=self.bot.translate('capacity-already').format(capacity))
                elif new_cap < 2 or new_cap > 100:
                    embed = self.bot.embed_template(title=self.bot.translate('capacity-out-range'))
                else:
                    self.block_lobby[ctx.guild] = True
                    await self.bot.db_helper.delete_all_queued_users(ctx.guild.id)
                    await self.bot.db_helper.update_guild(ctx.guild.id, capacity=new_cap)
                    embed = self.bot.embed_template(title=self.bot.translate('set-capacity').format(new_cap))
                    embed.set_footer(text=self.bot.translate('queue-emptied-footer'))

                    channel_id = await self.bot.get_guild_data(ctx.guild, 'voice_lobby')
                    voice_lobby = ctx.bot.get_channel(channel_id)
                    for player in voice_lobby.members:
                        await player.move_to(None)

                    self.block_lobby[ctx.guild] = False
                    await voice_lobby.edit(user_limit=new_cap)

        await ctx.send(embed=embed)

    @cap.error
    async def cap_error(self, ctx, error):
        """ Respond to a permissions error with an explanation message. """
        if isinstance(error, commands.MissingPermissions):
            await ctx.trigger_typing()
            missing_perm = error.missing_perms[0].replace('_', ' ')
            embed = self.bot.embed_template(title=self.bot.translate('change-capacity-perm').format(missing_perm))
            await ctx.send(embed=embed)
