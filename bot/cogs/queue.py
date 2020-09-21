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

    async def queue_embed(self, category, title=None):
        """ Method to create the queue embed for a guild. """
        queued_ids = await self.bot.db_helper.get_queued_users(category.id)
        capacity = await self.bot.get_league_data(category, 'capacity')
        profiles = [await self.bot.api_helper.get_player(member_id) for member_id in queued_ids]

        if title:
            title += f' ({len(queued_ids)}/{capacity})'

        if len(queued_ids) == 0:  # If there are no members in the queue
            queue_str = f'_{self.bot.translate("queue-is-empty")}_'
        else:  # members still in queue
            queue_str = ''.join(
                f'{num}. [{category.guild.get_member(member_id).display_name}]({profiles[num - 1].league_profile})\n'
                for num, member_id in enumerate(queued_ids, start=1))

        embed = self.bot.embed_template(title=title, description=queue_str)
        embed.set_footer(text=self.bot.translate('receive-notification'))
        return embed

    async def update_last_msg(self, category, embed):
        """ Send embed message and delete the last one sent. """
        try:
            after_msg = self.last_queue_msgs.get(category)
        except:
            after_msg = None

        try:
            after_text_id = await self.bot.get_league_data(category, 'text_queue')
        except:
            after_text_id = None

        after_text_channel = category.guild.get_channel(after_text_id)

        if after_msg is None:
            self.last_queue_msgs[category] = await after_text_channel.send(
                embed=embed)
        else:
            try:
                await after_msg.edit(embed=embed)
            except NotFound:
                self.last_queue_msgs[category] = await after_text_channel.send(
                    embed=embed)

    async def _update_last_msg(self, category, embed):
        """ Send embed message and delete the last one sent. """

        try:
            before_msg = self.last_queue_msgs.get(category)
        except:
            before_msg = None

        try:
            before_text_id = await self.bot.get_league_data(category, 'text_queue')
        except:
            before_text_id = None

        before_text_channel = category.guild.get_channel(before_text_id)

        if before_msg is None:
            self.last_queue_msgs[category] = await before_text_channel.send(
                embed=embed)
        else:
            try:
                await before_msg.edit(embed=embed)
            except NotFound:
                self.last_queue_msgs[category] = await before_text_channel.send(
                    embed=embed)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if before.channel == after.channel:
            return

        try:
            after_id = await self.bot.get_league_data(after.channel.category, 'voice_lobby')
        except AttributeError:
            after_id = None

        try:
            before_id = await self.bot.get_league_data(before.channel.category, 'voice_lobby')
        except AttributeError:
            before_id = None

        before_lobby = member.guild.get_channel(before_id)
        after_lobby = member.guild.get_channel(after_id)

        if after.channel == after_lobby is not None:
            if self.block_lobby[after_lobby.category]:
                return

            if not await self.bot.api_helper.is_linked(member.id):  # Message author isn't linked
                title = self.bot.translate('account-not-linked').format(member.display_name)
            else:  # Message author is linked
                awaitables = [
                    self.bot.api_helper.get_player(member.id),
                    self.bot.db_helper.insert_users(member.id),
                    self.bot.db_helper.get_queued_users(after_lobby.category_id),
                    self.bot.db_helper.get_league(after_lobby.category_id)
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
                    await self.bot.db_helper.insert_queued_users(after_lobby.category_id, member.id)
                    queue_ids += [member.id]
                    title = self.bot.translate('added-to-queue').format(member.display_name)

                    # Check and burst queue if full
                    if len(queue_ids) == capacity:
                        self.block_lobby[after_lobby.category] = True
                        match_cog = self.bot.get_cog('MatchCog')
                        pug_role_id = await self.bot.get_league_data(after_lobby.category, 'pug_role')
                        pug_role = member.guild.get_role(pug_role_id)
                        await after_lobby.set_permissions(pug_role, connect=False)
                        queue_members = [member.guild.get_member(member_id) for member_id in queue_ids]
                        all_readied = await match_cog.start_match(after_lobby.category, queue_members)

                        if all_readied:
                            await self.bot.db_helper.delete_queued_users(after_lobby.category_id, *queue_ids)
   
                        self.block_lobby[after_lobby.category] = False
                        await after_lobby.set_permissions(pug_role, connect=True)
                        title = self.bot.translate('players-in-queue')
                        embed = await self.queue_embed(after_lobby.category, title)
                        await self.update_last_msg(after_lobby.category, embed)
                        return

            embed = await self.queue_embed(after_lobby.category, title)
            # Delete last queue message
            await self.update_last_msg(after_lobby.category, embed)

        if before.channel == before_lobby is not None:
            if self.block_lobby[before_lobby.category]:
                return

            removed = await self.bot.db_helper.delete_queued_users(before_lobby.category_id, member.id)

            if member.id in removed:
                title = self.bot.translate('removed-from-queue').format(member.display_name)
            else:
                title = self.bot.translate('not-in-queue').format(member.display_name)

            embed = await self.queue_embed(before_lobby.category, title)
            # Update queue display message
            await self._update_last_msg(before_lobby.category, embed)

    @commands.command(brief='Check if account is linked and give linked role')
    async def check(self, ctx):
        if not await self.bot.isValidChannel(ctx):
            return

        if not await self.bot.api_helper.is_linked(ctx.author.id):
            msg = self.bot.translate('discord-not-linked')
        else:
            role_id = await self.bot.get_league_data(ctx.channel.category, 'pug_role')
            role = ctx.guild.get_role(role_id)
            await ctx.author.add_roles(role)
            await self.bot.api_helper.update_discord_name(ctx.author)
            msg = self.bot.translate('discord-get-role')

        embed = self.bot.embed_template(description=msg, color=self.bot.color)
        await ctx.send(content=ctx.author.mention, embed=embed)

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
            removed = await self.bot.db_helper.delete_queued_users(ctx.channel.category_id, removee.id)

            if removee.id in removed:
                title = self.bot.translate('removed-from-queue').format(removee.display_name)
            else:
                title = self.bot.translate('removed-not-in-queue').format(removee.display_name)

            embed = await self.queue_embed(ctx.channel.category, title)

            channel_id = await self.bot.get_league_data(ctx.channel.category, 'voice_lobby')
            voice_lobby = ctx.bot.get_channel(channel_id)
            if removee in voice_lobby.members:
                await removee.move_to(None)

            _embed = self.bot.embed_template(title=title)
            await ctx.send(embed=_embed)
            # Update queue display message
            await self.update_last_msg(ctx.channel.category, embed)

    @commands.command(brief='Empty the queue (must have server kick perms)')
    @commands.has_permissions(kick_members=True)
    async def empty(self, ctx):
        """ Reset the guild queue list to empty. """
        if not await self.bot.isValidChannel(ctx):
            return
        self.block_lobby[ctx.channel.category] = True
        await self.bot.db_helper.delete_all_queued_users(ctx.channel.category.id)
        msg = self.bot.translate('queue-emptied')
        embed = await self.queue_embed(ctx.channel.category, msg)

        channel_id = await self.bot.get_league_data(ctx.channel.category, 'voice_lobby')
        voice_lobby = ctx.bot.get_channel(channel_id)

        for player in voice_lobby.members:
            await player.move_to(None)

        self.block_lobby[ctx.channel.category] = False
        _embed = self.bot.embed_template(title=msg)
        await ctx.send(embed=_embed)
        # Update queue display message
        await self.update_last_msg(ctx.channel.category, embed)

    @remove.error
    @empty.error
    async def remove_error(self, ctx, error):
        """ Respond to a permissions error with an explanation message. """
        if isinstance(error, commands.MissingPermissions):
            await ctx.trigger_typing()
            missing_perm = error.missing_perms[0].replace('_', ' ')
            embed = self.bot.embed_template(title=self.bot.translate('required-perm').format(missing_perm))
            await ctx.send(embed=embed)

    @commands.command(usage='cap [new capacity]',
                      brief='Set the capacity of the queue (Must have admin perms)')
    @commands.has_permissions(administrator=True)
    async def cap(self, ctx, *args):
        """ Set the queue capacity. """
        if not await self.bot.isValidChannel(ctx):
            return

        capacity = await self.bot.get_league_data(ctx.channel.category, 'capacity')

        try:
            new_cap = int(args[0])
        except (IndexError, ValueError):
            msg = f'{self.bot.translate("invalid-usage")}: `{self.bot.command_prefix[0]}cap <number>`'
        else:
            if new_cap == capacity:
                msg = self.bot.translate('capacity-already').format(capacity)
            elif new_cap < 2 or new_cap > 100:
                msg = self.bot.translate('capacity-out-range')
            else:
                self.block_lobby[ctx.channel.category] = True
                await self.bot.db_helper.delete_all_queued_users(ctx.channel.category_id)
                await self.bot.db_helper.update_league(ctx.channel.category_id, capacity=new_cap)
                embed = await self.queue_embed(ctx.channel.category, self.bot.translate('queue-emptied'))
                embed.set_footer(text=self.bot.translate('queue-emptied-footer'))
                await self.update_last_msg(ctx.channel.category, embed)
                msg = self.bot.translate('set-capacity').format(new_cap)

                channel_id = await self.bot.get_league_data(ctx.channel.category, 'voice_lobby')
                voice_lobby = ctx.bot.get_channel(channel_id)
                for player in voice_lobby.members:
                    await player.move_to(None)

                self.block_lobby[ctx.channel.category] = False
                await voice_lobby.edit(user_limit=new_cap)

        await ctx.send(embed=self.bot.embed_template(title=msg))

    @commands.command(usage='create <league name>',
                      brief='Create league (Must have admin perms)')
    @commands.has_permissions(administrator=True)
    async def create(self, ctx, *args):
        args = ' '.join(arg for arg in args)

        if not len(args):
            msg = f'{self.bot.translate("invalid-usage")}: `{self.bot.command_prefix[0]}create <League name>`'
        else:
            category = await ctx.guild.create_category_channel(name=args)
            await self.bot.db_helper.insert_leagues(category.id)
            everyone_role = get(ctx.guild.roles, name='@everyone')
            pug_role = await ctx.guild.create_role(name=f'{args}_linked')
            text_channel_queue = await ctx.guild.create_text_channel(name=f'{args}_queue', category=category)
            text_channel_commands = await ctx.guild.create_text_channel(name=f'{args}_commands', category=category)
            voice_channel_lobby = await ctx.guild.create_voice_channel(name=f'{args} Lobby', category=category,
                                                                       user_limit=10)
            voice_channel_prelobby = await ctx.guild.create_voice_channel(name=f'{args} Pre-Lobby', category=category)
            await self.bot.db_helper.update_league(category.id, pug_role=pug_role.id)
            await self.bot.db_helper.update_league(category.id, text_queue=text_channel_queue.id)
            await self.bot.db_helper.update_league(category.id, text_commands=text_channel_commands.id)
            await self.bot.db_helper.update_league(category.id, voice_lobby=voice_channel_lobby.id)
            await self.bot.db_helper.update_league(category.id, voice_prelobby=voice_channel_prelobby.id)
            await text_channel_queue.set_permissions(everyone_role, send_messages=False)
            await voice_channel_lobby.set_permissions(everyone_role, connect=False)
            await voice_channel_lobby.set_permissions(pug_role, connect=True)
            msg = self.bot.translate('create-league').format(args)

        embed = self.bot.embed_template(title=msg)
        await ctx.send(embed=embed)

    @commands.command(usage='delete',
                      brief='Delete league (Must have admin perms)')
    @commands.has_permissions(administrator=True)
    async def delete(self, ctx):
        if not await self.bot.isValidChannel(ctx):
            return

        pug_role_id = await self.bot.get_league_data(ctx.channel.category, 'pug_role')
        pug_role = ctx.guild.get_role(pug_role_id)
        try:
            await pug_role.delete()
        except NotFound:
            pass

        await self.bot.db_helper.delete_leagues(ctx.channel.category_id)
        for channel in ctx.channel.category.channels + [ctx.channel.category]:
            await channel.delete()

    @cap.error
    @create.error
    @delete.error
    async def cap_error(self, ctx, error):
        """ Respond to a permissions error with an explanation message. """
        if isinstance(error, commands.MissingPermissions):
            await ctx.trigger_typing()
            missing_perm = error.missing_perms[0].replace('_', ' ')
            embed = self.bot.embed_template(title=self.bot.translate('required-perm').format(missing_perm))
            await ctx.send(embed=embed)
