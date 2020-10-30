# Forked from [csgo-queue-bot](https://github.com/cameronshinn/csgo-queue-bot)

## Description
- A Discord bot that allows setting up CS:GO PUGs and play with friends with easy setup matches and super smooth.


## Features
- Authentication player's Discord account with their Steam throght WEB API.
- Multiple queues per guild.
- Multiple matches at time.
- Multiple Servers.
- Multi-maps per match.
- Choice gameserver region.
- Join/Leave the queue based on lobby voice channel.
- Queue ready up system.
- Random/Ranked/Volunteer picking captains methods..
- Random/teambalance/captains picking teams methods.
- Random/Vote/Veto picking map methods.
- Add/Remove maps pool.
- Auto create teams channels.
- Auto delete teams channels on match end.
- Force end matches.
- Rank system.
- Ban system.
- Translations file.

## Requirements
1. [Web API](https://github.com/thboss/csgo-league-web)

2. [Gameserver Plugins](https://github.com/thboss/csgo-league-game)

3. Python3.6+


## Setup
1. First you must have a bot instance to run this script on. Follow Discord's tutorial [here](https://discord.onl/2019/03/21/how-to-set-up-a-bot-application/) on how to set one up. Be sure to invite it to a server before launch the bot.

   * The required permissions is `administrator`.
   * Enable the "server members intent" for your bot, as shown [here](https://discordpy.readthedocs.io/en/latest/intents.html#privileged-intents).

2. Setup and get an API token for the CS:GO League [web API](https://github.com/thboss/csgo-league-web) along with the host base URL.

3. Install libpq-dev (Linux only?). This is needed to install the psycopg2 Python package.

    * Linux command is `sudo apt-get install libpq-dev`.

4. Run `pip3 install -r requirements.txt` in the repository's root directory to get the necessary libraries.

5. Install PostgreSQL 9.5 or higher.

    * Linux command is `sudo apt-get install postgresql`.
    * Windows users can download [here](https://www.postgresql.org/download/windows).

6. Run the psql tool with `sudo -u postgres psql` and create a database by running the following commands:

    ```sql
    CREATE ROLE csgoleague WITH LOGIN PASSWORD 'yourpassword';
    CREATE DATABASE csgoleague OWNER csgoleague;
    ```

    Be sure to replace `'yourpassword'` with your own desired password.

    Quit psql with `\q`

7. Create an environment file named `.env` with in the repository's root directory. Fill this template with the requisite information you've gathered...

    ```py
    DISCORD_BOT_TOKEN= #Bot token from the Discord developer portal
    DISCORD_LEAGUE_LANGUAGE= # Bot language (key from translations.json), E.g. "en"
    DISCORD_LEAGUE_REGIONS= # game server regions, ex. "EU,USA,ASIA"
    DISCORD_LEAGUE_LEFT_TIME= # allowed time in minutes before ban the player for leaving them team channel (set 0 to disable ban system)
    DISCORD_LEAGUE_COOLDOWN= # ban time on left team channels, ex. "0d 1h 0m" (days/hours/minutes)
    DISCORD_LEAGUE_CANCEL_MATCH= # Cancel the match when players leave them team channel (empty to disable)

    CSGO_LEAGUE_API_KEY= # API from the CS:GO League web backend .env file
    CSGO_LEAGUE_API_URL= # URL where the web panel is hosted

    POSTGRESQL_USER= # "csgoleague" (if you used the same username)
    POSTGRESQL_PASSWORD= # The DB password you set
    POSTGRESQL_DB= # "csgoleague" (if you used the same DB name)
    POSTGRESQL_HOST= # The IP address of the DB server (127.0.0.1 if running on the same system as the bot)
    POSTGRESQL_PORT=5432
    ```


8. Apply the database migrations by running `python3 migrate.py up`.

9. Run the launcher Python script by running, `python3 launcher.py`.


## How to play

1. Type `q!create <League name>` to create new League and the bot automatically will create these channels:
    * name_queue :    view queue progress.
    * name_commands : bot commands are restrict in this channel.
    * name_lobby :    players must join this channel to add to the queue
    * name_prelobby :    move unreadied players to this channel

2. Type `q!link` in the commands channel and you will get DM has a link.

3. Open that link and log in with Steam to connect your account to League system.

4. Once linked, type `q!check`  in the commands channel to get the verified role.

5. Join Lobby voice channel and wait fills up the queue.

6. Bot automatically create teams channels and move players into.

7. Once match over, Bot remove teams channels.

#### NOTES
1. How to add new maps to the map pool?
      * Empty the database by running `python3 migrate.py down`.
      * Add map icon (.png) to `assets/maps/icons/` and rename it like `Dust II-de_dust`.
      * Apply the new database migrations by running `python3 migrate.py up`.

2. You can rename roles and channels that bot create it.

## Commands

### Admin commands

`q!create <name>` **-** Create a new PUG <br>

`q!delete` **-** Delete the PUG <br>

`q!forcelink <mention> <SteamId64>` **-** Force link a player on the backend <br>

`q!unlink <mention>` **-**  Unlink a player on the backend <br>

`q!region <region>` **-** Set the game server region <br>

`q!remove <mention>` **-** Remove the mentioned user from the queue <br>

`q!empty` **-** Empty the queue <br>

`q!cap <integer>` **-** Set the capacity of the queue to the specified value <br>

`q!teams <random|autobalance|captains>` **-** Set the team creation method <br>

`q!addspect` **-** Add player to the spectators <br>

`q!removespect` **-** Remove player from the spectators <br>

`q!captains <rank|random|volunteer>` **-** Set the captain selection method <br>

`q!pickmaps <random|vote|captains>` **-** Set the map selection method <br>

`q!countmaps <number>` **-** Set count maps per match <br>

`q!mpool {+|-}<map name>` **-** Add/Remove maps to default map pool <br>

`q!end <match id>` **-** Force end live match <br>


### Player commands

`q!link` **-**  Link a player on the backend <br>

`q!check` **-** Check if the player has been linked his account and give him role if so <br>

`q!stats` **-** See your stats <br>

`q!leaders` **-** See the top players in the server <br>

`q!spectators` **-** View the spectators <br>
