# match.py

import aiohttp
import asyncio
import discord
from discord.ext import commands
from discord.errors import NotFound
import random
import json
import re
import sys
import traceback
from collections import defaultdict
#import pyrankvote
#from pyrankvote import Candidate, Ballot


emoji_numbers = [u'\u0030\u20E3',
                 u'\u0031\u20E3',
                 u'\u0032\u20E3',
                 u'\u0033\u20E3',
                 u'\u0034\u20E3',
                 u'\u0035\u20E3',
                 u'\u0036\u20E3',
                 u'\u0037\u20E3',
                 u'\u0038\u20E3',
                 u'\u0039\u20E3',
                 u'\U0001F51F'] 


class PickError(ValueError):
    """ Raised when a team draft pick is invalid for some reason. """

    def __init__(self, message):
        """ Set message parameter. """
        self.message = message


class TeamDraftMenu(discord.Message):
    """ Message containing the components for a team draft. """

    def __init__(self, message, bot, members):
        """ Copy constructor from a message and specific team draft args. """
        # Copy all attributes from message object
        for attr_name in message.__slots__:
            try:
                attr_val = getattr(message, attr_name)
            except AttributeError:
                continue

            setattr(self, attr_name, attr_val)

        # Add custom attributes
        self.bot = bot
        self.members = members
        self.pick_emojis = dict(zip(emoji_numbers[1:], members))
        self.pick_order = '12211221'
        self.pick_number = None
        self.members_left = None
        self.teams = None
        self.future = None

    @property
    def _active_picker(self):
        """ Get the active picker using the pick order and nummber. """
        if self.pick_number is None:
            return None

        picking_team_number = int(self.pick_order[self.pick_number])
        picking_team = self.teams[picking_team_number - 1]  # Subtract 1 to get team's index

        if len(picking_team) == 0:
            return None

        return picking_team[0]        

    def _picker_embed(self, title):
        """ Generate the menu embed based on the current status of the team draft. """
        embed = self.bot.embed_template(title=title)
        embed.set_footer(text=self.bot.translate('team-pick-footer'))

        for team in self.teams:
            team_name = f'__{self.bot.translate("team")}__' if len(team) == 0 else f'__{self.bot.translate("team")} {team[0].display_name}__'

            if len(team) == 0:
                team_players = f'_{self.bot.translate("empty")}_'
            else:
                team_players = '\n'.join(p.display_name for p in team)

            embed.add_field(name=team_name, value=team_players)

        members_left_str = ''

        for emoji, member in self.pick_emojis.items():
            if not any(member in team for team in self.teams):
                members_left_str += f'{emoji}  {member.display_name}\n'
            else:
                members_left_str += f':heavy_multiplication_x:  ~~{member.display_name}~~\n'

        embed.insert_field_at(1, name=f'__{self.bot.translate("players-left")}__', value=members_left_str)

        status_str = ''

        status_str += f'**{self.bot.translate("capt1")}:** {self.teams[0][0].mention}\n' if len(self.teams[0]) else f'**{self.bot.translate("capt1")}:**\n'
        status_str += f'**{self.bot.translate("capt2")}:** {self.teams[1][0].mention}\n\n' if len(self.teams[1]) else f'**{self.bot.translate("capt2")}:**\n\n'
        status_str += f'**{self.bot.translate("current-capt")}:** {self._active_picker.mention}' if self._active_picker is not None else f'**{self.bot.translate("current-capt")}:**'

        embed.add_field(name=f'__{self.bot.translate("info")}__', value=status_str)
        return embed

    def _pick_player(self, picker, pickee):
        """ Process a team captain's player pick, assuming the picker is in the team draft. """
        picker_name = picker.nick if picker.nick is not None else picker.display_name
        # Get picking team
        if picker == pickee:
            raise PickError(self.bot.translate('picker-pick-self').format(picker_name))
        elif self.teams[0] == []:
            picking_team = self.teams[0]
            self.members_left.remove(picker)
            picking_team.append(picker)
        elif self.teams[1] == [] and picker == self.teams[0][0]:
            raise PickError(self.bot.translate('picker-not-turn').format(picker_name))
        elif self.teams[1] == [] and picker in self.teams[0]:
            raise PickError(self.bot.translate('picker-not-captain').format(picker_name))
        elif self.teams[1] == []:
            picking_team = self.teams[1]
            self.members_left.remove(picker)
            picking_team.append(picker)
        elif picker == self.teams[0][0]:
            picking_team = self.teams[0]
        elif picker == self.teams[1][0]:
            picking_team = self.teams[1]
        else:
            raise PickError(self.bot.translate('picker-not-captain').format(picker_name))

        # Check if it's picker's turn
        if picker != self._active_picker:
            raise PickError(self.bot.translate('picker-not-turn').format(picker_name))

        # Prevent picks when team is full
        if len(picking_team) > len(self.members) // 2:
            raise PickError(self.bot.translate('team-full').format(picker_name))

        self.members_left.remove(pickee)
        picking_team.append(pickee)
        self.pick_number += 1

    async def _update_menu(self, title):
        """ Update the message to reflect the current status of the team draft. """
        await self.edit(embed=self._picker_embed(title))
        items = self.pick_emojis.items()
        awaitables = [self.clear_reaction(emoji) for emoji, member in items if member not in self.members_left]
        await asyncio.gather(*awaitables, loop=self.bot.loop)

    async def _process_pick(self, reaction, member):
        """ Handler function for player pick reactions. """
        # Check that reaction is on this message and member is in the team draft
        if reaction.message.id != self.id or member not in self.members:
            return

        # Check that picked player is in the player pool
        pick = self.pick_emojis.get(str(reaction.emoji), None)

        if pick is None or pick not in self.members_left:
            return

        # Attempt to pick the player for the team
        try:
            self._pick_player(member, pick)
        except PickError as e:  # Player not picked
            title = e.message
        else:  # Player picked 
            title = self.bot.translate('team-picked').format(member.display_name, pick.display_name)

        if len(self.members_left) == 1:
            fat_kid_team = self.teams[0] if len(self.teams[0]) <= len(self.teams[1]) else self.teams[1]
            fat_kid_team.append(self.members_left.pop(0))
            await self._update_menu(title)

            if self.future is not None:
                self.future.set_result(None)
            return
        
        if len(self.members_left) == 0:
            await self._update_menu(title)
            if self.future is not None:
                self.future.set_result(None)
            return

        await self._update_menu(title)

    async def draft(self):
        """ Start the team draft and return the teams after it's finished. """
        # Initialize draft
        self.members_left = self.members.copy()  # Copy members to edit players remaining in the player pool
        self.teams = [[], []]
        self.pick_number = 0
        captain_method = await self.bot.get_guild_data(self.guild, 'captain_method')

        if captain_method == 'rank':
            players = await self.bot.api_helper.get_players([member.id for member in self.members_left])
            players.sort(reverse=True, key=lambda x: x.score)

            for team in self.teams:
                captain = self.bot.get_guild(self.guild.id).get_member(players.pop(0).discord)
                self.members_left.remove(captain)
                team.append(captain)
        elif captain_method == 'random':
            temp_members = self.members_left.copy()
            random.shuffle(temp_members)

            for team in self.teams:
                captain = temp_members.pop()
                self.members_left.remove(captain)
                team.append(captain)
        elif captain_method == 'volunteer':
            pass
        else:
            raise ValueError(f'Captain method "{captain_method}" isn\'t valid')

        await self.edit(embed=self._picker_embed(self.bot.translate('team-draft-begun')))

        items = self.pick_emojis.items()
        for emoji, member in items:
            if member in self.members_left:
                await self.add_reaction(emoji)

        # Add listener handlers and wait until there are no members left to pick
        self.future = self.bot.loop.create_future()
        self.bot.add_listener(self._process_pick, name='on_reaction_add')
        await asyncio.wait_for(self.future, 600)
        self.bot.remove_listener(self._process_pick, name='on_reaction_add')

        return self.teams


