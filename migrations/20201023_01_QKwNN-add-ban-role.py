# 20201023_01_QKwNN-add-ban-role.py

from yoyo import step

__depends__ = {'20200513_01_kPWNp-create-base-tables'}


steps = [
    step(
        (
            'ALTER TABLE guilds\n'
            'ADD COLUMN ban_role BIGINT DEFAULT NULL;'
        ),
        (
            'ALTER TABLE guilds\n'
            'DROP COLUMN ban_role;'
        )
    )
]