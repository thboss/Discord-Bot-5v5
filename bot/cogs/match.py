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
        emoji_numbers = [u'\u0031\u20E3',
                         u'\u0032\u20E3',
                         u'\u0033\u20E3',
                         u'\u0034\u20E3',
                         u'\u0035\u20E3',
                         u'\u0036\u20E3',
                         u'\u0037\u20E3',
                         u'\u0038\u20E3',
                         u'\u0039\u20E3',
                         u'\U0001F51F']
        self.pick_emojis = dict(zip(emoji_numbers, members))
        self.members_left = None
        self.teams = None
        self.future = None
        self.picking_count = 0
        self.picking_order = 'ABBAABBAAB'

    def _picker_embed(self, title):
        """ Generate the menu embed based on the current status of the team draft. """
        embed = self.bot.embed_template(title=title)
        embed.set_footer(text=self.bot.translate('team-pick-footer'))

        for team in self.teams:
            team_name = '__Team__' if len(team) == 0 else f'__Team {team[0].display_name}__'

            if len(team) == 0:
                team_players = self.bot.translate('empty')
            else:
                team_players = '\n'.join(p.display_name for p in team)

            embed.add_field(name=team_name, value=team_players)

        members_left_str = ''

        for emoji, member in self.pick_emojis.items():
            if not any(member in team for team in self.teams):
                members_left_str += f'{emoji}  {member.display_name}\n'
            else:
                members_left_str += f':heavy_multiplication_x:  ~~{member.display_name}~~\n'

        embed.insert_field_at(1, name=self.bot.translate('players-left'), value=members_left_str)
        return embed

    def _pick_player(self, picker, pickee):
        """ Process a team captain's player pick. """
        if any(team == [] for team in self.teams) and picker in self.members:
            picking_team = self.teams[self.teams.index([])]  # Get the first empty team
            if picker == pickee:
                raise PickError(self.bot.translate('picker-pick-self').format(picker.display_name))
            elif len(self.teams[0]) == 2 and len(self.teams[1]) == 0 and picker == self.teams[0][0]:
                raise PickError(self.bot.translate('picker-not-turn').format(picker.display_name))
            elif picker not in self.members_left:
                raise PickError(self.bot.translate('picker-not-captain').format(picker.display_name))
            else:
                self.members_left.remove(picker)
            picking_team.append(picker)
        elif picker == self.teams[0][0]:
            if self.picking_order[self.picking_count] == 'A':
                picking_team = self.teams[0]
            else:
                raise PickError(self.bot.translate('picker-not-turn').format(picker.display_name))
        elif picker == self.teams[1][0]:
            if self.picking_order[self.picking_count] == 'B':
                picking_team = self.teams[1]
            else:
                raise PickError(self.bot.translate('picker-not-turn').format(picker.display_name))
        elif picker in self.members:
            raise PickError(self.bot.translate('picker-not-captain').format(picker.display_name))
        else:
            raise PickError(self.bot.translate('picker-not-member').format(picker.display_name))

        if len(picking_team) > len(self.members) // 2:  # Team is full
            raise PickError(self.bot.translate('team-full').format(picker.display_name))

        if not picker == pickee:
            self.members_left.remove(pickee)
            picking_team.append(pickee)
            self.picking_count += 1

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

        await self._update_menu(title)

    async def draft(self):
        """ Start the team draft and return the teams after it's finished. """
        # Initialize draft
        self.members_left = self.members.copy()  # Copy members to edit players remaining in the player pool
        self.teams = [[], []]
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
        self.ban_order = '12121212'
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
            status_str += self.bot.translate('map-draft-capt1').format(self.captains[0].mention)
            status_str += self.bot.translate('map-draft-capt2').format(self.captains[1].mention)
            status_str += self.bot.translate('map-draft-current').format(self._active_picker.mention)

        embed.add_field(name=self.bot.translate('maps-left'), value=maps_str)
        embed.add_field(name=self.bot.translate('info'), value=status_str)
        return embed

    async def _update_menu(self, title):
        """ Update the message to reflect the current status of the map draft. """
        await self.edit(embed=self._draft_embed(title))
        awaitables = [self.clear_reaction(m.emoji) for m in self.map_pool if m.emoji not in self.maps_left]
        await asyncio.gather(*awaitables, loop=self.bot.loop)

    async def _process_ban(self, reaction, user):
        """ Handler function for map ban reactions. """
        # Check that reaction is on this message and user is a captain
        if reaction.message.id != self.id or user != self._active_picker:
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

        await self._update_menu(self.bot.translate('user-banned-map').format(user.display_name, map_ban.name))

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


