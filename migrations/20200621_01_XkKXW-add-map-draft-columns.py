# 20200621_01_XkKXW-add-map-draft-columns.py

from yoyo import step
import os

__depends__ = {'20200513_01_kPWNp-create-base-tables'}
 
maps = [icon.split('-')[1].split('.')[0] for icon in os.listdir('assets/maps/icons/')]
add_maps = 'ALTER TABLE guilds\n'
drop_maps = 'ALTER TABLE guilds\n'

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
            'ALTER TABLE guilds\n'
            'ADD COLUMN map_method map_method DEFAULT \'captains\';'
        ),
        (
            'ALTER TABLE guilds\n'
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