class MapDraftMenu(discord.Message):
    """ Message containing the components for a map draft. """

    def __init__(self, message, bot):
        """ Copy constructor from a message and specific team draft args. """
        # Copy all attributes from message object
        for attr_name in message.__slots__:
            try:
                attr_val = getattr(message, attr_name)
            except AttributeError:
                continue

            setattr(self, attr_name, attr_val)

        # Add custom attributes 
        self.bot = bot
        self.ban_order = '12' * 20
        self.captains = None
        self.map_pool = None
        self.maps_left = None
        self.ban_number = None
        self.future = None

    @property
    def _active_picker(self):
        """ Get the active picker using the pick order and nummber. """
        if self.ban_number is None or self.captains is None:
            return None

        picking_player_number = int(self.ban_order[self.ban_number])
        return self.captains[picking_player_number - 1]  # Subtract 1 to get picker's index

    def _draft_embed(self, title):
        """ Generate the menu embed based on the current status of the map draft. """
        embed = self.bot.embed_template(title=title)
        embed.set_footer(text=self.bot.translate('map-draft-footer'))
        maps_str = ''

        if self.map_pool is not None and self.maps_left is not None:
            for m in self.map_pool:
                maps_str += f'{m.emoji}  {m.name}\n' if m.emoji in self.maps_left else f':heavy_multiplication_x:  ~~{m.name}~~\n'

        status_str = ''

        if self.captains is not None and self._active_picker is not None:
            status_str += f'**{self.bot.translate("capt1")}:** {self.captains[0].mention}\n'
            status_str += f'**{self.bot.translate("capt2")}:** {self.captains[1].mention}\n\n'
            status_str += f'**{self.bot.translate("current-capt")}:** {self._active_picker.mention}'

        embed.add_field(name=f'__{self.bot.translate("maps-left")}__', value=maps_str)
        embed.add_field(name=f'__{self.bot.translate("info")}__', value=status_str)
        return embed

    async def _update_menu(self, title):
        """ Update the message to reflect the current status of the map draft. """
        await self.edit(embed=self._draft_embed(title))
        awaitables = [self.clear_reaction(m.emoji) for m in self.map_pool if m.emoji not in self.maps_left]
        await asyncio.gather(*awaitables, loop=self.bot.loop)

    async def _process_ban(self, reaction, member):
        """ Handler function for map ban reactions. """
        # Check that reaction is on this message and user is a captain
        if reaction.message.id != self.id or member != self._active_picker:
            return

        # Ban map if the emoji is valid
        try:
            map_ban = self.maps_left.pop(str(reaction))
        except KeyError:
            return

        self.ban_number += 1

        # Check if the draft is over
        if len(self.maps_left) == 1:
            if self.future is not None:
                self.future.set_result(None)

            return

        await self._update_menu(self.bot.translate('user-banned-map').format(member.display_name, map_ban.name))

    async def draft(self, pool, captain_1, captain_2):
        """ Start the team draft and return the teams after it's finished. """
        # Initialize draft
        self.captains = [captain_1, captain_2]
        self.map_pool = pool
        self.maps_left = {m.emoji: m for m in self.map_pool}
        self.ban_number = 0

        if len(self.map_pool) % 2 == 0:
            self.captains.reverse()

        # Edit input message and add emoji button reactions
        await self.edit(embed=self._draft_embed(self.bot.translate('map-bans-begun')))

        for m in self.map_pool:
            await self.add_reaction(m.emoji)

        # Add listener handlers and wait until there are no maps left to ban
        self.future = self.bot.loop.create_future()
        self.bot.add_listener(self._process_ban, name='on_reaction_add')
        await asyncio.wait_for(self.future, 600)
        self.bot.remove_listener(self._process_ban, name='on_reaction_add')
        await self.clear_reactions()

        # Return class to original state after map drafting is done
        map_pick = list(self.maps_left.values())[0]  # Get map pick before setting self.maps_left to None
        self.captains = None
        self.map_pool = None
        self.maps_left = None
        self.ban_number = None
        self.future = None

        return map_pick

