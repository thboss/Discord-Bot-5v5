# 20200923_01_DKHHX-add-spect_users-table.py

from yoyo import step
import os

__depends__ = {'20200513_01_kPWNp-create-base-tables'}


steps = [
    step(
        (
            'CREATE TABLE spect_users(\n'
            '    guild_id BIGSERIAL REFERENCES leagues (id) ON DELETE CASCADE,\n'
            '    user_id BIGSERIAL REFERENCES users (id),\n'
            '    CONSTRAINT spect_user_pkey PRIMARY KEY (guild_id, user_id)\n'
            ');'
        ),
        'DROP TABLE spect_users;'
    )
]