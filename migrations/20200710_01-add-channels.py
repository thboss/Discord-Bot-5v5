# 20200710_01_XkKXW-add-channels.py

from yoyo import step

__depends__ = {'20200513_01_kPWNp-create-base-tables'}

steps = [
    step(
        (
            'ALTER TABLE guilds\n'
            'ADD COLUMN category BIGINT DEFAULT NULL,\n'
            'ADD COLUMN pug_role BIGINT DEFAULT NULL,\n'
            'ADD COLUMN alerts_role BIGINT DEFAULT NULL,\n'
            'ADD COLUMN text_queue BIGINT DEFAULT NULL,\n'
            'ADD COLUMN text_commands BIGINT DEFAULT NULL,\n'
            'ADD COLUMN text_results BIGINT DEFAULT NULL,\n'
            'ADD COLUMN voice_lobby BIGINT DEFAULT NULL;'
        ),
        (
            'ALTER TABLE guilds\n'
            'DROP COLUMN category,\n'
            'DROP COLUMN pug_role,\n'
            'DROP COLUMN alerts_role,\n'
            'DROP COLUMN text_queue,\n'
            'DROP COLUMN text_commands,\n'
            'DROP COLUMN text_results,\n'
            'DROP COLUMN voice_lobby;'
        )
    )
]