'''
class MapVoteMenu(discord.Message):
    """ Message containing the components for a map draft. """

    def __init__(self, message, bot, members):
        """ Copy constructor from a message and specific team draft args. """
        # Copy all attributes from message object
        for attr_name in message.__slots__:
            try:
                attr_val = getattr(message, attr_name)
            except AttributeError:
                continue

            setattr(self, attr_name, attr_val)

        # Add custom attributes
        self.bot = bot
        self.members = members
        self.map_pool = None
        self.ballots = None
        self.maps_options = None
        self.ranked_votes = None
        self.future = None

    def _vote_embed(self):
        embed = self.bot.embed_template(title=self.bot.translate('vote-map-started'))
        embed.add_field(name="Maps", value='\n'.join(f'{m.emoji} {m.name}' for m in self.map_pool))
        embed.set_footer(text=self.bot.translate('vote-map-footer'))
        return embed

    async def _process_vote(self, reaction, member):
        """"""
        # Check that reaction is on this message and user is a captain
        if reaction.message.id != self.id or member not in self.members:
            return

        # Add map vote if it is valid
        if len(self.ranked_votes[member]) == 3:
            return
        
        for c in self.maps_options:
            if c.name == str(reaction) and c not in self.ranked_votes[member]:
                self.ranked_votes[member].append(c)
                self.ballots.append(Ballot(self.ranked_votes[member]))

        if len(self.ranked_votes[member]) == 3:
            for i, vote_option in enumerate(self.ranked_votes[member]):
                print(f'Rank {i+1} :',vote_option.name)
            print()
        # Check if the voting is over        
        for voter in self.ranked_votes:
            if len(self.ranked_votes[voter]) != 3 or len(self.ranked_votes) != len(self.members):
                return

        if self.future is not None:
            self.future.set_result(None)

    async def vote(self, mpool):
        """"""
        self.map_pool = mpool
        self.ballots = []
        self.maps_options = []
        self.ranked_votes = defaultdict(list)

        for m in self.map_pool:
            self.maps_options.append(Candidate(m.emoji))

        await self.edit(embed=self._vote_embed())

        for map_option in self.map_pool:
            await self.add_reaction(map_option.emoji)

        # Add listener handlers and wait until there are no maps left to ban
        self.future = self.bot.loop.create_future()
        self.bot.add_listener(self._process_vote, name='on_reaction_add')

        try:
            await asyncio.wait_for(self.future, 60)
        except asyncio.TimeoutError:
            pass

        self.bot.remove_listener(self._process_vote, name='on_reaction_add')
        try:
            await self.clear_reactions()
        except NotFound:
            pass

        election_result = pyrankvote.instant_runoff_voting(self.maps_options, self.ballots)
        print(election_result)
        winner = election_result.get_winners()[0].name
        pick_map = [m for m in self.map_pool if m.emoji == winner][0]
        print(pick_map.name)

        self.future = None
        self.map_pool = None
        self.ballots = None
        self.maps_options = None
        self.ranked_votes = None

        return pick_map
'''