class MapVoteMenu(discord.Message):
    """ Message containing the components for a map draft. """

    def __init__(self, message, bot, users):
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
        self.users = users
        self.voted_users = None
        self.map_pool = None
        self.map_votes = None
        self.future = None

    async def _process_vote(self, reaction, user):
        """"""
        # Check that reaction is on this message and user is a captain
        if reaction.message.id != self.id or user not in self.users:
            return

        # Add map vote if it is valid
        if user in self.voted_users:
            return
        try:
            self.map_votes[str(reaction)] += 1
        except KeyError:
            return

        self.voted_users.add(user)

        # Check if the voting is over
        if len(self.voted_users) == len(self.users):
            if self.future is not None:
                self.future.set_result(None)

    async def vote(self, mpool):
        """"""
        self.voted_users = set()
        self.map_pool = mpool
        self.map_votes = {m.emoji: 0 for m in self.map_pool}
        description = '\n'.join(f'{m.emoji} {m.name}' for m in self.map_pool)
        embed = self.bot.embed_template(title='Map vote started! (1 min)', description=description)
        embed.set_footer(text='React to either of the map icons below to vote for the corresponding map')
        await self.edit(embed=embed)

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

        self.map_pool = [m for m in self.bot.maps if m.emoji in winners_emoji]
        winners_maps = self.map_pool.copy()

        self.map_votes = None
        self.voted_users = None
        self.future = None
        self.map_pool = None

        if len(winners_emoji) == 1:
            return [m for m in winners_maps if m.emoji == winners_emoji[0]][0]
        else:
            return await self.vote(winners_maps)


