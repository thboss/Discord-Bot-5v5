# 20200513_01_kPWNp-create-base-tables.py

from yoyo import step

__depends__ = {}

steps = [
    step(
        'CREATE TYPE team_method AS ENUM(\'captains\', \'autobalance\', \'random\');',
        'DROP TYPE team_method;'
    ),
    step(
        'CREATE TYPE captain_method AS ENUM(\'volunteer\', \'rank\', \'random\');',
        'DROP TYPE captain_method;'
    ),
    step(
        (
            'CREATE TABLE guilds(\n'
            '    id BIGSERIAL PRIMARY KEY,\n'
            '    capacity SMALLINT DEFAULT 10,\n'
            '    team_method team_method DEFAULT \'captains\',\n'
            '    captain_method captain_method DEFAULT \'volunteer\',\n'
            '    category BIGINT DEFAULT NULL,\n'
            '    pug_role BIGINT DEFAULT NULL,\n'
            '    alerts_role BIGINT DEFAULT NULL,\n'
            '    text_queue BIGINT DEFAULT NULL,\n'
            '    text_commands BIGINT DEFAULT NULL,\n'
            '    text_results BIGINT DEFAULT NULL,\n'
            '    voice_lobby BIGINT DEFAULT NULL\n'            
            ');'
        ),
        'DROP TABLE guilds;'
    ),
    step(
        (
            'CREATE TABLE users('
            '    id BIGSERIAL PRIMARY KEY'
            ');'
        ),
        'DROP TABLE users;'
    ),
    step(
        (
            'CREATE TABLE queued_users(\n'
            '    guild_id BIGSERIAL REFERENCES guilds (id) ON DELETE CASCADE,\n'
            '    user_id BIGSERIAL REFERENCES users (id),\n'
            '    CONSTRAINT queued_user_pkey PRIMARY KEY (guild_id, user_id)\n'
            ');'
        ),
        'DROP TABLE queued_users;'
    ),
]