class MapVoteMenu(discord.Message):
    """ Message containing the components for a map draft. """

    def __init__(self, message, bot, members):
        """ Copy constructor from a message and specific team draft args. """
        # Copy all attributes from message object
        for attr_name in message.__slots__:
            try:
                attr_val = getattr(message, attr_name)
            except AttributeError:
                continue

            setattr(self, attr_name, attr_val)

        # Add custom attributes
        self.bot = bot
        self.members = members
        self.voted_members = None
        self.map_pool = None
        self.map_votes = None
        self.future = None
        self.tie_count = 0

    def _vote_embed(self):
        embed = self.bot.embed_template(title=self.bot.translate('vote-map-started'))
        str_value = '--------------------\n'
        str_value += '\n'.join(f'{emoji_numbers[self.map_votes[m.emoji]]} {m.emoji} {m.name} {":small_orange_diamond:" if self.map_votes[m.emoji] == max(self.map_votes.values()) and self.map_votes[m.emoji] != 0 else ""}' for m in self.map_pool)
        embed.add_field(name=f':repeat_one: :map: __{self.bot.translate("maps")}__', value=str_value)
        embed.set_footer(text=self.bot.translate('vote-map-footer'))
        return embed

    async def _process_vote(self, reaction, member):
        """"""
        # Check that reaction is on this message and user is not the bot
        if reaction.message.id != self.id or member == self.author:
            return

        if member not in self.members or str(reaction) not in [m.emoji for m in self.map_pool]:
            await self.remove_reaction(reaction, member)
            return

        if member in self.voted_members:
            await self.remove_reaction(reaction, member)
            return
        # Add map vote if it is valid
        self.map_votes[str(reaction)] += 1

        self.voted_members[member] = str(reaction)
        await self.edit(embed=self._vote_embed())
        # Check if the voting is over
        if len(self.voted_members) == len(self.members):
            if self.future is not None:
                self.future.set_result(None)

    async def vote(self, mpool):
        """"""
        self.voted_members = {}
        self.map_pool = mpool
        self.map_votes = {m.emoji: 0 for m in self.map_pool}
        await self.edit(embed=self._vote_embed())

        for map_option in self.map_pool:
            await self.add_reaction(map_option.emoji)

        # Add listener handlers and wait until there are no maps left to ban
        self.future = self.bot.loop.create_future()
        self.bot.add_listener(self._process_vote, name='on_reaction_add')

        try:
            await asyncio.wait_for(self.future, 60)
        except asyncio.TimeoutError:
            pass

        self.bot.remove_listener(self._process_vote, name='on_reaction_add')
        try:
            await self.clear_reactions()
        except NotFound:
            pass

        # Gather results
        winners_emoji = []
        winners_votes = 0

        for emoji, votes in self.map_votes.items():
            if votes > winners_votes:
                winners_emoji.clear()
                winners_emoji.append(emoji)
                winners_votes = votes
            elif votes == winners_votes:
                winners_emoji.append(emoji)

        self.map_pool = [m for m in mpool if m.emoji in winners_emoji]

        # Return class to original state after map drafting is done
        self.voted_users = None
        self.map_votes = None
        self.future = None

        if len(winners_emoji) == 1:
            return self.map_pool[0]
        elif len(winners_emoji) == 2 and self.tie_count == 1:
            return random.choice(self.map_pool)
        else:
            if len(winners_emoji) == 2:
                self.tie_count += 1
            return await self.vote(self.map_pool)


