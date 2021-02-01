# queue.py

from discord.ext import commands, tasks
from discord.errors import NotFound, HTTPException
from discord.utils import get
from collections import defaultdict
from datetime import datetime, timezone
import asyncio

from bot.helpers.utils import translate, timedelta_str


class QueueCog(commands.Cog):
    """ Cog to manage queues of players among multiple servers. """

    def __init__(self, bot):
        """ Set attributes. """
        self.bot = bot
        self.last_queue_msgs = {}
        self.block_lobby = {}
        self.block_lobby = defaultdict(lambda: False, self.block_lobby)

    async def queue_embed(self, category, title=None):
        """ Method to create the queue embed for a guild. """
        queued_ids = await self.bot.db_helper.get_queued_users(category.id)
        capacity = await self.bot.get_league_data(category, 'capacity')
        
        if len(queued_ids) > 1:
            players = await self.bot.api_helper.get_players(queued_ids)
        elif len(queued_ids) == 1:
            players = [await self.bot.api_helper.get_player(queued_ids[0])]

        if title:
            title += f' ({len(queued_ids)}/{capacity})'

        if len(queued_ids) == 0:  # If there are no members in the queue
            queue_str = f'_{translate("queue-is-empty")}_'
        else:  # members still in queue
            queue_str = ''.join(
                f'{num}. [{category.guild.get_member(member_id).display_name}]({players[num - 1].league_profile})\n'
                for num, member_id in enumerate(queued_ids, start=1))

        embed = self.bot.embed_template(title=title, description=queue_str)
        embed.set_footer(text=translate('receive-notification'))
        return embed

    async def update_last_msg(self, category, embed):
        """ Send embed message and delete the last one sent. """
        try:
            msg = self.last_queue_msgs.get(category)
        except:
            msg = None

        try:
            queue_id = await self.bot.get_league_data(category, 'text_queue')
        except:
            queue_id = None

        queue_channel = category.guild.get_channel(queue_id)

        try:
            await msg.edit(embed=embed)
        except (AttributeError, NotFound):
            self.last_queue_msgs[category] = await queue_channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if before.channel == after.channel:
            return

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

        if before.channel == before_lobby is not None:
            if self.block_lobby[before_lobby.category]:
                return

            removed = await self.bot.db_helper.delete_queued_users(before_lobby.category_id, member.id)

            if member.id in removed:
                title = translate('removed-from-queue', member.display_name)
            else:
                title = translate('not-in-queue', member.display_name)

            embed = await self.queue_embed(before_lobby.category, title)
            # Update queue display message
            await self.update_last_msg(before_lobby.category, embed)

        if after.channel == after_lobby is not None:
            if self.block_lobby[after_lobby.category]:
                return

            if not await self.bot.api_helper.is_linked(member.id):  # Message author isn't linked
                title = translate('account-not-linked', member.display_name)
            else:  # Message author is linked
                if not self.check_unbans.is_running():
                    self.check_unbans.start()

                awaitables = []
                for league_id in await self.bot.db_helper.get_guild_leagues(after_lobby.guild.id):
                    if league_id != after_lobby.category.id:
                        awaitables.append(self.bot.db_helper.get_queued_users(league_id))
                results = await asyncio.gather(*awaitables, loop=self.bot.loop)

                others_queue_ids = []
                for queue_ids in results:
                    others_queue_ids.extend(queue_ids)

                awaitables = [
                    self.bot.api_helper.get_player(member.id),
                    self.bot.db_helper.insert_users(member.id),
                    self.bot.db_helper.get_queued_users(after_lobby.category_id),
                    self.bot.get_league_data(after_lobby.category, 'capacity'),
                    self.bot.db_helper.get_spect_users(after_lobby.category_id),
                    self.bot.db_helper.get_banned_users(after_lobby.guild.id)
                ]
                results = await asyncio.gather(*awaitables, loop=self.bot.loop)
                player = results[0]
                queue_ids = results[2]
                capacity = results[3]
                spect_ids = results[4]
                banned_users = results[5]

                if member.id in banned_users:  # Author is banned from joining the queue
                    title = translate('is-banned', member.display_name)
                    unban_time = banned_users[member.id]
                    if unban_time is not None:  # If the user is banned for a duration
                        title += f' for {timedelta_str(unban_time - datetime.now(timezone.utc))}'
                elif member.id in queue_ids:  # Author already in queue
                    title = translate('already-in-queue', member.display_name)
                elif member.id in others_queue_ids:
                    title = f'Player **{member.display_name}** is already in another queue'
                elif member.id in spect_ids:  # Player in the spectators
                    title = translate('in-spectators', member.display_name)
                elif len(queue_ids) >= capacity:  # Queue full
                    title = translate('queue-is-full', member.display_name)
                elif not player:  # ApiHelper couldn't get player
                    title = translate('cannot-verify-match', member.display_name)
                elif player.in_match:  # member is already in a match
                    title = translate('already-in-match', member.display_name)
                else:  # member can be added
                    await self.bot.db_helper.insert_queued_users(after_lobby.category_id, member.id)
                    queue_ids += [member.id]
                    title = translate('added-to-queue', member.display_name)

                    # Check and burst queue if full
                    if len(queue_ids) == capacity:
                        self.block_lobby[after_lobby.category] = True
                        match_cog = self.bot.get_cog('MatchCog')
                        linked_role_id = await self.bot.get_guild_data(after_lobby.guild, 'linked_role')
                        linked_role = member.guild.get_role(linked_role_id)
                        queue_members = [member.guild.get_member(member_id) for member_id in queue_ids]
                        awaitables = [after_lobby.set_permissions(linked_role, connect=False)]

                        for league_id in await self.bot.db_helper.get_guild_leagues(after_lobby.guild.id):
                            lobby_id = await self.bot.get_league_data(self.bot.get_channel(league_id), 'voice_lobby')
                            lobby = self.bot.get_channel(lobby_id)
                            for member in queue_members:
                                awaitables.append(lobby.set_permissions(member, connect=False))
                        await asyncio.gather(*awaitables, loop=self.bot.loop, return_exceptions=True)

                        all_readied = await match_cog.start_match(after_lobby.category, queue_members)

                        if all_readied:
                            await self.bot.db_helper.delete_queued_users(after_lobby.category_id, *queue_ids)

                        if match_cog.no_servers[after_lobby.category]:
                            await self.bot.db_helper.delete_queued_users(after_lobby.category_id, *queue_ids)
                            prematch_id = await self.bot.get_guild_data(after_lobby.guild, 'prematch_channel')
                            prematch = after_lobby.guild.get_channel(prematch_id)

                            awaitables = []
                            for member in queue_members:
                                awaitables.append(member.move_to(prematch))

                            match_cog.no_servers[after_lobby.category] = False

                            for league_id in await self.bot.db_helper.get_guild_leagues(after_lobby.guild.id):
                                lobby_id = await self.bot.get_league_data(self.bot.get_channel(league_id), 'voice_lobby')
                                lobby = self.bot.get_channel(lobby_id)
                                for member in queue_members:
                                    awaitables.append(lobby.set_permissions(member, overwrite=None))
                            await asyncio.gather(*awaitables, loop=self.bot.loop, return_exceptions=True)

                        self.block_lobby[after_lobby.category] = False

                        await after_lobby.set_permissions(linked_role, connect=True)
                        title = translate('players-in-queue')
                        embed = await self.queue_embed(after_lobby.category, title)
                        await self.update_last_msg(after_lobby.category, embed)
                        return

            embed = await self.queue_embed(after_lobby.category, title)
            # Delete last queue message
            await self.update_last_msg(after_lobby.category, embed)

    @tasks.loop(seconds=30.0)
    async def check_unbans(self):
        banned_users = False
        for guild in self.bot.guilds:
            guild_bans = bool(await self.bot.db_helper.get_banned_users(guild.id))
            if guild_bans:
                banned_users = True
                break

        if banned_users:
            unbanned_users = {}
            for guild in self.bot.guilds:
                guild_unbanned_users = await self.bot.db_helper.get_unbanned_users(guild.id)
                unbanned_users[guild] = guild_unbanned_users
            
            for guild, member_ids in unbanned_users.items():
                members = [get(guild.members, id=member_id) for member_id in member_ids]
                banned_role_id = await self.bot.get_guild_data(guild, 'banned_role')
                ban_role = guild.get_role(banned_role_id)
                for member in members:
                    await member.remove_roles(ban_role)
        else:
            self.check_unbans.cancel()
