# commands.py

from discord.ext import commands
from discord.utils import get
from discord.errors import NotFound

from bot.helpers.utils import align_text, translate


class CommandsCog(commands.Cog):
    """"""

    def __init__(self, bot):
        self.bot = bot
        self.match_cog = self.bot.get_cog('MatchCog')
        self.queue_cog = self.bot.get_cog('QueueCog')

    @commands.command(usage='create <league name>',
                      brief=translate('command-create-brief'))
    @commands.has_permissions(administrator=True)
    async def create(self, ctx, *args):
        args = ' '.join(arg for arg in args)

        if not len(args):
            msg = f'{translate("invalid-usage")}: `{self.bot.command_prefix[0]}create <League name>`'
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
            msg = translate('create-league').format(args)

        embed = self.bot.embed_template(title=msg)
        await ctx.send(embed=embed)

    @commands.command(brief=translate('command-delete-brief'))
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

    @commands.command(brief=translate('command-link-brief'))
    async def link(self, ctx):
        """ Link a player by sending them a link to sign in with steam on the backend. """
        if not await self.bot.isValidChannel(ctx):
            return

        is_linked = await self.bot.api_helper.is_linked(ctx.author.id)

        if is_linked:
            player = await self.bot.api_helper.get_player(ctx.author.id)
            title = translate('already-linked', player.steam_profile)
        else:
            link = await self.bot.api_helper.generate_link_url(ctx.author.id)

            if link:
                # Send the author a DM containing this link
                try:
                    await ctx.author.send(translate('dm-link', link))
                    title = translate('link-sent')
                except:
                    title = translate('blocked-dm')
            else:
                title = translate('unknown-error')

        embed = self.bot.embed_template(description=title)
        await ctx.send(content=ctx.author.mention, embed=embed)

    @commands.command(usage='forcelink <mention> <Steam64 ID>',
                      brief=translate('command-forcelink-brief'))
    @commands.has_permissions(administrator=True)
    async def forcelink(self, ctx, *args):
        """ Force link player with steam on the backend. """
        if not await self.bot.isValidChannel(ctx):
            return
        print(int(args[1]), type(int(args[1])))
        try:
            user = ctx.message.mentions[0]
        except IndexError:
            title = f"{translate('invalid-usage')}: `{self.bot.command_prefix[0]}forcelink <mention> <Steam64 ID>`"
        else:
            link = await self.bot.api_helper.force_link_discord(user.id, args[1])

            if not link:
                title = 'Sorry! Steam ID is already linked with another discord'
            else:
                title = translate('force-linked', user.display_name, args[1])
                role_id = await self.bot.get_league_data(ctx.channel.category, 'pug_role')
                role = ctx.guild.get_role(role_id)
                await user.add_roles(role)
                await self.bot.api_helper.update_discord_name(user)

        embed = self.bot.embed_template(title=title)
        await ctx.send(embed=embed)

    @commands.command(usage='unlink <mention>',
                      brief=translate('command-unlink-brief'))
    @commands.has_permissions(administrator=True)
    async def unlink(self, ctx):
        """ Unlink a player by delete him on the backend. """
        if not await self.bot.isValidChannel(ctx):
            return

        try:
            user = ctx.message.mentions[0]
        except IndexError:
            title = f"{translate('invalid-usage')}: `{self.bot.command_prefix[0]}unlink <mention>`"
        else:
            linked = await self.bot.api_helper.is_linked(user.id)

            if not linked:
                title = translate('already-not-linked')
            else:
                await self.bot.api_helper.unlink_discord(user)
                title = translate('unlinked')
                role_id = await self.bot.get_league_data(ctx.channel.category, 'pug_role')
                role = ctx.guild.get_role(role_id)
                await user.remove_roles(role)

        embed = self.bot.embed_template(title=title)
        await ctx.send(embed=embed)

    @commands.command(brief=translate('command-check-brief'))
    async def check(self, ctx):
        if not await self.bot.isValidChannel(ctx):
            return

        if not await self.bot.api_helper.is_linked(ctx.author.id):
            msg = translate('discord-not-linked')
        else:
            role_id = await self.bot.get_league_data(ctx.channel.category, 'pug_role')
            role = ctx.guild.get_role(role_id)
            await ctx.author.add_roles(role)
            await self.bot.api_helper.update_discord_name(ctx.author)
            msg = translate('discord-get-role')

        embed = self.bot.embed_template(description=msg, color=self.bot.color)
        await ctx.send(content=ctx.author.mention, embed=embed)

    @commands.command(usage='remove <member mention>',
                      brief=translate('command-remove-brief'))
    @commands.has_permissions(kick_members=True)
    async def remove(self, ctx):
        """ Remove the specified member from the queue. """
        if not await self.bot.isValidChannel(ctx):
            return

        try:
            removee = ctx.message.mentions[0]
        except IndexError:
            embed = self.bot.embed_template(title=translate('mention-to-remove'))
            await ctx.send(embed=embed)
        else:
            removed = await self.bot.db_helper.delete_queued_users(ctx.channel.category_id, removee.id)

            if removee.id in removed:
                title = translate('removed-from-queue', removee.display_name)
            else:
                title = translate('removed-not-in-queue', removee.display_name)

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

    @commands.command(brief=translate('command-empty-brief'))
    @commands.has_permissions(kick_members=True)
    async def empty(self, ctx):
        """ Reset the league queue list to empty. """
        if not await self.bot.isValidChannel(ctx):
            return

        self.queue_cog.block_lobby[ctx.channel.category] = True
        await self.bot.db_helper.delete_all_queued_users(ctx.channel.category.id)
        msg = translate('queue-emptied')
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

    @commands.command(usage='cap [new capacity]',
                      brief=translate('command-cap-brief'))
    @commands.has_permissions(administrator=True)
    async def cap(self, ctx, *args):
        """ Set the queue capacity. """
        if not await self.bot.isValidChannel(ctx):
            return

        capacity = await self.bot.get_league_data(ctx.channel.category, 'capacity')

        try:
            new_cap = int(args[0])
        except (IndexError, ValueError):
            msg = f'{translate("invalid-usage")}: `{self.bot.command_prefix[0]}cap <number>`'
        else:
            if new_cap == capacity:
                msg = translate('capacity-already', capacity)
            elif new_cap < 2 or new_cap > 100:
                msg = translate('capacity-out-range')
            else:
                self.queue_cog.block_lobby[ctx.channel.category] = True
                await self.bot.db_helper.delete_all_queued_users(ctx.channel.category_id)
                await self.bot.db_helper.update_league(ctx.channel.category_id, capacity=new_cap)
                embed = await self.queue_cog.queue_embed(ctx.channel.category, translate('queue-emptied'))
                embed.set_footer(text=translate('queue-emptied-footer'))
                await self.queue_cog.update_last_msg(ctx.channel.category, embed)
                msg = translate('set-capacity', new_cap)

                lobby_id = await self.bot.get_league_data(ctx.channel.category, 'voice_lobby')
                prelobby_id = await self.bot.get_league_data(ctx.channel.category, 'voice_prelobby')
                lobby = ctx.bot.get_channel(lobby_id)
                prelobby = ctx.bot.get_channel(prelobby_id)

                for player in lobby.members:
                    await player.move_to(prelobby)

                self.queue_cog.block_lobby[ctx.channel.category] = False
                await lobby.edit(user_limit=new_cap)

        await ctx.send(embed=self.bot.embed_template(title=msg))

    @commands.command(usage='spectators', brief=translate('command-spectators-brief'))
    async def spectators(self, ctx):
        """ View the spectators. """
        if not await self.bot.isValidChannel(ctx):
            return

        spect_ids = await self.bot.db_helper.get_spect_users(ctx.channel.category_id)

        spect_members = [ctx.guild.get_member(spect_id) for spect_id in spect_ids]

        embed = self.bot.embed_template()
        embed.add_field(name=f'__Spectators__',
                        value='No spectators' if not spect_members else ''.join(
                            f'{num}. {member.mention}\n' for num, member in enumerate(spect_members, start=1)))
        await ctx.send(embed=embed)

    @commands.command(usage='addspect <mention>',
                      brief=translate('command-addspect-brief'))
    @commands.has_permissions(administrator=True)
    async def addspect(self, ctx):
        """ Add the specified member to the spectators. """
        if not await self.bot.isValidChannel(ctx):
            return

        try:
            spectator = ctx.message.mentions[0]
        except IndexError:
            title = f'{translate("invalid-usage")}: `{self.bot.command_prefix[0]}addspect <mention>`'
        else:
            await self.bot.db_helper.delete_queued_users(ctx.channel.category_id, spectator.id)

            if spectator.id not in await self.bot.db_helper.get_spect_users(ctx.channel.category_id):
                await self.bot.db_helper.insert_spect_users(ctx.channel.category_id, spectator.id)
                title = f'{translate("added-spect", spectator.display_name)}'
            else:
                title = f'{translate("already-spect", spectator.display_name)}'

        embed = self.bot.embed_template(title=title)
        await ctx.send(embed=embed)

    @commands.command(usage='removespect <mention>',
                      brief=translate('command-removespect-brief'))
    @commands.has_permissions(administrator=True)
    async def removespect(self, ctx):
        """ Remove the specified member from the spectators. """
        if not await self.bot.isValidChannel(ctx):
            return

        try:
            spectator = ctx.message.mentions[0]
        except IndexError:
            title = f'{translate("invalid-usage")}: `{self.bot.command_prefix[0]}removespect <mention>`'
        else:
            await self.bot.db_helper.delete_queued_users(ctx.channel.category_id, spectator.id)

            if spectator.id in await self.bot.db_helper.get_spect_users(ctx.channel.category_id):
                await self.bot.db_helper.delete_spect_users(ctx.channel.category_id, spectator.id)
                title = f'{translate("removed-spect", spectator.display_name)}'
            else:
                title = f'{translate("not-in-spect", spectator.display_name)}'

        embed = self.bot.embed_template(title=title)
        await ctx.send(embed=embed)

    @commands.command(usage='teams {captains|autobalance|random}',
                      brief=translate('command-teams-brief'))
    @commands.has_permissions(administrator=True)
    async def teams(self, ctx, method=None):
        """ Set or display the method by which teams are created. """
        if not await self.bot.isValidChannel(ctx):
            return

        team_method = await self.bot.get_league_data(ctx.channel.category, 'team_method')
        valid_methods = ['captains', 'autobalance', 'random']

        if method is None:
            title = translate('team-method', team_method)
        else:
            method = method.lower()

            if method == team_method:
                title = translate('team-method-already', team_method)
            elif method in valid_methods:
                title = translate('set-team-method', method)
                await self.bot.db_helper.update_league(ctx.channel.category_id, team_method=method)
            else:
                title = translate('team-valid-methods', valid_methods[0], valid_methods[1], valid_methods[2])

        embed = self.bot.embed_template(title=title)
        await ctx.send(embed=embed)

    @commands.command(usage='captains {volunteer|rank|random}',
                      brief=translate('command-captains-brief'))
    @commands.has_permissions(administrator=True)
    async def captains(self, ctx, method=None):
        """ Set or display the method by which captains are selected. """
        if not await self.bot.isValidChannel(ctx):
            return

        guild_data = await self.bot.db_helper.get_league(ctx.channel.category_id)
        captain_method = guild_data['captain_method']
        valid_methods = ['volunteer', 'rank', 'random']

        if method is None:
            title = translate('captains-method', captain_method)
        else:
            method = method.lower()

            if method == captain_method:
                title = translate('captains-method-already', captain_method)
            elif method in valid_methods:
                title = translate('set-captains-method', method)
                await self.bot.db_helper.update_league(ctx.channel.category_id, captain_method=method)
            else:
                title = translate('captains-valid-method', valid_methods[0], valid_methods[1], valid_methods[2])

        embed = self.bot.embed_template(title=title)
        await ctx.send(embed=embed)

    @commands.command(usage='maps [{captains|vote|random}]',
                      brief=translate('command-maps-brief'))
    @commands.has_permissions(administrator=True)
    async def maps(self, ctx, method=None):
        """ Set or display the method by which the teams are created. """
        if not await self.bot.isValidChannel(ctx):
            return

        map_method = await self.bot.get_league_data(ctx.channel.category, 'map_method')
        valid_methods = ['captains', 'vote', 'random']

        if method is None:
            title = translate('map-method', map_method)
        else:
            method = method.lower()

            if method == map_method:
                title = translate('map-method-already', map_method)
            elif method in valid_methods:
                title = translate('set-map-method', method)
                await self.bot.db_helper.update_league(ctx.channel.category_id, map_method=method)
            else:
                title = translate('map-valid-method', valid_methods[0], valid_methods[1], valid_methods[2])

        embed = self.bot.embed_template(title=title)
        await ctx.send(embed=embed)

    @commands.command(usage='mpool {+|-}<map name> ...',
                      brief=translate('command-mpool-brief'))
    @commands.has_permissions(administrator=True)
    async def mpool(self, ctx, *args):
        """ Edit the guild's map pool for map drafts. """
        if not await self.bot.isValidChannel(ctx):
            return

        map_pool = [m.dev_name for m in self.bot.all_maps if
                    await self.bot.get_league_data(ctx.channel.category, m.dev_name)]

        if len(args) == 0:
            embed = self.bot.embed_template(title=translate('map-pool'))
        else:
            description = ''
            any_wrong_arg = False  # Indicates if the command was used correctly

            for arg in args:
                map_name = arg[1:]  # Remove +/- prefix
                map_obj = next((m for m in self.bot.all_maps if m.dev_name == map_name), None)

                if map_obj is None:
                    description += '\u2022 ' + translate('could-not-interpret', arg)
                    any_wrong_arg = True
                    continue

                if arg.startswith('+'):  # Add map
                    if map_name not in map_pool:
                        map_pool.append(map_name)
                        description += '\u2022 ' + translate('added-map', map_name)
                elif arg.startswith('-'):  # Remove map
                    if map_name in map_pool:
                        map_pool.remove(map_name)
                        description += '\u2022 ' + translate('removed-map', map_name)

            if len(map_pool) < 3:
                description = translate('map-pool-fewer-3')
            else:
                map_pool_data = {m.dev_name: m.dev_name in map_pool for m in self.bot.all_maps}
                await self.bot.db_helper.update_league(ctx.channel.category_id, **map_pool_data)

            embed = self.bot.embed_template(title=translate('modified-map-pool'), description=description)

            if any_wrong_arg:  # Add example usage footer if command was used incorrectly
                embed.set_footer(text=f'Ex: {self.bot.command_prefix[0]}mpool +de_cache -de_mirage')

        active_maps = ''.join(f'{m.emoji}  `{m.dev_name}`\n' for m in self.bot.all_maps if m.dev_name in map_pool)
        inactive_maps = ''.join(f'{m.emoji}  `{m.dev_name}`\n' for m in self.bot.all_maps if m.dev_name not in map_pool)

        if not inactive_maps:
            inactive_maps = f'*{translate("none")}*'

        embed.add_field(name=f'__{translate("active-maps")}__', value=active_maps)
        embed.add_field(name=f'__{translate("inactive-maps")}__', value=inactive_maps)
        await ctx.send(embed=embed)

    @commands.command(usage='end [match id]',
                      brief=translate('command-end-brief'))
    @commands.has_permissions(administrator=True)
    async def end(self, ctx, *args):
        """ Force end a match. """
        if not await self.bot.isValidChannel(ctx):
            return

        if len(args) == 0:
            msg = f'{translate("invalid-usage")}: `{self.bot.command_prefix[0]}end <Match ID>`'
        else:
            matches = await self.bot.api_helper.matches_status()
            if args[0] in matches:
                if await self.bot.api_helper.end_match(args[0]):
                    msg = translate("match-cancelled", args[0])
                else:
                    msg = translate('match-already-over', args[0])
            else:
                msg = translate("invalid-match-id")

        embed = self.bot.embed_template(title=msg)
        await ctx.send(embed=embed)

    @commands.command(brief=translate('command-stats-brief'))
    async def stats(self, ctx):
        """ Send an embed containing stats data parsed from the player object returned from the API. """
        if not await self.bot.isValidChannel(ctx):
            return

        try:
            user = ctx.message.mentions[0]
        except IndexError:
            user = ctx.author

        player = await self.bot.api_helper.get_player(user.id)

        if player:
            win_percent_str = f'{player.win_percent * 100:.2f}%'
            hs_percent_str = f'{player.hs_percent * 100:.2f}%'
            fb_percent_str = f'{player.first_blood_rate * 100:.2f}%'
            description = '```ml\n' \
                          f' {translate("rank-score")}:      {player.score:>6} \n' \
                          f' {translate("matches-played")}:    {player.matches_played:>6} \n' \
                          f' {translate("win-percentage")}:    {win_percent_str:>6} \n' \
                          f' {translate("kd-ratio")}:          {player.kd_ratio:>6.2f} \n' \
                          f' {translate("adr")}:               {player.adr:>6.2f} \n' \
                          f' {translate("hs-percentage")}:     {hs_percent_str:>6} \n' \
                          f' {translate("first-blood-rate")}:  {fb_percent_str:>6} ' \
                          '```'
            embed = self.bot.embed_template(description=description)
            embed.set_author(name=user.display_name, url=player.league_profile, icon_url=user.avatar_url_as(size=128))
        else:
            title = translate("cannot-get-stats", ctx.author.display_name)
            embed = self.bot.embed_template(title=title)

        await ctx.send(embed=embed)

    @commands.command(brief=translate('command-leaders-brief'))
    async def leaders(self, ctx):
        """ Send an embed containing the leaderboard data parsed from the player objects returned from the API. """
        if not await self.bot.isValidChannel(ctx):
            return

        num = 5  # Easily modfiy the number of players on the leaderboard
        guild_players = await self.bot.api_helper.get_players([user.id for user in ctx.guild.members])

        if len(guild_players) == 0:
            embed = self.bot.embed_template(title=translate("nobody-ranked"))
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
        formatted_data = [list(map(lambda x: align_text(x, width, align), col)) for col, width, align in z]
        formatted_data = list(map(list, zip(*formatted_data)))  # Transpose list for .format() string
        description = '```ml\n    {}  {}  {}  {} \n'.format(*formatted_data[0])

        for rank, player_row in enumerate(formatted_data[1:], start=1):
            description += ' {}. {}  {}  {}  {} \n'.format(rank, *player_row)

        description += '```'

        # Send leaderboard
        title = f'__{translate("server-leaderboard")}__'
        embed = self.bot.embed_template(title=title, description=description)
        await ctx.send(embed=embed)

    @remove.error
    @empty.error
    @cap.error
    @addspect.error
    @removespect.error
    @create.error
    @delete.error
    @teams.error
    @captains.error
    @maps.error
    @end.error
    @unlink.error
    @forcelink.error
    async def config_error(self, ctx, error):
        """ Respond to a permissions error with an explanation message. """
        if isinstance(error, commands.MissingPermissions):
            await ctx.trigger_typing()
            missing_perm = error.missing_perms[0].replace('_', ' ')
            embed = self.bot.embed_template(title=translate('required-perm', missing_perm))
            await ctx.send(embed=embed)
