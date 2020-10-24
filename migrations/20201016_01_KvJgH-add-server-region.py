# 20201016_01_KvJgH-add-server-region.py

from yoyo import step

__depends__ = {'20200513_01_kPWNp-create-base-tables'}


steps = [
    step(
        (
            'ALTER TABLE pugs\n'
            'ADD COLUMN region VARCHAR(20) NOT NULL DEFAULT \'EU\';'
        ),
        (
            'ALTER TABLE pugs\n'
            'DROP COLUMN region;'
        )
    )
]