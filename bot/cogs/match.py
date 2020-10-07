# match.py

import aiohttp
import asyncio
from discord.ext import commands
from discord.utils import get
from discord.errors import HTTPException

from . import menus
from bot.helpers.utils import translate

from random import shuffle, choice
from traceback import print_exception
from collections import defaultdict
import sys


class MatchCog(commands.Cog):
    """ Handles everything needed to create matches. """

    def __init__(self, bot):
        """ Set attributes. """
        self.bot = bot
        self.ready_message = {}
        self.match_dict = {}
        self.no_servers = {}
        self.no_servers = defaultdict(lambda: False, self.no_servers)

        async def check_over_matches():
            if self.match_dict:
                matches = await self.bot.api_helper.matches_status()
                for matchid in list(self.match_dict):
                    if matchid in matches and not matches[matchid]:
                        await self.delete_match_channels(matchid)

        self.bot.scheduler.add_job(check_over_matches, 'interval', seconds=10, id='check_over')

    async def draft_teams(self, message, members):
        """ Create a TeamDraftMenu from an existing message and run the draft. """
        menu = menus.TeamDraftMenu(message, self.bot, members)
        teams = await menu.draft()
        return teams[0], teams[1]

    async def autobalance_teams(self, members):
        """ Balance teams based on players' RankMe score. """
        # Only balance teams with even amounts of players
        if len(members) % 2 != 0:
            raise ValueError(translate('members-must-even'))
        
        # Get players and sort by RankMe score
        members_dict = dict(zip(await self.bot.api_helper.get_players([member.id for member in members]), members))
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

    async def track_ready(self, message, members):
        menu = menus.ReadyMenu(message, self.bot, members)
        ready_users = await menu.ready_up()
        return ready_users

    async def create_match_channels(self, league_category, match_id, members_team_one, members_team_two):
        """ Create teams voice channels and move players into. """

        match_category = await league_category.guild.create_category_channel(f'{translate("match")}{match_id}')
        role = get(league_category.guild.roles, name='@everyone')

        channel_team_one = await league_category.guild.create_voice_channel(
            name=f'{translate("team")} {members_team_one[0].display_name}',
            category=match_category,
            user_limit=len(members_team_one))
        await channel_team_one.set_permissions(role, connect=False, read_messages=True)

        channel_team_two = await league_category.guild.create_voice_channel(
            name=f'{translate("team")} {members_team_two[0].display_name}',
            category=match_category,
            user_limit=len(members_team_two))
        await channel_team_two.set_permissions(role, connect=False, read_messages=True)

        self.match_dict[match_id] = {'league_category': league_category,
                                     'match_category': match_category,
                                     'channel_team_one': channel_team_one,
                                     'channel_team_two': channel_team_two,
                                     'members_team_one': members_team_one,
                                     'members_team_two': members_team_two}

        lobby_id = await self.bot.get_league_data(league_category, 'voice_lobby')
        lobby = self.bot.get_channel(lobby_id)

        # move members into thier team channels
        for m1, m2 in zip(members_team_one, members_team_two):
            await channel_team_one.set_permissions(m1, connect=True)
            await lobby.set_permissions(m1, connect=False)
            await channel_team_two.set_permissions(m2, connect=True)
            await lobby.set_permissions(m2, connect=False)            
            try:
                await m1.move_to(channel_team_one)
            except (AttributeError, HTTPException):
                pass 
            try:
                await m2.move_to(channel_team_two)
            except (AttributeError, HTTPException):
                pass

    async def delete_match_channels(self, matchid):
        """ Move match players to pre-lobby and delete teams voice channels on match end. """

        lobby_id = await self.bot.get_league_data(self.match_dict[matchid]['league_category'], 'voice_lobby')
        lobby = self.bot.get_channel(lobby_id)
        prelobby_id = await self.bot.get_league_data(self.match_dict[matchid]['league_category'], 'voice_prelobby')
        prelobby = self.bot.get_channel(prelobby_id)
        match_players = self.match_dict[matchid]['members_team_one'] + self.match_dict[matchid]['members_team_two']

        for player in match_players:
            await lobby.set_permissions(player, overwrite=None)
            try:
                await player.move_to(prelobby)
            except (AttributeError, HTTPException):
                pass

        await self.match_dict[matchid]['channel_team_two'].delete()
        await self.match_dict[matchid]['channel_team_one'].delete()
        await self.match_dict[matchid]['match_category'].delete()

        self.match_dict.pop(matchid)

    async def start_match(self, category, members):
        """ Ready all the members up and start a match. """

        queue_cog = self.bot.get_cog('QueueCog')
        msg = queue_cog.last_queue_msgs.get(category)
        channel_id = await self.bot.get_league_data(category, 'text_queue')
        text_channel = category.guild.get_channel(channel_id)

        if msg is not None:
            await msg.delete()
            queue_cog.last_queue_msgs.pop(category)

        self.ready_message[category] = await text_channel.send(''.join([member.mention for member in members]))
        ready_users = await self.track_ready(self.ready_message[category], members)
        unreadied = set(members) - ready_users

        if unreadied:  # Not everyone readied up
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
                except (AttributeError, HTTPException):
                    pass

            await self.ready_message[category].edit(content='', embed=burst_embed)
            return False  # Not everyone readied up
        else:  # Everyone readied up
            # Attempt to make teams and start match
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
                raise ValueError(translate('team-method-not-valid', team_method))

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
                raise ValueError(translate('map-method-not-valid', map_method))

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
                self.no_servers[category] = True
                return False
            else:
                await asyncio.sleep(3)

                if len(team_one) > 1:
                    team1_players = await self.bot.api_helper.get_players([member.id for member in team_one])
                else:
                    team1_players = [await self.bot.api_helper.get_player(team_one[0].id)]

                if len(team_two) > 1:
                    team2_players = await self.bot.api_helper.get_players([member.id for member in team_two])
                else:
                    team2_players = [await self.bot.api_helper.get_player(team_two[0].id)]

                match_url = f'{self.bot.api_helper.base_url}/match/{match.id}'
                description = translate('server-connect', match.connect_url, match.connect_command)
                burst_embed = self.bot.embed_template(title=translate('server-ready'), description=description)

                burst_embed.set_author(name=f'{translate("match")}{match.id}', url=match_url)
                burst_embed.set_thumbnail(url=map_pick.image_url)
                
                burst_embed.add_field(name=f'__{translate("team")} {team_one[0].display_name}__',
                                      value=''.join(f'{num}. [{member.display_name}]({team1_players[num-1].league_profile})\n' for num, member in enumerate(team_one, start=1)))
                burst_embed.add_field(name=f'__{translate("team")} {team_two[0].display_name}__',
                                      value=''.join(f'{num}. [{member.display_name}]({team2_players[num-1].league_profile})\n' for num, member in enumerate(team_two, start=1)))
                burst_embed.add_field(name=f'__Spectators__',
                                      value='No spectators' if not spect_members else ''.join(f'{num}. {member.mention}\n' for num, member in enumerate(spect_members, start=1)))
                burst_embed.set_footer(text=translate('server-message-footer'))

            await self.ready_message[category].edit(embed=burst_embed)
            await self.create_match_channels(category, str(match.id), team_one, team_two)

            return True  # Everyone readied up
