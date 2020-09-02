# Forked from [csgo-league-bot](https://github.com/csgo-league/csgo-league-bot)

## Requirements
1. [Web API](https://github.com/thboss/csgo-league-web)

2. [Server Plugins](https://github.com/thboss/csgo-league-game)

## Setup
1. First you must have a bot instance to run this script on. Follow Discord's tutorial [here](https://discord.onl/2019/03/21/how-to-set-up-a-bot-application/) on how to set one up. Be sure to invite it to a server before launch the bot.

   * The required permissions is `administrator`.

2. Setup and get an API token for the CS:GO League [web API](https://github.com/thboss/csgo-league-web) along with the host base URL.

3. Install libpq-dev (Linux only?). This is needed to install the psycopg2 Python package.

    * Linux command is `sudo apt-get install libpq-dev`.

3. Run `pip3 install -r requirements.txt` in the repository's root directory to get the necessary libraries.

    * Note that python-Levenshtein requires your system to have a C++ compiler (Visual Studio C++ compiler for Windows or g++ for Linux). This library may be replaced in the future to eliminate this requirement.

4. Install PostgreSQL 9.5 or higher.

    * Linux command is `sudo apt-get install postgresql`.
    * Windows users can download [here](https://www.postgresql.org/download/windows).

5. Run the psql tool with `sudo -u postgres psql` and create a database by running the following commands:

    ```sql
    CREATE ROLE csgoleague WITH LOGIN PASSWORD 'yourpassword';
    CREATE DATABASE csgoleague OWNER csgoleague;
    ```

    Be sure to replace `'yourpassword'` with your own desired password.

    Quit psql with `\q`

5. Create an environment file named `.env` with in the repository's root directory. Fill this template with the requisite information you've gathered...

    ```py
    DISCORD_BOT_TOKEN= #Bot token from the Discord developer portal
    DISCORD_LEAGUE_LANGUAGE= # Bot language (key from translations.json), E.g. "en"

    CSGO_LEAGUE_API_KEY= # API from the CS:GO League web backend .env file
    CSGO_LEAGUE_API_URL= # URL where the web panel is hosted

    POSTGRESQL_USER= # "csgoleague" (if you used the same username)
    POSTGRESQL_PASSWORD= # The DB password you set
    POSTGRESQL_DB= # "csgoleague" (if you used the same DB name)
    POSTGRESQL_HOST= # The IP address of the DB server (127.0.0.1 if running on the same system as the bot)
    ```


6. Apply the database migrations by running `python3 migrate.py up`.

7. Run the launcher Python script by running, `python3 launcher.py`.


## Commands

### Admin commands

`q!remove <mention>` **-** Remove the mentioned user from the queue <br>

`q!empty` **-** Empty the queue <br>

`q!cap <integer>` **-** Set the capacity of the queue to the specified value <br>

`q!teams <random|autobalance|captains>` **-** Set the team creation method <br>

`q!captains <rank|random|volunteer>` **-** Set the captain selection method <br>

`q!maps <random|vote|captains>` **-** Set the map selection method <br>

`q!mpool {+|-}<map name>` **-** Add/Remove maps to default map pool <br>

`q!end <match id>` **-** Force end live match <br>


### Player commands

`q!link` **-**  Link a player on the backend <br>

`q!unlink` **-**  Unlink a player on the backend <br>

`q!alerts <on|off>` **-** Enable/Disable alerts about remaining players to fill up the queue <br>

`q!stats` **-** See your stats <br>

`q!leaders` **-** See the top players in the server <br>

`q!check` **-** Check if the player has been linked his account and give him role if so <br>
