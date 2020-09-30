# match.py

import aiohttp
import asyncio
import discord
from discord.ext import commands

from . import menus
from bot.helpers.utils import translate

from random import shuffle, choice
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
            raise ValueError(translate('members-must-even'))

        # Get players and sort by RankMe score
        players = await self.bot.api_helper.get_players([member.id for member in member_ids])
        players.sort(key=lambda x: member_ids.index(x['discord']))
        members_dict = dict(zip(players, member_ids))
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

        match_category = await category.guild.create_category_channel(f'{translate("match")}{match_id}')
        role = discord.utils.get(category.guild.roles, name='@everyone')

        channel_team_one = await category.guild.create_voice_channel(
            name=f'{translate("team")} {team_one[0].display_name}',
            category=match_category,
            user_limit=len(team_one))
        await channel_team_one.set_permissions(role, connect=False, read_messages=True)

        channel_team_two = await category.guild.create_voice_channel(
            name=f'{translate("team")} {team_two[0].display_name}',
            category=match_category,
            user_limit=len(team_two))
        await channel_team_two.set_permissions(role, connect=False, read_messages=True)

        if category not in self.match_dict:
            self.match_dict[category] = {}

        self.match_dict[category][match_id] = [match_category, channel_team_one, channel_team_two, team_one, team_two]

        lobby_id = await self.bot.get_league_data(category, 'voice_lobby')
        lobby = self.bot.get_channel(lobby_id)

        for p1, p2 in zip(team_one, team_two):
            await channel_team_one.set_permissions(p1, connect=True)
            await lobby.set_permissions(p1, connect=False)
            await channel_team_two.set_permissions(p2, connect=True)
            await lobby.set_permissions(p2, connect=False)            
            try:
                await p1.move_to(channel_team_one)
            except (AttributeError, discord.errors.HTTPException):
                pass 
            try:
                await p2.move_to(channel_team_two)
            except (AttributeError, discord.errors.HTTPException):
                pass

    async def delete_match_channels(self, category, matchid):
        """ Move players to another channels and remove voice channels on match end. """
        lobby_id = await self.bot.get_league_data(category, 'voice_lobby')
        lobby = self.bot.get_channel(lobby_id)
        prelobby_id = await self.bot.get_league_data(category, 'voice_prelobby')
        prelobby = self.bot.get_channel(prelobby_id)
        match_players = self.match_dict[category][matchid][3] + self.match_dict[category][matchid][4]

        for player in match_players:
            await lobby.set_permissions(player, overwrite=None)
            try:
                await player.move_to(prelobby)
            except (AttributeError, discord.errors.HTTPException):
                pass

        for channel in reversed(self.match_dict[category][matchid][:3]):
            await channel.delete()

        self.match_dict[category].pop(matchid)

    def _ready_embed(self, category):
        str_value = ''
        description = translate('react-ready').format('✅')
        embed = self.bot.embed_template(title=translate('queue-filled'), description=description)

        for num, member in enumerate(self.members[category], start=1):
            if member not in self.reactors[category]:
                str_value += f':heavy_multiplication_x:  {num}. [{member.display_name}]({self.queue_profiles[category][num-1].league_profile})\n '
            else:
                str_value += f'✅  {num}. [{member.display_name}]({self.queue_profiles[category][num-1].league_profile})\n '

        embed.add_field(name=f":hourglass: __{translate('player')}__",
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
        if self.reactors[reaction.message.channel.category].issuperset(self.members[reaction.message.channel.category]):
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
            prelobby_id = await self.bot.get_league_data(category, 'voice_prelobby')
            prelobby = category.guild.get_channel(prelobby_id)
            title = translate('not-all-ready')
            burst_embed = self.bot.embed_template(title=title, description=description)
            burst_embed.set_footer(text=translate('not-ready-removed'))
            # disconnect unreadied players from the lobby voice channel
            for player in unreadied:
                try:
                    await player.move_to(prelobby)
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
                raise ValueError(translate('team-method-not-valid').format(team_method))

            await asyncio.sleep(1)

            spect_ids = await self.bot.db_helper.get_spect_users(category.id)
            spect_members = [category.guild.get_member(member_id) for member_id in spect_ids]
            spect_players = [await self.bot.api_helper.get_player(spect_id) for spect_id in spect_ids]
            spect_steams = [str(spect_player.steam) for spect_player in spect_players]
            # Get map pick
            mpool = [m for m in self.bot.all_maps if await self.bot.get_league_data(category, m.dev_name)]

            if map_method == 'captains':
                map_pick = await self.draft_maps(self.ready_message[category], mpool, team_one[0], team_two[0])
            elif map_method == 'vote':
                map_pick = await self.vote_maps(self.ready_message[category], mpool, members)
            elif map_method == 'random':
                map_pick = await self.random_map(mpool)
            else:
                raise ValueError(translate('map-method-not-valid').format(map_method))

            await asyncio.sleep(1)
            burst_embed = self.bot.embed_template(description=translate('fetching-server'))
            await self.ready_message[category].edit(content='', embed=burst_embed)

            # Check if able to get a match server and edit message embed accordingly
            try:
                match = await self.bot.api_helper.start_match(team_one, team_two, spect_steams, map_pick.dev_name)
            except aiohttp.ClientResponseError as e:
                description = translate('no-servers')
                burst_embed = self.bot.embed_template(title=translate('problem'), description=description)
                await self.ready_message[category].edit(embed=burst_embed)
                print_exception(type(e), e, e.__traceback__, file=sys.stderr)  # Print exception to stderr
                return False
            else:
                await asyncio.sleep(3)

                team1_profiles = [await self.bot.api_helper.get_player(member.id) for member in team_one]
                team2_profiles = [await self.bot.api_helper.get_player(member.id) for member in team_two]

                match_url = f'{self.bot.api_helper.base_url}/match/{match.id}'
                description = translate('server-connect').format(match.connect_url, match.connect_command)
                burst_embed = self.bot.embed_template(title=translate('server-ready'), description=description)

                burst_embed.set_author(name=f'{translate("match")}{match.id}', url=match_url)
                burst_embed.set_thumbnail(url=map_pick.image_url)
                burst_embed.add_field(name=f'__{translate("team")} {team_one[0].display_name}__',
                                      value=''.join(f'{num}. [{member.display_name}]({team1_profiles[num-1].league_profile})\n' for num, member in enumerate(team_one, start=1)))
                burst_embed.add_field(name=f'__{translate("team")} {team_two[0].display_name}__',
                                      value=''.join(f'{num}. [{member.display_name}]({team2_profiles[num-1].league_profile})\n' for num, member in enumerate(team_two, start=1)))
                burst_embed.add_field(name=f'__Spectators__',
                                      value='No spectators' if not spect_members else ''.join(f'{num}. {member.mention}\n' for num, member in enumerate(spect_members, start=1)))
                burst_embed.set_footer(text=translate('server-message-footer'))

            await self.ready_message[category].edit(embed=burst_embed)
            await self.create_match_channels(category, str(match.id), team_one, team_two)

            async def check_live():
                if not await self.bot.api_helper.is_match_live(str(match.id)):
                    await self.delete_match_channels(category, str(match.id))
                    self.bot.scheduler.remove_job(str(match.id))

            self.bot.scheduler.add_job(check_live, 'interval', seconds=10, id=str(match.id))

            return True  # Everyone readied up
