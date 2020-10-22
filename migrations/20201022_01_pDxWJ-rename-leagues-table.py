# 20201022_01_pDxWJ-rename-leagues-table.py

from yoyo import step

__depends__ = {'20200513_01_kPWNp-create-base-tables'}


steps = [
    step(
        (
            'ALTER TABLE leagues\n'
            'RENAME TO pugs;'
        )
    )
]