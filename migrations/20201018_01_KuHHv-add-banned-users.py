# 20201018_01_KuHHv-add-banned-users.py

from yoyo import step

__depends__ = {'20200513_01_kPWNp-create-base-tables'}


steps = [
    step(
        (
            'CREATE TABLE guilds(\n'
            '    id BIGSERIAL PRIMARY KEY\n'
            ');'
        ),
        'DROP TABLE guilds;'
    ),
    step(
        (
            'CREATE TABLE banned_users(\n'
            '    guild_id BIGSERIAL REFERENCES guilds (id) ON DELETE CASCADE,\n'
            '    user_id BIGSERIAL REFERENCES users (id),\n'
            '    unban_time TIMESTAMP WITH TIME ZONE DEFAULT null,\n'
            '    CONSTRAINT banned_user_pkey PRIMARY KEY (guild_id, user_id)\n'
            ');'
        ),
        'DROP TABLE banned_users;'
    )
]