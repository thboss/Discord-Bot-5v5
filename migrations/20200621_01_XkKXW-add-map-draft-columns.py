# 20200621_01_XkKXW-add-map-draft-columns.py

from yoyo import step
import os

__depends__ = {'20200513_01_kPWNp-create-base-tables'}

icons_dic = 'assets/maps/icons/'
maps = [icon.split('-')[1].split('.')[0] for icon in os.listdir(icons_dic) if icon.endswith('.png') and '-' in icon and os.stat(icons_dic + icon).st_size < 256000]
add_maps = drop_maps = 'ALTER TABLE leagues\n'
m = os.listdir('assets/maps/icons/')

for i, _map in enumerate(maps):
    if i+1 != len(maps):
        add_maps += f'ADD COLUMN {_map} BOOL NOT NULL DEFAULT true,\n'
    else:
        add_maps += f'ADD COLUMN {_map} BOOL NOT NULL DEFAULT true;'

for i, _map in enumerate(maps):
    if i+1 != len(maps):
        drop_maps += f'DROP COLUMN {_map},\n'
    else:
        drop_maps += f'DROP COLUMN {_map};'

steps = [
    step(
        'CREATE TYPE map_method AS ENUM(\'captains\', \'vote\', \'random\');',
        'DROP TYPE map_method;'
    ),
    step(
        (
            'ALTER TABLE leagues\n'
            'ADD COLUMN map_method map_method DEFAULT \'captains\';'
        ),
        (
            'ALTER TABLE leagues\n'
            'DROP COLUMN map_method;'
        )
    ),
    step(
        (
            add_maps
        ),
        (
            drop_maps
        )
    )
]