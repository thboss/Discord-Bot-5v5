# 20201026_01_VKFFQ-add-multi-maps.py

from yoyo import step

__depends__ = {'20200513_01_kPWNp-create-base-tables'}


steps = [
    step(
        (
            'ALTER TABLE pugs\n'
            'ADD COLUMN count_maps SMALLINT DEFAULT 1;'
        ),
        (
            'ALTER TABLE pugs\n'
            'DROP COLUMN count_maps;'
        )
    )
]