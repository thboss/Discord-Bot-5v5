# commands.py

from discord.ext import commands
from discord.utils import get
from discord.errors import NotFound
from steam.steamid import SteamID, from_url
import asyncio

from bot.helpers.utils import align_text, translate, timedelta_str, unbantime


class CommandsCog(commands.Cog):
    """"""

    def __init__(self, bot):
        self.bot = bot
        self.match_cog = self.bot.get_cog('MatchCog')
        self.queue_cog = self.bot.get_cog('QueueCog')

    @commands.command(usage='create <name>',
                      brief=translate('command-create-brief'))
    @commands.has_permissions(administrator=True)
    async def create(self, ctx, *args):
        args = ' '.join(arg for arg in args)

        if not len(args):
            msg = f'{translate("invalid-usage")}: `{self.bot.command_prefix[0]}create <name>`'
        else:
            category = await ctx.guild.create_category_channel(name=args)
            everyone_role = get(ctx.guild.roles, name='@everyone')

            awaitables = [
                self.bot.db_helper.get_guild(ctx.guild.id),
                ctx.guild.create_text_channel(name=f'queue', category=category),
                ctx.guild.create_text_channel(name=f'commands', category=category),
                ctx.guild.create_voice_channel(name=f'Lobby', category=category, user_limit=10),
                self.bot.db_helper.insert_leagues(category.id),
            ]
            results = await asyncio.gather(*awaitables, loop=self.bot.loop)

            await self.bot.db_helper.insert_guild_leagues(ctx.guild.id, category.id)

            banned_role = ctx.guild.get_role(results[0]['banned_role'])
            linked_role = ctx.guild.get_role(results[0]['linked_role'])
            prematch_channel = ctx.guild.get_channel(results[0]['prematch_channel'])
            queue_channel = results[1]
            commands_channel = results[2]
            lobby_channel = results[3]

            banned_role = await ctx.guild.create_role(name='Banned') if banned_role is None else banned_role
            linked_role = await ctx.guild.create_role(name='Linked') if linked_role is None else linked_role
            prematch_channel = await ctx.guild.create_voice_channel(
                name='Pre-Match') if prematch_channel is None else prematch_channel

            awaitables = [
                self.bot.db_helper.update_league(category.id, text_queue=queue_channel.id,
                                                              text_commands=commands_channel.id,
                                                              voice_lobby=lobby_channel.id),
                self.bot.db_helper.update_guild(ctx.guild.id, linked_role=linked_role.id,
                                                              banned_role=banned_role.id,
                                                              prematch_channel=prematch_channel.id),
                queue_channel.set_permissions(everyone_role, send_messages=False),
                lobby_channel.set_permissions(everyone_role, connect=False),
                lobby_channel.set_permissions(linked_role, connect=True),
                lobby_channel.set_permissions(banned_role, connect=False)
            ]
            await asyncio.gather(*awaitables, loop=self.bot.loop)

            msg = translate('create-league').format(args)

        embed = self.bot.embed_template(title=msg)
        await ctx.send(embed=embed)

    @commands.command(brief=translate('command-delete-brief'))
    @commands.has_permissions(administrator=True)
    async def delete(self, ctx):
        if not await self.bot.valid_channel(ctx):
            return

        await self.bot.db_helper.delete_guild_leagues(ctx.guild.id, ctx.channel.category_id)
        await self.bot.db_helper.delete_leagues(ctx.channel.category_id)
        for channel in ctx.channel.category.channels + [ctx.channel.category]:
            await channel.delete()

    @commands.command(usage='link <mention> <Steam ID/Profile>',
                      brief=translate('command-link-brief'))
    async def link(self, ctx, *args):
        """ Force link player with steam on the backend. """
        if not await self.bot.valid_channel(ctx):
            return

        if not args and not ctx.message.mentions: # Link by sned url
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

        else: # Force link
            author_perms = ctx.author.guild_permissions
            if not author_perms.administrator:
                raise commands.MissingPermissions(missing_perms=['administrator'])

            try:
                user = ctx.message.mentions[0]
                steam_id = SteamID(args[1])
            except IndexError:
                title = f"**{translate('invalid-usage')}: `{self.bot.command_prefix[0]}link <mention> <steam profile>`**"
            else:
                if not steam_id.is_valid():
                    steam_id = from_url(args[1], http_timeout=15)
                    if steam_id is None:
                        steam_id = from_url(f'https://steamcommunity.com/id/{args[1]}/', http_timeout=15)
                        if steam_id is None:
                            raise commands.UserInputError(message='Please enter a valid SteamID or community url.')

                link = await self.bot.api_helper.force_link_discord(user.id, steam_id)
                member_ids = [member.id for member in ctx.guild.members]
                players = await self.bot.api_helper.get_players(member_ids)
                players = {p.discord: p.steam for p in players}

                if not link:
                    if user.id in players and players[user.id] == steam_id:
                        player = await self.bot.api_helper.get_player(user.id)
                        title = f'User **{user.display_name}** is already linked to **[Steam account]({player.steam_profile})**'
                    else:
                        try:
                            steam_author = list(players.keys())[list(players.values()).index(steam_id)]
                        except ValueError:
                            title = f'Steam id **{steam_id}** is linked to another discord account (Not in this discord server)'
                        else:
                            title = f'Steam id **{steam_id}** is linked to another discord account : **{ctx.guild.get_member(steam_author).mention}**'

                else:
                    player = await self.bot.api_helper.get_player(user.id)
                    title = translate('force-linked', user.display_name, player.steam_profile)
                    linked_role_id = await self.bot.get_guild_data(ctx.guild, 'linked_role')
                    linked_role = ctx.guild.get_role(linked_role_id)
                    await user.add_roles(linked_role)
                    await self.bot.api_helper.update_discord_name(user)

        embed = self.bot.embed_template(description=title)
        await ctx.send(embed=embed)

    @commands.command(usage='unlink <mention>',
                      brief=translate('command-unlink-brief'))
    @commands.has_permissions(administrator=True)
    async def unlink(self, ctx):
        """ Unlink a player by delete him on the backend. """
        if not await self.bot.valid_channel(ctx):
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
                linked_role_id = await self.bot.get_guild_data(ctx.guild, 'linked_role')
                linked_role = ctx.guild.get_role(linked_role_id)
                await user.remove_roles(linked_role)

        embed = self.bot.embed_template(title=title)
        await ctx.send(embed=embed)

    @commands.command(brief=translate('command-check-brief'))
    async def check(self, ctx):
        if not await self.bot.valid_channel(ctx):
            return

        if not await self.bot.api_helper.is_linked(ctx.author.id):
            msg = translate('discord-not-linked')
        else:
            linked_role_id = await self.bot.get_guild_data(ctx.guild, 'linked_role')
            linked_role = ctx.guild.get_role(linked_role_id)
            await ctx.author.add_roles(linked_role)
            await self.bot.api_helper.update_discord_name(ctx.author)
            msg = translate('discord-get-role')

        embed = self.bot.embed_template(description=msg, color=self.bot.color)
        await ctx.send(content=ctx.author.mention, embed=embed)

    @commands.command(brief=translate('command-empty-brief'))
    @commands.has_permissions(kick_members=True)
    async def empty(self, ctx):
        """ Reset the league's queue list to empty. """
        if not await self.bot.valid_channel(ctx):
            return

        self.queue_cog.block_lobby[ctx.channel.category] = True
        await self.bot.db_helper.clear_queued_users(ctx.channel.category.id)
        msg = translate('queue-emptied')
        embed = await self.queue_cog.queue_embed(ctx.channel.category, msg)

        lobby_id = await self.bot.get_league_data(ctx.channel.category, 'voice_lobby')
        prematch_id = await self.bot.get_guild_data(ctx.guild, 'prematch_channel')
        lobby = ctx.bot.get_channel(lobby_id)
        prematch = ctx.bot.get_channel(prematch_id)

        for player in lobby.members:
            await player.move_to(prematch)

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
        if not await self.bot.valid_channel(ctx):
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
                await self.bot.db_helper.clear_queued_users(ctx.channel.category_id)
                await self.bot.db_helper.update_league(ctx.channel.category_id, capacity=new_cap)
                embed = await self.queue_cog.queue_embed(ctx.channel.category, translate('queue-emptied'))
                embed.set_footer(text=translate('queue-emptied-footer'))
                await self.queue_cog.update_last_msg(ctx.channel.category, embed)
                msg = translate('set-capacity', new_cap)

                lobby_id = await self.bot.get_league_data(ctx.channel.category, 'voice_lobby')
                prematch_id = await self.bot.get_guild_data(ctx.guild, 'prematch_channel')
                lobby = ctx.bot.get_channel(lobby_id)
                prematch = ctx.bot.get_channel(prematch_id)

                for player in lobby.members:
                    await player.move_to(prematch)

                self.queue_cog.block_lobby[ctx.channel.category] = False
                await lobby.edit(user_limit=new_cap)

        await ctx.send(embed=self.bot.embed_template(title=msg))

    @commands.command(usage='spectators {+|-} <mention> <mention> ...',
                      brief=translate('command-spectators-brief'))
    async def spectators(self, ctx, *args):
        """"""
        if not await self.bot.valid_channel(ctx):
            return

        curr_spectator_ids = await self.bot.db_helper.get_spect_users(ctx.channel.category_id)
        curr_spectators = [ctx.guild.get_member(spectator_id) for spectator_id in curr_spectator_ids]
        spectators = ctx.message.mentions

        if not args:
            embed = self.bot.embed_template()
            embed.add_field(name=f'__Spectators__',
                            value='No spectators' if not curr_spectators else ''.join(f'{num}. {member.mention}\n' for num, member in enumerate(curr_spectators, start=1)))
            await ctx.send(embed=embed)
            return

        author_perms = ctx.author.guild_permissions
        if not author_perms.administrator:
            raise commands.MissingPermissions(missing_perms=['administrator'])

        prefix = args[0]
        title = ''

        if prefix not in ['+', '-']:
            title = f'{translate("invalid-usage")}: `{self.bot.command_prefix[0]}spectators [+|-] <mention>`'
        else:
            await self.bot.db_helper.delete_queued_users(ctx.channel.category_id, [spectator.id for spectator in spectators])
            for spectator in spectators:
                if args[0] == '+':
                    if spectator.id not in curr_spectator_ids:
                        await self.bot.db_helper.insert_spect_users(ctx.channel.category_id, spectator.id)
                        title += f'{translate("added-spect", spectator.display_name)}\n'
                    else:
                        title = f'{translate("already-spect", spectator.display_name)}\n'
                elif args[0] == '-':
                    if spectator.id in curr_spectator_ids:
                        await self.bot.db_helper.delete_spect_users(ctx.channel.category_id, spectator.id)
                        title += f'{translate("removed-spect", spectator.display_name)}\n'
                    else:
                        title = f'{translate("already-spect", spectator.display_name)}\n'

        embed = self.bot.embed_template(title=title)
        await ctx.send(embed=embed)

    @commands.command(usage='teams {captains|autobalance|random}',
                      brief=translate('command-teams-brief'))
    @commands.has_permissions(administrator=True)
    async def teams(self, ctx, method=None):
        """ Set or display the method by which teams are created. """
        if not await self.bot.valid_channel(ctx):
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
        if not await self.bot.valid_channel(ctx):
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

    @commands.command(usage='mpool {+|-}<map name> ...',
                      brief=translate('command-mpool-brief'))
    async def mpool(self, ctx, *args):
        """ Edit the guild's map pool for map drafts. """
        if not await self.bot.valid_channel(ctx):
            return

        map_pool = [m.dev_name for m in self.bot.all_maps.values() if
                    await self.bot.get_league_data(ctx.channel.category, m.dev_name)]

        if len(args) == 0:
            embed = self.bot.embed_template(title=translate('map-pool'))
        else:
            author_perms = ctx.author.guild_permissions
            if not author_perms.administrator:
                raise commands.MissingPermissions(missing_perms=['administrator'])

            description = ''
            any_wrong_arg = False  # Indicates if the command was used correctly

            for arg in args:
                map_name = arg[1:]  # Remove +/- prefix
                map_obj = next((m for m in self.bot.all_maps.values() if m.dev_name == map_name), None)

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
                map_pool_data = {m.dev_name: m.dev_name in map_pool for m in self.bot.all_maps.values()}
                await self.bot.db_helper.update_league(ctx.channel.category_id, **map_pool_data)

            embed = self.bot.embed_template(title=translate('modified-map-pool'), description=description)

            if any_wrong_arg:  # Add example usage footer if command was used incorrectly
                embed.set_footer(text=f'Ex: {self.bot.command_prefix[0]}mpool +de_cache -de_mirage')

        active_maps = ''.join(f'{m.emoji}  `{m.dev_name}`\n' for m in self.bot.all_maps.values() if m.dev_name in map_pool)
        inactive_maps = ''.join(f'{m.emoji}  `{m.dev_name}`\n' for m in self.bot.all_maps.values() if m.dev_name not in map_pool)

        if not inactive_maps:
            inactive_maps = f'*{translate("none")}*'

        embed.add_field(name=f'__{translate("active-maps")}__', value=active_maps)
        embed.add_field(name=f'__{translate("inactive-maps")}__', value=inactive_maps)
        await ctx.send(embed=embed)

    @commands.command(usage='maps [{captains|vote|random}]',
                      brief=translate('command-maps-brief'))
    @commands.has_permissions(administrator=True)
    async def maps(self, ctx, method=None):
        """ Set or display the method by which the teams are created. """
        if not await self.bot.valid_channel(ctx):
            return

        map_method = await self.bot.get_league_data(ctx.channel.category, 'map_method')
        valid_methods = ['ban', 'vote', 'random']

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

    @commands.command(usage='end [match id]',
                      brief=translate('command-end-brief'))
    @commands.has_permissions(administrator=True)
    async def end(self, ctx, *args):
        """ Force end a match. """
        if not await self.bot.valid_channel(ctx):
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
        if not await self.bot.valid_channel(ctx):
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
        if not await self.bot.valid_channel(ctx):
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

    @commands.command(usage='ban <user mention> ... [<days>d] [<hours>h] [<minutes>m]',
                      brief=translate('command-ban-brief'))
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx, *args):
        """ Ban users mentioned in the command from joining the queue for a certain amount of time or indefinitely. """
        # Check that users are mentioned
        if len(ctx.message.mentions) == 0:
            embed = self.bot.embed_template(title=translate('mention-user-to-ban'))
            await ctx.send(embed=embed)
            return

        time_delta, unban_time = unbantime(ctx.message.content)

        # Get user IDs to ban from mentions and insert them into ban table
        user_ids = [user.id for user in ctx.message.mentions]
        await self.bot.db_helper.insert_banned_users(ctx.guild.id, *user_ids, unban_time=unban_time)
        banned_role_id = await self.bot.get_guild_data(ctx.guild, 'banned_role')
        banned_role = ctx.guild.get_role(banned_role_id)
        for user in ctx.message.mentions:
            await user.add_roles(banned_role)

        # Generate embed and send message
        banned_users_str = ', '.join(f'**{user.display_name}**' for user in ctx.message.mentions)
        ban_time_str = '' if unban_time is None else f' for {timedelta_str(time_delta)}'
        embed = self.bot.embed_template(title=f'Banned {banned_users_str}{ban_time_str}')
        embed.set_footer(text=translate('banned-footer'))
        await ctx.send(embed=embed)

    @commands.command(usage='unban <user mention> ...',
                      brief=translate('command-unban-brief'))
    @commands.has_permissions(ban_members=True)
    async def unban(self, ctx):
        """ Unban users mentioned in the command so they can join the queue. """
        # Check that users are mentioned
        if len(ctx.message.mentions) == 0:
            embed = self.bot.embed_template(title='mention-user-to-unban')
            await ctx.send(embed=embed)
            return

        # Get user IDs to unban from mentions and delete them from the ban table
        user_ids = [user.id for user in ctx.message.mentions]
        unbanned_ids = await self.bot.db_helper.delete_banned_users(ctx.guild.id, *user_ids)

        # Generate embed and send message
        unbanned_users = [user for user in ctx.message.mentions if user.id in unbanned_ids]        
        never_banned_users = [user for user in ctx.message.mentions if user.id not in unbanned_ids]
        unbanned_users_str = ', '.join(f'**{user.display_name}**' for user in unbanned_users)
        never_banned_users_str = ', '.join(f'**{user.display_name}**' for user in never_banned_users)
        title_1 = 'nobody' if unbanned_users_str == '' else unbanned_users_str
        were_or_was = 'were' if len(never_banned_users) > 1 else 'was'
        title_2 = '' if never_banned_users_str == '' else f' ({never_banned_users_str} {were_or_was} never banned)'
        embed = self.bot.embed_template(title=f'Unbanned {title_1}{title_2}')
        embed.set_footer(text=translate('unbanned-footer'))
        await ctx.send(embed=embed)

        banned_role_id = await self.bot.get_guild_data(ctx.guild, 'banned_role')
        banned_role = ctx.guild.get_role(banned_role_id)
        for user in unbanned_users:
            await user.remove_roles(banned_role)


    @create.error
    @delete.error
    @empty.error
    @cap.error
    @spectators.error
    @teams.error
    @captains.error
    @maps.error
    @mpool.error
    @end.error
    @unlink.error
    @link.error
    @ban.error
    @unban.error
    async def config_error(self, ctx, error):
        """ Respond to a permissions error with an explanation message. """
        if isinstance(error, commands.MissingPermissions):
            await ctx.trigger_typing()
            missing_perm = error.missing_perms[0].replace('_', ' ')
            embed = self.bot.embed_template(title=translate('required-perm', missing_perm))
            await ctx.send(embed=embed)

        if isinstance(error, commands.UserInputError):
            await ctx.trigger_typing()
            embed = self.bot.embed_template(title=str(error))
            await ctx.send(embed=embed)