class MatchCog(commands.Cog):
    """ Handles everything needed to create matches. """

    def __init__(self, bot):
        """ Set attributes. """
        self.bot = bot
        self.pending_ready_tasks = {}
        self.dict_ready_message = {}
        self.match_dict = {}
        self.moving_players = {}
        self.moving_players = defaultdict(lambda: False, self.moving_players)

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

    async def vote_maps(self, message, mpool, users):
        """"""
        menu = MapVoteMenu(message, self.bot, users)
        voted_map = await menu.vote(mpool)
        return voted_map

    async def random_map(self, mpool):
        """"""
        return random.choice(mpool)

    async def setup_match_channels(self, guild, match_id, team_one, team_two):
        """Create teams voice channels and move players inside"""
        team1_name = team_one[0].nick if team_one[0].nick is not None else team_one[0].display_name
        team2_name = team_two[0].nick if team_two[0].nick is not None else team_two[0].display_name

        match_category = await guild.create_category_channel(
            self.bot.translate('team-vs-team').format(team1_name, team2_name))
        role = discord.utils.get(guild.roles, name='@everyone')

        voice_channel_one = await guild.create_voice_channel(name=f'Team {team1_name}',
                                                             category=match_category,
                                                             user_limit=len(team_one))
        await voice_channel_one.set_permissions(role, connect=False, read_messages=True)

        voice_channel_two = await guild.create_voice_channel(name=f'Team {team2_name}',
                                                             category=match_category,
                                                             user_limit=len(team_two))
        await voice_channel_two.set_permissions(role, connect=False, read_messages=True)

        if guild not in self.match_dict:
            self.match_dict[guild] = {}

        self.match_dict[guild][match_id] = [match_category, voice_channel_one, voice_channel_two, team_one, team_two]

        channel_id = await self.bot.get_guild_data(guild, 'voice_lobby')
        voice_lobby = self.bot.get_channel(channel_id)

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
        channel_id = await self.bot.get_guild_data(message.guild, 'voice_lobby')
        voice_lobby = self.bot.get_channel(channel_id)
        ended_match = self.match_dict[message.guild][matchid]
        match_players = ended_match[3] + ended_match[4]

        role = discord.utils.get(voice_lobby.guild.roles, name='@everyone')

        voice_channel_end = await voice_lobby.guild.create_voice_channel(name=f'Match ID {matchid}',
                                                                         category=ended_match[0],
                                                                         user_limit=len(match_players))
        await voice_channel_end.set_permissions(role, connect=False, read_messages=True)

        for player in match_players:
            await voice_lobby.set_permissions(player, overwrite=None)

        for player in match_players:
            try:
                await player.move_to(voice_channel_end)
            except (AttributeError, discord.errors.HTTPException):
                pass

        await ended_match[1].delete()
        await ended_match[2].delete()
        await asyncio.sleep(60)
        await voice_channel_end.delete()
        await ended_match[0].delete()
        self.match_dict[message.guild].pop(matchid)

    @commands.Cog.listener()
    async def on_message(self, message):
        """ Listen to message in results channel and get ended match from webhooks message. """
        if len(message.embeds) < 1:
            return

        channel_id = await self.bot.get_guild_data(message.guild, 'text_results')
        if message.channel.id != channel_id:
            return

        panel_url = f'{self.bot.api_helper.base_url}/match/'
        if panel_url not in message.embeds[0].description:
            return

        match_id = re.findall('match/(\d+)', message.embeds[0].description)[0]

        try:
            if match_id in self.match_dict[message.guild]:
                await self.delete_match_channels(message, match_id)
        except KeyError:
            return

    async def start_match(self, ctx, members):
        """ Ready all the members up and start a match. """
        # Notify everyone to ready up
        member_mentions = [member.mention for member in members]
        ready_emoji = '✅'
        description = self.bot.translate('react-ready').format(chr(10).join(member_mentions), ready_emoji)
        burst_embed = self.bot.embed_template(title=self.bot.translate('queue-filled'), description=description)
        queue_cog = self.bot.get_cog('QueueCog')
        msg = queue_cog.last_queue_msgs.get(ctx.guild)
        channel_id = await self.bot.get_guild_data(ctx.guild, 'text_queue')
        text_channel = ctx.guild.get_channel(channel_id)

        if msg is not None:
            await msg.delete()
            queue_cog.last_queue_msgs.pop(ctx.guild)

        index_channel = ctx.guild.channels.index(text_channel)
        ready_message = await ctx.guild.channels[index_channel].send(''.join(member_mentions), embed=burst_embed)
        self.dict_ready_message[ctx.guild] = ready_message

        await ready_message.add_reaction(ready_emoji)

        reactors = set()  # Track who has readied up

        # Wait for everyone to ready up
        def all_ready(reaction, member):
            """ Check if all players in the queue have readied up. """
            # Check if this is a reaction we care about
            if reaction.message.id != ready_message.id or member not in members or reaction.emoji != ready_emoji:
                return False

            reactors.add(member)

            if reactors.issuperset(members):  # All queued members have reacted
                return True
            else:
                return False

        try:
            if ctx.guild in self.pending_ready_tasks:
                self.pending_ready_tasks[ctx.guild].close()

            self.pending_ready_tasks[ctx.guild] = self.bot.wait_for('reaction_add', timeout=60.0, check=all_ready)
            await self.pending_ready_tasks[ctx.guild]
        except asyncio.TimeoutError:  # Not everyone readied up
            unreadied = set(members) - reactors
            awaitables = [
                ready_message.clear_reactions(),
                self.bot.db_helper.delete_queued_users(ctx.guild.id, *(member.id for member in unreadied))
            ]
            await asyncio.gather(*awaitables, loop=self.bot.loop)
            description = '\n'.join(':heavy_multiplication_x:  ' + member.mention for member in unreadied)
            title = self.bot.translate('not-all-ready')
            burst_embed = self.bot.embed_template(title=title, description=description)
            burst_embed.set_footer(text=self.bot.translate('not-ready-removed'))
            # disconnect unreadied players from the lobby voice channel
            self.moving_players[ctx.guild] = True
            for player in unreadied:
                try:
                    await player.move_to(None)
                except (AttributeError, discord.errors.HTTPException):
                    pass

            await ready_message.edit(embed=burst_embed)
            self.moving_players[ctx.guild] = False
            return False  # Not everyone readied up
        else:  # Everyone readied up
            if ctx.guild in self.pending_ready_tasks:
                self.pending_ready_tasks.pop(ctx.guild)
            # Attempt to make teams and start match
            awaitables = [
                ready_message.clear_reactions(),
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
                team_one, team_two = await self.draft_teams(ready_message, members)
            else:
                raise ValueError(self.bot.translate('team-method-not-valid').format(team_method))

            await asyncio.sleep(1)
            # Get map pick
            if map_method == 'captains':
                map_pick = await self.draft_maps(ready_message, mpool, team_one[0], team_two[0])
            elif map_method == 'vote':
                map_pick = await self.vote_maps(ready_message, mpool, members)
            elif map_method == 'random':
                map_pick = await self.random_map(mpool)
            else:
                raise ValueError(self.bot.translate('map-method-not-valid').format(map_method))

            await asyncio.sleep(1)
            burst_embed = self.bot.embed_template(description=self.bot.translate('fetching-server'))
            await ready_message.edit(embed=burst_embed)

            self.moving_players[ctx.guild] = True
            # Check if able to get a match server and edit message embed accordingly
            try:
                match = await self.bot.api_helper.start_match(team_one, team_two,
                                                              map_pick.dev_name)  # Request match from API
            except aiohttp.ClientResponseError as e:
                description = self.bot.translate('no-servers')
                burst_embed = self.bot.embed_template(title=self.bot.translate('problem'), description=description)
                await ready_message.delete()
                self.dict_ready_message.pop(ctx.guild)
                await ctx.guild.channels[index_channel].send(embed=burst_embed)
                self.moving_players[ctx.guild] = False
                traceback.print_exception(type(e), e, e.__traceback__, file=sys.stderr)  # Print exception to stderr
                return False
            else:
                await asyncio.sleep(5)
                match_id = str(match.get_match_id)
                description = self.bot.translate('server-connect').format(match.connect_url, match.connect_command,
                                                                          map_pick.name, map_pick.emoji, match_id)
                burst_embed = self.bot.embed_template(title=self.bot.translate('server-ready'), description=description)
                burst_embed.set_thumbnail(url=map_pick.image_url)
                burst_embed.add_field(name=self.bot.translate('team-name').format(team_one[0].display_name),
                                      value='\n'.join(member.mention for member in team_one))
                burst_embed.add_field(name=self.bot.translate('team-name').format(team_two[0].display_name),
                                      value='\n'.join(member.mention for member in team_two))
                burst_embed.set_footer(text=self.bot.translate('server-message-footer'))

            await ready_message.delete()
            self.dict_ready_message.pop(ctx.guild)
            await ctx.guild.channels[index_channel].send(embed=burst_embed)
            await self.setup_match_channels(ctx.guild, match_id, team_one, team_two)
            self.moving_players[ctx.guild] = False

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
            inactive_maps = self.bot.translate('none')

        embed.add_field(name=self.bot.translate('active-maps'), value=active_maps)
        embed.add_field(name=self.bot.translate('inactive-maps'), value=inactive_maps)
        await ctx.send(embed=embed)

    @teams.error
    @captains.error
    @maps.error
    async def config_error(self, ctx, error):
        """ Respond to a permissions error with an explanation message. """
        if isinstance(error, commands.MissingPermissions):
            await ctx.trigger_typing()
            missing_perm = error.missing_perms[0].replace('_', ' ')
            title = self.bot.translate('cannot-set').format(ctx.command.name, missing_perm)
            embed = self.bot.embed_template(title=title)
            await ctx.send(embed=embed)