class MatchCog(commands.Cog):
    """ Handles everything needed to create matches. """

    def __init__(self, bot):
        """ Set attributes. """
        self.bot = bot
        self.members = {}
        self.reactors = {}
        self.future = {}
        self.ready_message = {}
        self.match_dict = {}

    async def draft_teams(self, message, members):
        """ Create a TeamDraftMenu from an existing message and run the draft. """
        menu = TeamDraftMenu(message, self.bot, members)
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
        random.shuffle(temp_members)
        team_size = len(temp_members) // 2
        return temp_members[:team_size], temp_members[team_size:]

    async def draft_maps(self, message, mpool, captain_1, captain_2):
        """"""
        menu = MapDraftMenu(message, self.bot)
        map_pick = await menu.draft(mpool, captain_1, captain_2)
        return map_pick

    async def vote_maps(self, message, mpool, members):
        """"""
        menu = MapVoteMenu(message, self.bot, members)
        voted_map = await menu.vote(mpool)
        return voted_map

    async def random_map(self, mpool):
        """"""
        return random.choice(mpool)

    async def setup_match_channels(self, guild, match_id, team_one, team_two):
        """Create teams voice channels and move players inside"""
        team1_name = team_one[0].nick if team_one[0].nick is not None else team_one[0].display_name
        team2_name = team_two[0].nick if team_two[0].nick is not None else team_two[0].display_name

        match_category = await guild.create_category_channel(f'{self.bot.translate("match")}{match_id}')
        role = discord.utils.get(guild.roles, name='@everyone')

        voice_channel_one = await guild.create_voice_channel(name=f'{self.bot.translate("team")} {team1_name}',
                                                             category=match_category,
                                                             user_limit=len(team_one))
        await voice_channel_one.set_permissions(role, connect=False, read_messages=True)

        voice_channel_two = await guild.create_voice_channel(name=f'{self.bot.translate("team")} {team2_name}',
                                                             category=match_category,
                                                             user_limit=len(team_two))
        await voice_channel_two.set_permissions(role, connect=False, read_messages=True)

        if guild not in self.match_dict:
            self.match_dict[guild] = {}

        self.match_dict[guild][match_id] = [match_category, voice_channel_one, voice_channel_two, team_one, team_two]

        vc_id = await self.bot.get_guild_data(guild, 'voice_lobby')
        voice_lobby = self.bot.get_channel(vc_id)

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

    async def delete_match_channels(self, message, matchid):
        """ Move players to another channels and remove voice channels on match end. """
        vc_id = await self.bot.get_guild_data(message.guild, 'voice_lobby')
        voice_lobby = self.bot.get_channel(vc_id)
        ended_match = self.match_dict[message.guild][matchid]
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
        self.match_dict[message.guild].pop(matchid)

    @commands.Cog.listener()
    async def on_message(self, message):
        """ Listen to message in results channel and get ended match from webhooks message. """
        if len(message.embeds) < 1:
            return

        results_channel_id = await self.bot.get_guild_data(message.guild, 'text_results')
        if message.channel.id != results_channel_id:
            return

        panel_url = f'{self.bot.api_helper.base_url}/match/'
        if panel_url not in message.embeds[0].description:
            return
            
        if '0:0' in message.embeds[0].author.name:
            return

        match_id = re.findall('match/(\d+)', message.embeds[0].description)[0]
        
        try:
            self.bot.api_helper.get_live_matches().pop(match_id)
        except KeyError:
            pass

        try:
            if match_id in self.match_dict[message.guild]:
                await self.delete_match_channels(message, match_id)
        except KeyError:
            return

    def _ready_embed(self, ctx):
        str_value = ''
        description = self.bot.translate('react-ready').format('✅')
        embed = self.bot.embed_template(title=self.bot.translate('queue-filled'), description=description)
        for member in self.members[ctx.guild]:
            if member not in self.reactors[ctx.guild]:
                str_value += f':heavy_multiplication_x:  {member.mention}\n'
            else:
                str_value += f'✅  {member.mention}\n'

        embed.add_field(name=f":hourglass: __{self.bot.translate('player')}__", value='-------------------\n' + str_value)
        del str_value, description
        return embed

    async def _process_ready(self, reaction, member):
        """ Check if all players in the queue have readied up. """
        if member.id == self.ready_message[member.guild].author.id:
            return
        # Check if this is a message we care about
        if reaction.message.id != self.ready_message[member.guild].id:
            return
        # Check if this is a member and reaction we care about
        if member not in self.members[member.guild] or reaction.emoji != '✅':
            await self.ready_message[member.guild].remove_reaction(reaction, member)
            return

        self.reactors[member.guild].add(member)
        await self.ready_message[member.guild].edit(embed=self._ready_embed(member))
        if self.reactors[member.guild].issuperset(self.members[member.guild]):  # All queued members have reacted
            if self.future[member.guild] is not None:
                self.future[member.guild].set_result(None)       

    async def start_match(self, ctx, members):
        """ Ready all the members up and start a match. """
        # Notify everyone to ready up
        self.members[ctx.guild] =  members
        self.reactors[ctx.guild] = set()  # Track who has readied up
        self.future[ctx.guild] = self.bot.loop.create_future()

        queue_cog = self.bot.get_cog('QueueCog')
        member_mentions = [member.mention for member in members]
        burst_embed = self._ready_embed(ctx)
        msg = queue_cog.last_queue_msgs.get(ctx.guild)
        channel_id = await self.bot.get_guild_data(ctx.guild, 'text_queue')
        text_channel = ctx.guild.get_channel(channel_id)

        if msg is not None:
            await msg.delete()
            queue_cog.last_queue_msgs.pop(ctx.guild)

        index_channel = ctx.guild.channels.index(text_channel)
        self.ready_message[ctx.guild] = await ctx.guild.channels[index_channel].send(''.join(member_mentions), embed=burst_embed)
        await self.ready_message[ctx.guild].add_reaction('✅')

        self.bot.add_listener(self._process_ready, name='on_reaction_add')
        try:
            await asyncio.wait_for(self.future[ctx.guild], 60)
        except asyncio.TimeoutError:  # Not everyone readied up
            self.bot.remove_listener(self._process_ready, name='on_reaction_add')
            unreadied = set(members) - self.reactors[ctx.guild]
            awaitables = [
                self.ready_message[ctx.guild].clear_reactions(),
                self.bot.db_helper.delete_queued_users(ctx.guild.id, *(member.id for member in unreadied))
            ]
            await asyncio.gather(*awaitables, loop=self.bot.loop)
            description = '\n'.join(':x:  ' + member.mention for member in unreadied)
            title = self.bot.translate('not-all-ready')
            burst_embed = self.bot.embed_template(title=title, description=description)
            burst_embed.set_footer(text=self.bot.translate('not-ready-removed'))
            # disconnect unreadied players from the lobby voice channel
            for player in unreadied:
                try:
                    await player.move_to(None)
                except (AttributeError, discord.errors.HTTPException):
                    pass

            await self.ready_message[ctx.guild].edit(content='', embed=burst_embed)
            #self.ready_message.pop(ctx.guild)
            return False  # Not everyone readied up
        else:  # Everyone readied up
            # Attempt to make teams and start match
            self.bot.remove_listener(self._process_ready, name='on_reaction_add')
            awaitables = [
                self.ready_message[ctx.guild].clear_reactions(),
                self.bot.db_helper.get_guild(ctx.guild.id)
            ]
            results = await asyncio.gather(*awaitables, loop=self.bot.loop)
            team_method = results[1]['team_method']
            map_method = results[1]['map_method']
            mpool = [m for m in self.bot.maps if await self.bot.get_guild_data(ctx.guild, m.dev_name)]

            if team_method == 'random' or len(members) == 2:
                team_one, team_two = await self.randomize_teams(members)
            elif team_method == 'autobalance':
                team_one, team_two = await self.autobalance_teams(members)
            elif team_method == 'captains':
                team_one, team_two = await self.draft_teams(self.ready_message[ctx.guild], members)
            else:
                raise ValueError(self.bot.translate('team-method-not-valid').format(team_method))

            await asyncio.sleep(1)
            # Get map pick
            if map_method == 'captains':
                map_pick = await self.draft_maps(self.ready_message[ctx.guild], mpool, team_one[0], team_two[0])
            elif map_method == 'vote':
                map_pick = await self.vote_maps(self.ready_message[ctx.guild], mpool, members)
            elif map_method == 'random':
                map_pick = await self.random_map(mpool)
            else:
                raise ValueError(self.bot.translate('map-method-not-valid').format(map_method))

            await asyncio.sleep(1)
            burst_embed = self.bot.embed_template(description=self.bot.translate('fetching-server'))
            await self.ready_message[ctx.guild].edit(content='', embed=burst_embed)

            # Check if able to get a match server and edit message embed accordingly
            try:
                match = await self.bot.api_helper.start_match(team_one, team_two,
                                                              map_pick.dev_name)  # Request match from API
            except aiohttp.ClientResponseError as e:
                description = self.bot.translate('no-servers')
                burst_embed = self.bot.embed_template(title=self.bot.translate('problem'), description=description)
                #self.ready_message.pop(ctx.guild)
                await self.ready_message[ctx.guild].edit(embed=burst_embed)
                traceback.print_exception(type(e), e, e.__traceback__, file=sys.stderr)  # Print exception to stderr
                return False
            else:
                await asyncio.sleep(3)
                team1_name = team_one[0].nick if team_one[0].nick is not None else team_one[0].display_name
                team2_name = team_two[0].nick if team_two[0].nick is not None else team_two[0].display_name
                match_id = str(match.get_match_id)
                match_url = f'{self.bot.api_helper.base_url}/match/{match_id}'
                description = self.bot.translate('server-connect').format(match.connect_url, match.connect_command)
                burst_embed = self.bot.embed_template(title=self.bot.translate('server-ready'), description=description)

                burst_embed.set_author(name=f'{self.bot.translate("match")}{match_id}', url=match_url)
                burst_embed.set_thumbnail(url=map_pick.image_url)
                burst_embed.add_field(name=f'__{self.bot.translate("team")} {team1_name}__',
                                      value='\n'.join(member.mention for member in team_one))
                burst_embed.add_field(name=f'__{self.bot.translate("team")} {team2_name}__',
                                      value='\n'.join(member.mention for member in team_two))
                burst_embed.set_footer(text=self.bot.translate('server-message-footer'))

                #self.ready_message.pop(ctx.guild)
                
            await self.ready_message[ctx.guild].edit(embed=burst_embed)
            await self.setup_match_channels(ctx.guild, match_id, team_one, team_two)

            return True  # Everyone readied up

    @commands.command(usage='teams {captains|autobalance|random}',
                      brief='Set or view the team creation method (Must have admin perms)')
    @commands.has_permissions(administrator=True)
    async def teams(self, ctx, method=None):
        """ Set or display the method by which teams are created. """
        if not await self.bot.isValidChannel(ctx):
            return

        team_method = await self.bot.get_guild_data(ctx.guild, 'team_method')
        valid_methods = ['captains', 'autobalance', 'random']

        if method is None:
            title = self.bot.translate('team-method').format(team_method)
        else:
            method = method.lower()

            if method == team_method:
                title = self.bot.translate('team-method-already').format(team_method)
            elif method in valid_methods:
                title = self.bot.translate('set-team-method').format(method)
                await self.bot.db_helper.update_guild(ctx.guild.id, team_method=method)
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

        guild_data = await self.bot.db_helper.get_guild(ctx.guild.id)
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
                await self.bot.db_helper.update_guild(ctx.guild.id, captain_method=method)
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

        map_method = await self.bot.get_guild_data(ctx.guild, 'map_method')
        valid_methods = ['captains', 'vote', 'random']

        if method is None:
            title = self.bot.translate('map-method').format(map_method)
        else:
            method = method.lower()

            if method == map_method:
                title = self.bot.translate('map-method-already').format(map_method)
            elif method in valid_methods:
                title = self.bot.translate('set-map-method').format(method)
                await self.bot.db_helper.update_guild(ctx.guild.id, map_method=method)
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

        map_pool = [m.dev_name for m in self.bot.maps if await self.bot.get_guild_data(ctx.guild, m.dev_name)]

        if len(args) == 0:
            embed = self.bot.embed_template(title=self.bot.translate('map-pool'))
        else:
            description = ''
            any_wrong_arg = False  # Indicates if the command was used correctly

            for arg in args:
                map_name = arg[1:]  # Remove +/- prefix
                map_obj = next((m for m in self.bot.maps if m.dev_name == map_name), None)

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
                map_pool_data = {m.dev_name: m.dev_name in map_pool for m in self.bot.maps}
                await self.bot.db_helper.update_guild(ctx.guild.id, **map_pool_data)

            embed = self.bot.embed_template(title=self.bot.translate('modified-map-pool'), description=description)

            if any_wrong_arg:  # Add example usage footer if command was used incorrectly
                embed.set_footer(text=f'Ex: {self.bot.command_prefix[0]}mpool +de_cache -de_mirage')

        active_maps = ''.join(f'{m.emoji}  `{m.dev_name}`\n' for m in self.bot.maps if m.dev_name in map_pool)
        inactive_maps = ''.join(f'{m.emoji}  `{m.dev_name}`\n' for m in self.bot.maps if m.dev_name not in map_pool)

        if not inactive_maps:
            inactive_maps = f'*{self.bot.translate("none")}*'

        embed.add_field(name=f'__{self.bot.translate("active-maps")}__', value=active_maps)
        embed.add_field(name=f'__{self.bot.translate("inactive-maps")}__', value=inactive_maps)
        await ctx.send(embed=embed)

    @commands.command(usage='end [match id]',
                      brief='Force end a match (must have admin perms)')
    @commands.has_permissions(administrator=True)                      
    async def end(self, ctx, *args):
        """ Test end match """
        if not await self.bot.isValidChannel(ctx):
            return
        
        if len(args) == 0:
            msg = f'{self.bot.translate("invalid-usage")}: `{self.bot.command_prefix[0]}end <Match ID>`'
        else:
            try:
                await self.bot.api_helper.end_match(args[0])
            except KeyError:
                msg = self.bot.translate("invalid-match-id")
            else:
                msg = self.bot.translate("match-cancelled").format(args[0])

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
