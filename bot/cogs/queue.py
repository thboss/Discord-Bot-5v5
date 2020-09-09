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
        self.before_member_channel = defaultdict(lambda: None)
        self.after_member_channel = defaultdict(lambda: None)
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

    async def update_last_msg(self, ctx, embed):
        """ Send embed message and delete the last one sent. """
        try:
            after_msg = self.last_queue_msgs.get(self.after_member_channel[ctx].category)
        except:
            after_msg = None

        try:
            after_text_id = await self.bot.get_league_data(self.after_member_channel[ctx].category, 'text_queue')
        except:
            after_text_id = None

        after_text_channel = ctx.guild.get_channel(after_text_id)

        if after_msg is None:
            self.last_queue_msgs[self.after_member_channel[ctx].category] = await after_text_channel.send(
                embed=embed)
        else:
            try:
                await after_msg.edit(embed=embed)
            except NotFound:
                self.last_queue_msgs[self.after_member_channel[ctx].category] = await after_text_channel.send(
                    embed=embed)

    async def _update_last_msg(self, ctx, embed):
        """ Send embed message and delete the last one sent. """

        try:
            before_msg = self.last_queue_msgs.get(self.before_member_channel[ctx].category)
        except:
            before_msg = None

        try:
            before_text_id = await self.bot.get_league_data(self.before_member_channel[ctx].category, 'text_queue')
        except:
            before_text_id = None

        before_text_channel = ctx.guild.get_channel(before_text_id)

        if before_msg is None:
            self.last_queue_msgs[self.before_member_channel[ctx].category] = await before_text_channel.send(
                embed=embed)
        else:
            try:
                await before_msg.edit(embed=embed)
            except NotFound:
                self.last_queue_msgs[self.before_member_channel[ctx].category] = await before_text_channel.send(
                    embed=embed)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if before.channel == after.channel:
            return

        self.before_member_channel[member] = before.channel
        self.after_member_channel[member] = after.channel

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

        match_cog = self.bot.get_cog('MatchCog')

        if after.channel == after_lobby is not None:

            if not await self.bot.api_helper.is_linked(member.id):  # Message author isn't linked
                title = self.bot.translate('account-not-linked').format(member.display_name)
            else:  # Message author is linked
                awaitables = [
                    self.bot.api_helper.get_player(member.id),
                    self.bot.db_helper.insert_users(member.id),
                    self.bot.db_helper.get_queued_users(after.channel.category_id),
                    self.bot.db_helper.get_league(after.channel.category_id)
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
                    await self.bot.db_helper.insert_queued_users(after.channel.category_id, member.id)
                    queue_ids += [member.id]
                    title = self.bot.translate('added-to-queue').format(member.display_name)

                    # Check and burst queue if full
                    if len(queue_ids) == capacity:
                        self.block_lobby[after.channel.category] = True
                        pug_role_id = await self.bot.get_league_data(after.channel.category, 'pug_role')
                        pug_role = member.guild.get_role(pug_role_id)
                        await after_lobby.set_permissions(pug_role, connect=False)
                        queue_members = [member.guild.get_member(member_id) for member_id in queue_ids]
                        all_readied = await match_cog.start_match(after.channel.category, queue_members)

                        if all_readied:
                            await self.bot.db_helper.delete_queued_users(before.channel.category_id, *queue_ids)

                        self.block_lobby[after.channel.category] = False
                        await after_lobby.set_permissions(pug_role, connect=True)
                        title = self.bot.translate('players-in-queue')
                        embed = await self.queue_embed(after.channel.category, title)
                        await self.update_last_msg(member, embed)
                        return

            embed = await self.queue_embed(after.channel.category, title)
            # Delete last queue message
            await self.update_last_msg(member, embed)

        if before.channel == before_lobby is not None:

            removed = await self.bot.db_helper.delete_queued_users(before.channel.category_id, member.id)

            if member.id in removed:
                title = self.bot.translate('removed-from-queue').format(member.display_name)
            else:
                title = self.bot.translate('not-in-queue').format(member.display_name)

            embed = await self.queue_embed(before.channel.category, title)
            # Update queue display message
            await self._update_last_msg(member, embed)

    @commands.command(brief='Check if account is linked and give linked role')
    async def check(self, ctx):
        if not await self.bot.isValidChannel(ctx):
            return

        if not await self.bot.api_helper.is_linked(ctx.author.id):
            msg = self.bot.translate('discord-not-linked').format(ctx.author.mention)
            embed = self.bot.embed_template(description=msg, color=self.bot.color)
            await ctx.send(embed=embed)
            return

        role_id = await self.bot.get_league_data(ctx.channel.category, 'pug_role')
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
            role_id = await self.bot.get_league_data(ctx.channel.category, 'alerts_role')
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
            await self.update_last_msg(ctx, embed)

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

        capacity = await self.bot.get_league_data(ctx.channel.category, 'capacity')

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
                    self.block_lobby[ctx.channel.category] = True
                    await self.bot.db_helper.delete_all_queued_users(ctx.channel.category_id)
                    await self.bot.db_helper.update_league(ctx.channel.category_id, capacity=new_cap)
                    embed = self.bot.embed_template(title=self.bot.translate('set-capacity').format(new_cap))
                    embed.set_footer(text=self.bot.translate('queue-emptied-footer'))

                    channel_id = await self.bot.get_league_data(ctx.channel.category, 'voice_lobby')
                    voice_lobby = ctx.bot.get_channel(channel_id)
                    for player in voice_lobby.members:
                        await player.move_to(None)

                    self.block_lobby[ctx.channel.category] = False
                    await voice_lobby.edit(user_limit=new_cap)

        await ctx.send(embed=embed)

    @commands.command(usage='lang <language key>',
                      brief='Set or display bot language (Must have admin perms)')
    @commands.has_permissions(administrator=True)
    async def lang(self, ctx, arg=None):
        """ Set or display bot language. """
        if not await self.bot.isValidChannel(ctx):
            return

        language = await self.bot.get_league_data(ctx.channel.category, 'language')
        valid_languages = self.bot.translations.keys()

        if arg is None:
            title = self.bot.translate('current-language').format(language)
        else:
            arg = arg.lower()

            if arg == language:
                title = self.bot.translate('language-already').format(language)
            elif arg in valid_languages:
                title = self.bot.translate('set-language').format(language)
                await self.bot.db_helper.update_league(ctx.channel.category_id, language=arg)
            else:
                title = self.bot.translate('valid-languages') + ', '.join(lang for lang in valid_languages)

        embed = self.bot.embed_template(title=title)
        await ctx.send(embed=embed)

    @commands.command(usage='create <league name>',
                      brief='Create league (Must have admin perms)')
    @commands.has_permissions(administrator=True)
    async def create(self, ctx, *args):
        args = ' '.join(arg for arg in args)

        if not len(args):
            msg = f'Invalid usage: q!create <league name>'
        else:
            category = await ctx.guild.create_category_channel(name=args)
            await self.bot.db_helper.insert_leagues(category.id)
            everyone_role = get(ctx.guild.roles, name='@everyone')
            pug_role = await ctx.guild.create_role(name=f'{args}_linked')
            alerts_role = await ctx.guild.create_role(name=f'{args}_alerts')
            text_channel_queue = await ctx.guild.create_text_channel(name=f'{args}_queue', category=category)
            text_channel_commands = await ctx.guild.create_text_channel(name=f'{args}_commands', category=category)
            text_channel_results = await ctx.guild.create_text_channel(name=f'{args}_results', category=category)
            voice_channel_lobby = await ctx.guild.create_voice_channel(name=f'{args}_lobby', category=category,
                                                                       user_limit=10)
            await self.bot.db_helper.update_league(category.id, pug_role=pug_role.id),
            await self.bot.db_helper.update_league(category.id, alerts_role=alerts_role.id),
            await self.bot.db_helper.update_league(category.id, text_queue=text_channel_queue.id),
            await self.bot.db_helper.update_league(category.id, text_commands=text_channel_commands.id),
            await self.bot.db_helper.update_league(category.id, text_results=text_channel_results.id),
            await self.bot.db_helper.update_league(category.id, voice_lobby=voice_channel_lobby.id),
            await text_channel_queue.set_permissions(everyone_role, send_messages=False),
            await text_channel_results.set_permissions(everyone_role, send_messages=False),
            await voice_channel_lobby.set_permissions(everyone_role, connect=False),
            await voice_channel_lobby.set_permissions(pug_role, connect=True)
            msg = f'Successfully created league: {args}'

        embed = self.bot.embed_template(title=msg)
        await ctx.send(embed=embed)

    @commands.command()
    async def delete(self, ctx):
        for channel in ctx.guild.channels:
            if channel.name != 'general':
                await channel.delete()

    @lang.error
    @cap.error
    @create.error
    async def cap_error(self, ctx, error):
        """ Respond to a permissions error with an explanation message. """
        if isinstance(error, commands.MissingPermissions):
            await ctx.trigger_typing()
            missing_perm = error.missing_perms[0].replace('_', ' ')
            embed = self.bot.embed_template(title=self.bot.translate('change-capacity-perm').format(missing_perm))
            await ctx.send(embed=embed)
