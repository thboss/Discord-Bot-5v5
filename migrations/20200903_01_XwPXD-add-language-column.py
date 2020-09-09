# 20200903_01_XwPXD-add-language-column.py

from yoyo import step

__depends__ = {'20200513_01_kPWNp-create-base-tables'}

steps = [
    step(
        (
            'ALTER TABLE guilds\n'
            'ADD COLUMN language VARCHAR(20) NOT NULL DEFAULT \'en\';'
        ),
        (
            'ALTER TABLE guilds\n'
            'DROP COLUMN language;'
        )
    )
]