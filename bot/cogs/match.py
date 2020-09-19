# match.py

import aiohttp
import asyncio
import discord
from discord.ext import commands

from . import menus

from random import shuffle, choice
from re import findall
from traceback import print_exception
import sys


class MatchCog(commands.Cog):
    """ Handles everything needed to create matches. """

    def __init__(self, bot):
        """ Set attributes. """
        self.bot = bot
        self.members = {}
        self.queue_profiles = {}
        self.reactors = {}
        self.future = {}
        self.ready_message = {}
        self.match_dict = {}

    async def draft_teams(self, message, members):
        """ Create a TeamDraftMenu from an existing message and run the draft. """
        menu = menus.TeamDraftMenu(message, self.bot, members)
        teams = await menu.draft()
        return teams[0], teams[1]

    async def autobalance_teams(self, member_ids):
        """ Balance teams based on players' RankMe score. """
        # Only balance teams with even amounts of players
        if len(member_ids) % 2 != 0:
            raise ValueError(self.bot.translate('members-must-even'))

        # Get players and sort by RankMe score
        members_dict = dict(
            zip(await self.bot.api_helper.get_players([member.id for member in member_ids]), member_ids))
        players = list(members_dict.keys())
        players.sort(key=lambda x: x.score)

        # Balance teams
        team_size = len(players) // 2
        team_one = [players.pop()]
        team_two = [players.pop()]

        while players:
            if len(team_one) >= team_size:
                team_two.append(players.pop())
            elif len(team_two) >= team_size:
                team_one.append(players.pop())
            elif sum(p.score for p in team_one) < sum(p.score for p in team_two):
                team_one.append(players.pop())
            else:
                team_two.append(players.pop())

        return list(map(members_dict.get, team_one)), list(map(members_dict.get, team_two))

    @staticmethod
    async def randomize_teams(members):
        """ Randomly split a list of members in half. """
        temp_members = members.copy()
        shuffle(temp_members)
        team_size = len(temp_members) // 2
        return temp_members[:team_size], temp_members[team_size:]

    async def draft_maps(self, message, mpool, captain_1, captain_2):
        """"""
        menu = menus.MapDraftMenu(message, self.bot)
        map_pick = await menu.draft(mpool, captain_1, captain_2)
        return map_pick

    async def vote_maps(self, message, mpool, members):
        """"""
        menu = menus.MapVoteMenu(message, self.bot, members)
        voted_map = await menu.vote(mpool)
        return voted_map

    @staticmethod
    async def random_map(mpool):
        """"""
        return choice(mpool)

    async def create_match_channels(self, category, match_id, team_one, team_two):
        """Create teams voice channels and move players inside"""

        match_category = await category.guild.create_category_channel(f'{self.bot.translate("match")}{match_id}')
        role = discord.utils.get(category.guild.roles, name='@everyone')

        voice_channel_one = await category.guild.create_voice_channel(
            name=f'{self.bot.translate("team")} {team_one[0].display_name}',
            category=match_category,
            user_limit=len(team_one))
        await voice_channel_one.set_permissions(role, connect=False, read_messages=True)

        voice_channel_two = await category.guild.create_voice_channel(
            name=f'{self.bot.translate("team")} {team_two[0].display_name}',
            category=match_category,
            user_limit=len(team_two))
        await voice_channel_two.set_permissions(role, connect=False, read_messages=True)

        if category not in self.match_dict:
            self.match_dict[category] = {}

        self.match_dict[category][match_id] = [match_category, voice_channel_one, voice_channel_two, team_one, team_two]

        lobby_id = await self.bot.get_league_data(category, 'voice_lobby')
        voice_lobby = self.bot.get_channel(lobby_id)

        for t1_player in range(len(team_one)):
            await voice_channel_one.set_permissions(team_one[t1_player], connect=True)
            await voice_lobby.set_permissions(team_one[t1_player], connect=False)
            try:
                await team_one[t1_player].move_to(voice_channel_one)
            except (AttributeError, discord.errors.HTTPException):
                pass

        for t2_player in range(len(team_two)):
            await voice_channel_two.set_permissions(team_two[t2_player], connect=True)
            await voice_lobby.set_permissions(team_two[t2_player], connect=False)
            try:
                await team_two[t2_player].move_to(voice_channel_two)
            except (AttributeError, discord.errors.HTTPException):
                pass

    async def delete_match_channels(self, category, matchid):
        """ Move players to another channels and remove voice channels on match end. """
        lobby_id = await self.bot.get_league_data(category, 'voice_lobby')
        voice_lobby = self.bot.get_channel(lobby_id)
        ended_match = self.match_dict[category][matchid]
        match_players = ended_match[3] + ended_match[4]

        role = discord.utils.get(voice_lobby.guild.roles, name='@everyone')

        vc_ended_match = await voice_lobby.guild.create_voice_channel(name=self.bot.translate('match-over'),
                                                                      category=ended_match[0],
                                                                      user_limit=len(match_players))
        await vc_ended_match.set_permissions(role, connect=False, read_messages=True)

        for player in match_players:
            await voice_lobby.set_permissions(player, overwrite=None)

        for player in match_players:
            try:
                await player.move_to(vc_ended_match)
            except (AttributeError, discord.errors.HTTPException):
                pass

        await ended_match[1].delete()
        await ended_match[2].delete()
        await asyncio.sleep(60)
        await vc_ended_match.delete()
        await ended_match[0].delete()
        self.match_dict[category].pop(matchid)

    @commands.Cog.listener()
    async def on_message(self, message):
        """ Listen to message in results channel and get ended match from webhooks message. """
        if len(message.embeds) < 1:
            return
        try:
            results_channel_id = await self.bot.get_league_data(message.channel.category, 'text_results')
        except AttributeError:
            return

        if message.channel.id != results_channel_id:
            return

        panel_url = f'{self.bot.api_helper.base_url}/match/'
        if panel_url not in message.embeds[0].description:
            return

        match_id = findall('match/(\d+)', message.embeds[0].description)[0]

        try:
            if match_id in self.match_dict[message.channel.category]:
                await self.delete_match_channels(message.channel.category, match_id)
        except KeyError:
            return

    def _ready_embed(self, category):
        str_value = ''
        description = self.bot.translate('react-ready').format('✅')
        embed = self.bot.embed_template(title=self.bot.translate('queue-filled'), description=description)

        for num, member in enumerate(self.members[category], start=1):
            if member not in self.reactors[category]:
                str_value += f':heavy_multiplication_x:  {num}. [{member.display_name}]({self.queue_profiles[category][num-1].league_profile})\n'
            else:
                str_value += f'✅  {num}. [{member.display_name}]({self.queue_profiles[category][num-1].league_profile})\n'

        embed.add_field(name=f":hourglass: __{self.bot.translate('player')}__",
                        value='-------------------\n' + str_value)
        del str_value, description
        return embed

    async def _process_ready(self, reaction, member):
        """ Check if all players in the queue have readied up. """
        if member.id == self.ready_message[reaction.message.channel.category].author.id:
            return
        # Check if this is a message we care about
        if reaction.message.id != self.ready_message[reaction.message.channel.category].id:
            return
        # Check if this is a member and reaction we care about
        if member not in self.members[reaction.message.channel.category] or reaction.emoji != '✅':
            await self.ready_message[reaction.message.channel.category].remove_reaction(reaction, member)
            return

        self.reactors[reaction.message.channel.category].add(member)
        await self.ready_message[reaction.message.channel.category].edit(embed=self._ready_embed(reaction.message.channel.category))
        if self.reactors[reaction.message.channel.category].issuperset(self.members[reaction.message.channel.category]):  # All queued members have reacted
            if self.future[reaction.message.channel.category] is not None:
                self.future[reaction.message.channel.category].set_result(None)

    async def start_match(self, category, members):
        """ Ready all the members up and start a match. """
        queue_cog = self.bot.get_cog('QueueCog')
        self.members[category] = members
        self.reactors[category] = set()  # Track who has readied up
        self.future[category] = self.bot.loop.create_future()
        self.queue_profiles[category] = [await self.bot.api_helper.get_player(member.id) for member in members]

        member_mentions = [member.mention for member in members]
        burst_embed = self._ready_embed(category)
        msg = queue_cog.last_queue_msgs.get(category)
        channel_id = await self.bot.get_league_data(category, 'text_queue')
        text_channel = category.guild.get_channel(channel_id)

        if msg is not None:
            await msg.delete()
            queue_cog.last_queue_msgs.pop(category)

        self.ready_message[category] = await text_channel.send(''.join(member_mentions), embed=burst_embed)
        await self.ready_message[category].add_reaction('✅')

        self.bot.add_listener(self._process_ready, name='on_reaction_add')
        try:
            await asyncio.wait_for(self.future[category], 60)
        except asyncio.TimeoutError:  # Not everyone readied up
            self.bot.remove_listener(self._process_ready, name='on_reaction_add')
            unreadied = set(members) - self.reactors[category]
            awaitables = [
                self.ready_message[category].clear_reactions(),
                self.bot.db_helper.delete_queued_users(category.id, *(member.id for member in unreadied))
            ]
            await asyncio.gather(*awaitables, loop=self.bot.loop)
            unreadied_profiles = [await self.bot.api_helper.get_player(member.id) for member in unreadied]
            description = ''.join(f':x: [{member.display_name}]({unreadied_profiles[num-1].league_profile})\n' for num, member in enumerate(unreadied, start=1))
            title = self.bot.translate('not-all-ready')
            burst_embed = self.bot.embed_template(title=title, description=description)
            burst_embed.set_footer(text=self.bot.translate('not-ready-removed'))
            # disconnect unreadied players from the lobby voice channel
            for player in unreadied:
                try:
                    await player.move_to(None)
                except (AttributeError, discord.errors.HTTPException):
                    pass

            await self.ready_message[category].edit(content='', embed=burst_embed)
            return False  # Not everyone readied up
        else:  # Everyone readied up
            # Attempt to make teams and start match
            self.bot.remove_listener(self._process_ready, name='on_reaction_add')
            awaitables = [
                self.ready_message[category].clear_reactions(),
                self.bot.db_helper.get_league(category.id)
            ]
            results = await asyncio.gather(*awaitables, loop=self.bot.loop)

            team_method = results[1]['team_method']
            map_method = results[1]['map_method']

            if team_method == 'random' or len(members) == 2:
                team_one, team_two = await self.randomize_teams(members)
            elif team_method == 'autobalance':
                team_one, team_two = await self.autobalance_teams(members)
            elif team_method == 'captains':
                team_one, team_two = await self.draft_teams(self.ready_message[category], members)
            else:
                raise ValueError(self.bot.translate('team-method-not-valid').format(team_method))

            await asyncio.sleep(1)
            # Get map pick
            mpool = [m for m in self.bot.all_maps if await self.bot.get_league_data(category, m.dev_name)]

            if map_method == 'captains':
                map_pick = await self.draft_maps(self.ready_message[category], mpool, team_one[0], team_two[0])
            elif map_method == 'vote':
                map_pick = await self.vote_maps(self.ready_message[category], mpool, members)
            elif map_method == 'random':
                map_pick = await self.random_map(mpool)
            else:
                raise ValueError(self.bot.translate('map-method-not-valid').format(map_method))

            await asyncio.sleep(1)
            burst_embed = self.bot.embed_template(description=self.bot.translate('fetching-server'))
            await self.ready_message[category].edit(content='', embed=burst_embed)

            results_id = await self.bot.get_league_data(category, 'text_results')
            results_channel = category.guild.get_channel(results_id)
            webhook = await results_channel.webhooks()

            if not webhook:
                webhook.append(await results_channel.create_webhook(name='League Results'))

            # Check if able to get a match server and edit message embed accordingly
            try:
                match = await self.bot.api_helper.start_match(team_one, team_two, map_pick.dev_name, webhook[0].url)
            except aiohttp.ClientResponseError as e:
                description = self.bot.translate('no-servers')
                burst_embed = self.bot.embed_template(title=self.bot.translate('problem'), description=description)
                await self.ready_message[category].edit(embed=burst_embed)
                print_exception(type(e), e, e.__traceback__, file=sys.stderr)  # Print exception to stderr
                return False
            else:
                await asyncio.sleep(3)

                team1_profiles = [await self.bot.api_helper.get_player(member.id) for member in team_one]
                team2_profiles = [await self.bot.api_helper.get_player(member.id) for member in team_two]

                match_url = f'{self.bot.api_helper.base_url}/match/{match.id}'
                description = self.bot.translate('server-connect').format(match.connect_url, match.connect_command)
                burst_embed = self.bot.embed_template(title=self.bot.translate('server-ready'), description=description)

                burst_embed.set_author(name=f'{self.bot.translate("match")}{match.id}', url=match_url)
                burst_embed.set_thumbnail(url=map_pick.image_url)
                burst_embed.add_field(name=f'__{self.bot.translate("team")} {team_one[0].display_name}__',
                                      value=''.join(f'{num}. [{member.display_name}]({team1_profiles[num-1].league_profile})\n' for num, member in enumerate(team_one, start=1)))
                burst_embed.add_field(name=f'__{self.bot.translate("team")} {team_two[0].display_name}__',
                                      value=''.join(f'{num}. [{member.display_name}]({team2_profiles[num-1].league_profile})\n' for num, member in enumerate(team_two, start=1)))
                burst_embed.set_footer(text=self.bot.translate('server-message-footer'))

            await self.ready_message[category].edit(embed=burst_embed)
            await self.create_match_channels(category, str(match.id), team_one, team_two)

            return True  # Everyone readied up

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
                if args[0] in self.match_dict[ctx.channel.category] and await self.bot.api_helper.end_match(args[0]):
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
