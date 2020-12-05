# menus.py

import asyncio
import discord
from random import shuffle, choice

from bot.helpers.utils import translate


EMOJI_NUMBERS = [u'\u0030\u20E3',
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
        self.pick_emojis = dict(zip(EMOJI_NUMBERS[1:], members))
        self.pick_order = '1' + '2211'*20
        self.pick_number = None
        self.members_left = None
        self.players = None
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
        embed.set_footer(text=translate('team-pick-footer'))

        for team in self.teams:
            team_name = f'__{translate("team")}__' if len(
                team) == 0 else f'__{translate("team")} {team[0].display_name}__'

            if len(team) == 0:
                team_players = f'_{translate("empty")}_'
            else:
                team_players = '\n'.join(p.display_name for p in team)

            embed.add_field(name=team_name, value=team_players)

        members_left_str = ''

        for index, (emoji, member) in enumerate(self.pick_emojis.items()):
            if not any(member in team for team in self.teams):
                members_left_str += f'{emoji}  [{member.display_name}]({self.players[index].league_profile})  |  {self.players[index].score}\n'
            else:
                members_left_str += f':heavy_multiplication_x:  ~~[{member.display_name}]({self.players[index].league_profile})~~\n'

        embed.insert_field_at(1, name=f'__{translate("players-left")}__', value=members_left_str)

        status_str = ''

        status_str += f'**{translate("capt1")}:** {self.teams[0][0].mention}\n' if len(
            self.teams[0]) else f'**{translate("capt1")}:**\n '
        status_str += f'**{translate("capt2")}:** {self.teams[1][0].mention}\n\n' if len(
            self.teams[1]) else f'**{translate("capt2")}:**\n\n '
        status_str += f'**{translate("current-capt")}:** {self._active_picker.mention}' \
            if self._active_picker is not None else f'**{translate("current-capt")}:**'

        embed.add_field(name=f'__{translate("info")}__', value=status_str)
        return embed

    def _pick_player(self, picker, pickee):
        """ Process a team captain's player pick, assuming the picker is in the team draft. """
        # Get picking team
        if picker == pickee:
            raise PickError(translate('picker-pick-self', picker.display_name))
        elif not self.teams[0]:
            picking_team = self.teams[0]
            self.members_left.remove(picker)
            picking_team.append(picker)
        elif self.teams[1] == [] and picker == self.teams[0][0]:
            raise PickError(translate('picker-not-turn', picker.display_name))
        elif self.teams[1] == [] and picker in self.teams[0]:
            raise PickError(translate('picker-not-captain', picker.display_name))
        elif not self.teams[1]:
            picking_team = self.teams[1]
            self.members_left.remove(picker)
            picking_team.append(picker)
        elif picker == self.teams[0][0]:
            picking_team = self.teams[0]
        elif picker == self.teams[1][0]:
            picking_team = self.teams[1]
        else:
            raise PickError(translate('picker-not-captain', picker.display_name))

        # Check if it's picker's turn
        if picker != self._active_picker:
            raise PickError(translate('picker-not-turn', picker.display_name))

        # Prevent picks when team is full
        if len(picking_team) > len(self.members) // 2:
            raise PickError(translate('team-full', picker.display_name))

        self.members_left.remove(pickee)
        picking_team.append(pickee)
        self.pick_number += 1

    async def _update_menu(self, title):
        """ Update the message to reflect the current status of the team draft. """
        await self.edit(embed=self._picker_embed(title))

    async def _process_pick(self, reaction, member):
        """ Handler function for player pick reactions. """
        # Check that reaction is on this message and member is in the team draft
        if reaction.message.id != self.id or member == self.author:
            return

        # Check that picked player is in the player pool
        pick = self.pick_emojis.get(str(reaction.emoji), None)

        if pick is None or pick not in self.members_left or member not in self.members:
            await self.remove_reaction(reaction, member)
            return

        # Attempt to pick the player for the team
        try:
            self._pick_player(member, pick)
        except PickError as e:  # Player not picked
            await self.remove_reaction(reaction, member)
            title = e.message
        else:  # Player picked 
            await self.clear_reaction(reaction.emoji)
            title = translate('team-picked', member.display_name, pick.display_name)

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
        # Initialize 
        self.members_left = self.members.copy()  # Copy members to edit players remaining in the player pool
        self.players = await self.bot.api_helper.get_players([member.id for member in self.members])
        self.teams = [[], []]
        self.pick_number = 0
        captain_method = await self.bot.get_pug_data(self.channel.category, 'captain_method')

        if captain_method == 'rank':
            players = await self.bot.api_helper.get_players([member.id for member in self.members_left])
            players.sort(reverse=True, key=lambda x: x.score)

            for team in self.teams:
                captain = self.guild.get_member(players.pop(0).discord)
                self.members_left.remove(captain)
                team.append(captain)
        elif captain_method == 'random':
            temp_members = self.members_left.copy()
            shuffle(temp_members)

            for team in self.teams:
                captain = temp_members.pop()
                self.members_left.remove(captain)
                team.append(captain)
        elif captain_method == 'volunteer':
            pass
        else:
            raise ValueError(f'Captain method "{captain_method}" isn\'t valid')

        await self.edit(embed=self._picker_embed(translate('team-draft-begun')))

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


class MapVetoMenu(discord.Message):
    """ Message containing the components for a map veto. """

    def __init__(self, message, bot):
        """"""
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
        self.num_maps = 1
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

    def _veto_embed(self, title):
        """ Generate the menu embed based on the current status of the map bans. """
        embed = self.bot.embed_template(title=title)
        embed.set_footer(text=translate('map-veto-footer'))
        maps_str = ''

        if self.map_pool is not None and self.maps_left is not None:
            for m in self.map_pool:
                maps_str += f'{m.emoji}  {m.name}\n' if m.emoji in self.maps_left else f':heavy_multiplication_x:  ' \
                            f'~~{m.name}~~\n '

        status_str = ''

        if self.captains is not None and self._active_picker is not None:
            status_str += f'**{translate("capt1")}:** {self.captains[0].mention}\n'
            status_str += f'**{translate("capt2")}:** {self.captains[1].mention}\n\n'
            status_str += f'**{translate("current-capt")}:** {self._active_picker.mention}'

        embed.add_field(name=f'__{translate("maps-left")}__', value=maps_str)
        embed.add_field(name=f'__{translate("info")}__', value=status_str)
        return embed

    async def _process_ban(self, reaction, member):
        """ Handler function for map ban reactions. """
        # Check that reaction is on this message
        if reaction.message.id != self.id or member == self.author:
            return

        if member not in self.captains or str(reaction) not in [m for m in self.maps_left] or member != self._active_picker:
            await self.remove_reaction(reaction, member)
            return
        # Ban map if the emoji is valid
        try:
            map_ban = self.maps_left.pop(str(reaction))
        except KeyError:
            return

        self.ban_number += 1
        # Clear banned map reaction
        await self.clear_reaction(map_ban.emoji)
        # Edit message
        embed = self._veto_embed(translate('user-banned-map', member.display_name, map_ban.name))
        await self.edit(embed=embed)

        # Check if the veto is over
        if len(self.maps_left) == self.num_maps:
            if self.future is not None:
                self.future.set_result(None)

    async def veto(self, pool, captain_1, captain_2, num_maps):
        """"""
        # Initialize veto
        self.captains = [captain_1, captain_2]
        self.map_pool = pool
        self.maps_left = {m.emoji: m for m in self.map_pool}
        self.ban_number = 0
        self.num_maps = num_maps

        if len(self.map_pool) % 2 == 0:
            self.captains.reverse()

        # Edit input message and add emoji button reactions
        await self.edit(embed=self._veto_embed(translate('map-bans-begun')))

        awaitables = [self.add_reaction(m.emoji) for m in self.map_pool]
        await asyncio.gather(*awaitables, loop=self.bot.loop)

        # Add listener handlers and wait until there are no maps left to ban
        self.future = self.bot.loop.create_future()
        self.bot.add_listener(self._process_ban, name='on_reaction_add')
        await asyncio.wait_for(self.future, 600)
        self.bot.remove_listener(self._process_ban, name='on_reaction_add')
        await self.clear_reactions()

        picked_maps = list(self.maps_left.values())
        shuffle(picked_maps)

        return picked_maps


class ReadyMenu(discord.Message):
    def __init__(self, message, bot, members):
        """"""
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
        self.reactors = None
        self.future = None
        self.players = None

    def _ready_embed(self):
        """ Generate the menu embed based on the current ready status of players. """
        str_value = ''
        description = translate('react-ready', '✅')
        embed = self.bot.embed_template(title=translate('queue-filled'), description=description)

        for num, member in enumerate(self.members, start=1):
            if member not in self.reactors:
                str_value += f':heavy_multiplication_x:  {num}. [{member.display_name}]({self.players[num-1].league_profile})\n '
            else:
                str_value += f'✅  {num}. [{member.display_name}]({self.players[num-1].league_profile})\n '

        embed.add_field(name=f":hourglass: __{translate('player')}__",
                        value='-------------------\n' + str_value)
        return embed

    async def _process_ready(self, reaction, member):
        """ Track who has readied up. """
        # Check if this is a message we care about
        if reaction.message.id != self.id or member == self.author:
            return
        # Check if this is a member and reaction we care about
        if member not in self.members or reaction.emoji != '✅':
            await self.remove_reaction(reaction, member)
            return

        self.reactors.add(member)
        await self.edit(embed=self._ready_embed())

        if self.reactors.issuperset(self.members):
            if self.future is not None:
                self.future.set_result(None)

    async def ready_up(self):
        """"""
        self.reactors = set()
        self.future = self.bot.loop.create_future()
        self.players = await self.bot.api_helper.get_players([member.id for member in self.members])
        await self.edit(embed=self._ready_embed())
        await self.add_reaction('✅')

        self.bot.add_listener(self._process_ready, name='on_reaction_add')
        try:
            await asyncio.wait_for(self.future, 60)
        except asyncio.TimeoutError:
            pass

        self.bot.remove_listener(self._process_ready, name='on_reaction_add')
        
        return self.reactors


class MapVoteMenu(discord.Message):
    """"""

    def __init__(self, message, bot, members):
        """"""
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
        embed = self.bot.embed_template(title=translate('vote-map-started'))
        str_value = '--------------------\n'
        str_value += '\n'.join(
            f'{EMOJI_NUMBERS[self.map_votes[m.emoji]]} {m.emoji} {m.name} '
            f'{":small_orange_diamond:" if self.map_votes[m.emoji] == max(self.map_votes.values()) and self.map_votes[m.emoji] != 0 else ""} '
            for m in self.map_pool)
        embed.add_field(name=f':repeat_one: :map: __{translate("maps")}__', value=str_value)
        embed.set_footer(text=translate('vote-map-footer'))
        return embed

    async def _process_vote(self, reaction, member):
        """"""
        # Check that reaction is on this message and user is not the bot
        if reaction.message.id != self.id or member == self.author:
            return

        if member not in self.members or member in self.voted_members or str(reaction) not in [m.emoji for m in self.map_pool]:
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

        awaitables = [self.add_reaction(m.emoji) for m in self.map_pool]
        await asyncio.gather(*awaitables, loop=self.bot.loop)

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
        except discord.errors.NotFound:
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

        # Return class to original state after map veto is done
        self.voted_members = None
        self.map_votes = None
        self.future = None

        if len(winners_emoji) == 1:
            return self.map_pool
        elif len(winners_emoji) == 2 and self.tie_count == 1:
            return [choice(self.map_pool)]
        else:
            if len(winners_emoji) == 2:
                self.tie_count += 1
            return await self.vote(self.map_pool)


class MatchTypeVoteMenu(discord.Message):
    """"""

    def __init__(self, message, bot, captains):
        """"""
        # Copy all attributes from message object
        for attr_name in message.__slots__:
            try:
                attr_val = getattr(message, attr_name)
            except AttributeError:
                continue

            setattr(self, attr_name, attr_val)

        # Add custom attributes
        self.bot = bot
        self.numbers = EMOJI_NUMBERS[1:6]
        self.captains = captains
        self.voted_captains = {}
        self.future = None

    def _vote_embed(self):
        embed = self.bot.embed_template(title='Captains vote for number of maps')
        str_value = '------------\n'
        str_value += '\n'.join(
            f'{num}  Bo{self.numbers.index(num) + 1}'
            f'{":small_orange_diamond:" if self.num_votes[num] == max(self.num_votes.values()) and self.num_votes[num] != 0 else ""} '
            for num in self.numbers)
        embed.add_field(name=f':repeat_one:  __' + translate("match-type") + '__', value=str_value)
        embed.set_footer(text=translate('vote-match-type-footer'))
        return embed

    async def _process_vote(self, reaction, member):
        """"""
        # Check that reaction is on this message and user is not the bot
        if reaction.message.id != self.id or member == self.author:
            return

        if member not in self.captains or member in self.voted_captains or str(reaction) not in self.numbers:
            await self.remove_reaction(reaction, member)
            return

        self.num_votes[str(reaction)] += 1

        self.voted_captains[member] = str(reaction)
        await self.edit(embed=self._vote_embed())
        # Check if the voting is over
        if len(self.voted_captains) == len(self.captains):
            if self.future is not None:
                self.future.set_result(None)

    async def vote(self):
        """"""
        self.num_votes = {num: 0 for num in self.numbers}
        await self.edit(embed=self._vote_embed())

        awaitables = [self.add_reaction(num) for num in self.numbers]
        await asyncio.gather(*awaitables, loop=self.bot.loop)

        self.future = self.bot.loop.create_future()
        self.bot.add_listener(self._process_vote, name='on_reaction_add')

        try:
            await asyncio.wait_for(self.future, 60)
        except asyncio.TimeoutError:
            pass

        self.bot.remove_listener(self._process_vote, name='on_reaction_add')
        try:
            await self.clear_reactions()
        except discord.errors.NotFound:
            pass

        # Gather results
        winners_emoji = []
        winners_votes = 0

        for emoji, votes in self.num_votes.items():
            if votes > winners_votes:
                winners_emoji.clear()
                winners_emoji.append(emoji)
                winners_votes = votes
            elif votes == winners_votes:
                winners_emoji.append(emoji)

        if len(winners_emoji) <= 2:
            return self.numbers.index(winners_emoji[0]) + 1
        else:  # Force set Bo1 if no captains voted
            return 1
