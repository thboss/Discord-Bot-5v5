# utils.py

import math
import os
import re
import json
import asyncio

from dotenv import load_dotenv


time_arg_pattern = re.compile(r'\b((?:(?P<days>[0-9]+)d)|(?:(?P<hours>[0-9]+)h)|(?:(?P<minutes>[0-9]+)m))\b')

load_dotenv()

with open('translations.json', encoding="utf8") as f:
    translations = json.load(f)


def translate(text, *args):
    if args:
        try:
            return translations[os.environ['DISCORD_LEAGUE_LANGUAGE']][text].format(*args)
        except (KeyError, ValueError):
            return translations['en'][text].format(*args)
    else:
        try:
            return translations[os.environ['DISCORD_LEAGUE_LANGUAGE']][text]
        except (KeyError, ValueError):
            return translations['en'][text]


def align_text(text, length, align='center'):
    """ Center the text within whitespace of input length. """
    if length < len(text):
        return text

    whitespace = length - len(text)

    if align == 'center':
        pre = math.floor(whitespace / 2)
        post = math.ceil(whitespace / 2)
    elif align == 'left':
        pre = 0
        post = whitespace
    elif align == 'right':
        pre = whitespace
        post = 0
    else:
        raise ValueError('Align argument must be "center", "left" or "right"')

    return ' ' * pre + text + ' ' * post


class Map:
    """ A group of attributes representing a map. """

    def __init__(self, name, dev_name, emoji, image_url):
        """ Set attributes. """
        self.name = name
        self.dev_name = dev_name
        self.emoji = emoji
        self.image_url = image_url
