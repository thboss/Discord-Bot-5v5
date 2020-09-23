
# commands.py

from discord.ext import commands
from discord.utils import get
from discord.errors import NotFound

import bot.helpers.utils as utils


class CommandsCog(commands.Cog):
    """"""

    def __init__(self, bot):
        self.bot = bot
        self.match_cog = self.bot.get_cog('MatchCog')
        self.queue_cog = self.bot.get_cog('QueueCog')

    @commands.command(brief='Link a player on the backend')
    async def link(self, ctx):
        """ Link a player by sending them a link to sign in with steam on the backend. """
        if not await self.bot.isValidChannel(ctx):
            return

        is_linked = await self.bot.api_helper.is_linked(ctx.author.id)

        if is_linked:
            player = await self.bot.api_helper.get_player(ctx.author.id)
            title = self.bot.translate('already-linked').format(player.steam_profile)
        else:
            link = await self.bot.api_helper.generate_link_url(ctx.author.id)

            if link:
                # Send the author a DM containing this link
                try:
                    await ctx.author.send(self.bot.translate('dm-link').format(link))
                    title = self.bot.translate('link-sent')
                except:
                    title = self.bot.translate('blocked-dm')
            else:
                title = self.bot.translate('unknown-error')

        embed = self.bot.embed_template(description=title)
        await ctx.send(content=ctx.author.mention, embed=embed)

    @commands.command(brief='UnLink a player on the backend')
    async def unlink(self, ctx):
        """ Unlink a player by delete him on the backend. """
        if not await self.bot.isValidChannel(ctx):
            return

        is_linked = await self.bot.api_helper.is_linked(ctx.author.id)

        if not is_linked:
            title = self.bot.translate('already-not-linked')
        else:
            await self.bot.api_helper.unlink_discord(ctx.author)
            title = self.bot.translate('unlinked')
            role_id = await self.bot.get_league_data(ctx.channel.category, 'pug_role')
            role = ctx.guild.get_role(role_id)
            await ctx.author.remove_roles(role)

        embed = self.bot.embed_template(title=title)
        await ctx.send(content=ctx.author.mention, embed=embed)

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

            embed = await self.queue_cog.queue_embed(ctx.channel.category, title)

            lobby_id = await self.bot.get_league_data(ctx.channel.category, 'voice_lobby')
            prelobby_id = await self.bot.get_league_data(ctx.channel.category, 'voice_prelobby')
            lobby = ctx.bot.get_channel(lobby_id)
            prelobby = ctx.bot.get_channel(prelobby_id)

            if removee in lobby.members:
                await removee.move_to(prelobby)

            _embed = self.bot.embed_template(title=title)
            await ctx.send(embed=_embed)
            # Update queue display message
            await self.queue_cog.update_last_msg(ctx.channel.category, embed)

    @commands.command(brief='Empty the queue (must have server kick perms)')
    @commands.has_permissions(kick_members=True)
    async def empty(self, ctx):
        """ Reset the league queue list to empty. """
        if not await self.bot.isValidChannel(ctx):
            return

        self.queue_cog.block_lobby[ctx.channel.category] = True
        await self.bot.db_helper.delete_all_queued_users(ctx.channel.category.id)
        msg = self.bot.translate('queue-emptied')
        embed = await self.queue_cog.queue_embed(ctx.channel.category, msg)

        lobby_id = await self.bot.get_league_data(ctx.channel.category, 'voice_lobby')
        prelobby_id = await self.bot.get_league_data(ctx.channel.category, 'voice_prelobby')
        lobby = ctx.bot.get_channel(lobby_id)
        prelobby = ctx.bot.get_channel(prelobby_id)

        for player in lobby.members:
            await player.move_to(prelobby)

        self.queue_cog.block_lobby[ctx.channel.category] = False
        _embed = self.bot.embed_template(title=msg)
        await ctx.send(embed=_embed)
        # Update queue display message
        await self.queue_cog.update_last_msg(ctx.channel.category, embed)

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
                self.queue_cog.block_lobby[ctx.channel.category] = True
                await self.bot.db_helper.delete_all_queued_users(ctx.channel.category_id)
                await self.bot.db_helper.update_league(ctx.channel.category_id, capacity=new_cap)
                embed = await self.queue_cog.queue_embed(ctx.channel.category, self.bot.translate('queue-emptied'))
                embed.set_footer(text=self.bot.translate('queue-emptied-footer'))
                await self.queue_cog.update_last_msg(ctx.channel.category, embed)
                msg = self.bot.translate('set-capacity').format(new_cap)

                lobby_id = await self.bot.get_league_data(ctx.channel.category, 'voice_lobby')
                prelobby_id = await self.bot.get_league_data(ctx.channel.category, 'voice_prelobby')
                lobby = ctx.bot.get_channel(lobby_id)
                prelobby = ctx.bot.get_channel(prelobby_id)
                
                for player in lobby.members:
                    await player.move_to(prelobby)

                self.queue_cog.block_lobby[ctx.channel.category] = False
                await lobby.edit(user_limit=new_cap)

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

    @commands.command(usage='teams {captains|autobalance|random}',
                      brief='Set or view the team creation method (Must have admin perms)')
    @commands.has_permissions(administrator=True)
    async def teams(self, ctx, method=None):
        """ Set or display the method by which teams are created. """
        if not await self.bot.isValidChannel(ctx):
            return

        team_method = await self.bot.get_league_data(ctx.channel.category, 'team_method')
        valid_methods = ['captains', 'autobalance', 'random']

        if method is None:
            title = self.bot.translate('team-method').format(team_method)
        else:
            method = method.lower()

            if method == team_method:
                title = self.bot.translate('team-method-already').format(team_method)
            elif method in valid_methods:
                title = self.bot.translate('set-team-method').format(method)
                await self.bot.db_helper.update_league(ctx.channel.category_id, team_method=method)
            else:
                title = self.bot.translate('team-valid-methods').format(valid_methods[0], valid_methods[1],
                                                                        valid_methods[2])

        embed = self.bot.embed_template(title=title)
        await ctx.send(embed=embed)

    @commands.command(usage='captains {volunteer|rank|random}',
                      brief='Set or view the captain selection method (Must have admin perms)')
    @commands.has_permissions(administrator=True)
    async def captains(self, ctx, method=None):
        """ Set or display the method by which captains are selected. """
        if not await self.bot.isValidChannel(ctx):
            return

        guild_data = await self.bot.db_helper.get_league(ctx.channel.category_id)
        captain_method = guild_data['captain_method']
        valid_methods = ['volunteer', 'rank', 'random']

        if method is None:
            title = self.bot.translate('captains-method').format(captain_method)
        else:
            method = method.lower()

            if method == captain_method:
                title = self.bot.translate('captains-method-already').format(captain_method)
            elif method in valid_methods:
                title = self.bot.translate('set-captains-method').format(method)
                await self.bot.db_helper.update_league(ctx.channel.category_id, captain_method=method)
            else:
                title = self.bot.translate('captains-valid-method').format(valid_methods[0], valid_methods[1],
                                                                           valid_methods[2])

        embed = self.bot.embed_template(title=title)
        await ctx.send(embed=embed)

    @commands.command(usage='maps [{captains|vote|random}]',
                      brief='Set or view the map selection method (must have admin perms)')
    @commands.has_permissions(administrator=True)
    async def maps(self, ctx, method=None):
        """ Set or display the method by which the teams are created. """
        if not await self.bot.isValidChannel(ctx):
            return

        map_method = await self.bot.get_league_data(ctx.channel.category, 'map_method')
        valid_methods = ['captains', 'vote', 'random']

        if method is None:
            title = self.bot.translate('map-method').format(map_method)
        else:
            method = method.lower()

            if method == map_method:
                title = self.bot.translate('map-method-already').format(map_method)
            elif method in valid_methods:
                title = self.bot.translate('set-map-method').format(method)
                await self.bot.db_helper.update_league(ctx.channel.category_id, map_method=method)
            else:
                title = self.bot.translate('map-valid-method').format(valid_methods[0], valid_methods[1],
                                                                      valid_methods[2])

        embed = self.bot.embed_template(title=title)
        await ctx.send(embed=embed)

    @commands.command(usage='mpool {+|-}<map name> ...',
                      brief='Add or remove maps from the map pool (must have admin perms)')
    @commands.has_permissions(administrator=True)
    async def mpool(self, ctx, *args):
        """ Edit the guild's map pool for map drafts. """
        if not await self.bot.isValidChannel(ctx):
            return

        map_pool = [m.dev_name for m in self.bot.all_maps if await self.bot.get_league_data(ctx.channel.category, m.dev_name)]

        if len(args) == 0:
            embed = self.bot.embed_template(title=self.bot.translate('map-pool'))
        else:
            description = ''
            any_wrong_arg = False  # Indicates if the command was used correctly

            for arg in args:
                map_name = arg[1:]  # Remove +/- prefix
                map_obj = next((m for m in self.bot.all_maps if m.dev_name == map_name), None)

                if map_obj is None:
                    description += '\u2022 ' + self.bot.translate('could-not-interpret').format(arg)
                    any_wrong_arg = True
                    continue

                if arg.startswith('+'):  # Add map
                    if map_name not in map_pool:
                        map_pool.append(map_name)
                        description += '\u2022 ' + self.bot.translate('added-map').format(map_name)
                elif arg.startswith('-'):  # Remove map
                    if map_name in map_pool:
                        map_pool.remove(map_name)
                        description += '\u2022 ' + self.bot.translate('removed-map').format(map_name)

            if len(map_pool) < 3:
                description = self.bot.translate('map-pool-fewer-3')
            else:
                map_pool_data = {m.dev_name: m.dev_name in map_pool for m in self.bot.all_maps}
                await self.bot.db_helper.update_league(ctx.channel.category_id, **map_pool_data)

            embed = self.bot.embed_template(title=self.bot.translate('modified-map-pool'), description=description)

            if any_wrong_arg:  # Add example usage footer if command was used incorrectly
                embed.set_footer(text=f'Ex: {self.bot.command_prefix[0]}mpool +de_cache -de_mirage')

        active_maps = ''.join(f'{m.emoji}  `{m.dev_name}`\n' for m in self.bot.all_maps if m.dev_name in map_pool)
        inactive_maps = ''.join(f'{m.emoji}  `{m.dev_name}`\n' for m in self.bot.all_maps if m.dev_name not in map_pool)

        if not inactive_maps:
            inactive_maps = f'*{self.bot.translate("none")}*'

        embed.add_field(name=f'__{self.bot.translate("active-maps")}__', value=active_maps)
        embed.add_field(name=f'__{self.bot.translate("inactive-maps")}__', value=inactive_maps)
        await ctx.send(embed=embed)

    @commands.command(usage='end [match id]',
                      brief='Force end a match (must have admin perms)')
    @commands.has_permissions(administrator=True)
    async def end(self, ctx, *args):
        """ Force end a match. """
        if not await self.bot.isValidChannel(ctx):
            return

        if len(args) == 0:
            msg = f'{self.bot.translate("invalid-usage")}: `{self.bot.command_prefix[0]}end <Match ID>`'
        else:
            try:
                if args[0] in self.match_cog.match_dict[ctx.channel.category] and await self.bot.api_helper.end_match(args[0]):
                    msg = self.bot.translate("match-cancelled").format(args[0])
                else:
                    msg = self.bot.translate("invalid-match-id")
            except KeyError:
                msg = self.bot.translate("invalid-match-id")

        embed = self.bot.embed_template(title=msg)
        await ctx.send(embed=embed)

    @teams.error
    @captains.error
    @maps.error
    @end.error
    async def config_error(self, ctx, error):
        """ Respond to a permissions error with an explanation message. """
        if isinstance(error, commands.MissingPermissions):
            await ctx.trigger_typing()
            missing_perm = error.missing_perms[0].replace('_', ' ')
            title = self.bot.translate('cannot-set').format(ctx.command.name, missing_perm)
            embed = self.bot.embed_template(title=title)
            await ctx.send(embed=embed)

    @commands.command(brief='See your stats')
    async def stats(self, ctx):
        """ Send an embed containing stats data parsed from the player object returned from the API. """
        if not await self.bot.isValidChannel(ctx):
            return

        user = ctx.author
        player = await self.bot.api_helper.get_player(user.id)

        if player:
            win_percent_str = f'{player.win_percent * 100:.2f}%'
            hs_percent_str = f'{player.hs_percent * 100:.2f}%'
            fb_percent_str = f'{player.first_blood_rate * 100:.2f}%'
            description = '```ml\n' \
                          f' {self.bot.translate("rank-score")}:      {player.score:>6} \n' \
                          f' {self.bot.translate("matches-played")}:    {player.matches_played:>6} \n' \
                          f' {self.bot.translate("win-percentage")}:    {win_percent_str:>6} \n' \
                          f' {self.bot.translate("kd-ratio")}:          {player.kd_ratio:>6.2f} \n' \
                          f' {self.bot.translate("adr")}:               {player.adr:>6.2f} \n' \
                          f' {self.bot.translate("hs-percentage")}:     {hs_percent_str:>6} \n' \
                          f' {self.bot.translate("first-blood-rate")}:  {fb_percent_str:>6} ' \
                          '```'
            embed = self.bot.embed_template(description=description)
            embed.set_author(name=user.display_name, url=player.league_profile, icon_url=user.avatar_url_as(size=128))
        else:
            title = self.bot.translate("cannot-get-stats").format(ctx.author.display_name)
            embed = self.bot.embed_template(title=title)

        await ctx.send(embed=embed)

    @commands.command(brief='See the top players in the server')
    async def leaders(self, ctx):
        """ Send an embed containing the leaderboard data parsed from the player objects returned from the API. """
        if not await self.bot.isValidChannel(ctx):
            return

        num = 5  # Easily modfiy the number of players on the leaderboard
        guild_players = await self.bot.api_helper.get_players([user.id for user in ctx.guild.members])

        if len(guild_players) == 0:
            embed = self.bot.embed_template(title=self.bot.translate("nobody-ranked"))
            await ctx.send(embed=embed)

        guild_players.sort(key=lambda u: (u.score, u.matches_played), reverse=True)

        # Select the top players only
        if len(guild_players) > num:
            guild_players = guild_players[:num]

        # Generate leaderboard text
        data = [['Player'] + [ctx.guild.get_member(player.discord).display_name for player in guild_players],
                ['Score'] + [str(player.score) for player in guild_players],
                ['Winrate'] + [f'{player.win_percent * 100:.2f}%' for player in guild_players],
                ['Played'] + [str(player.matches_played) for player in guild_players]]
        data[0] = [name if len(name) < 12 else name[:9] + '...' for name in data[0]]  # Shorten long names
        widths = list(map(lambda x: len(max(x, key=len)), data))
        aligns = ['left', 'right', 'right', 'right']
        z = zip(data, widths, aligns)
        formatted_data = [list(map(lambda x: utils.align_text(x, width, align), col)) for col, width, align in z]
        formatted_data = list(map(list, zip(*formatted_data)))  # Transpose list for .format() string
        description = '```ml\n    {}  {}  {}  {} \n'.format(*formatted_data[0])

        for rank, player_row in enumerate(formatted_data[1:], start=1):
            description += ' {}. {}  {}  {}  {} \n'.format(rank, *player_row)

        description += '```'

        # Send leaderboard
        title = f'__{self.bot.translate("server-leaderboard")}__'
        embed = self.bot.embed_template(title=title, description=description)
        await ctx.send(embed=embed)
