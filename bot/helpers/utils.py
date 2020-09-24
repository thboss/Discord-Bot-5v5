# utils.py

import math
import os
import json


with open('translations.json', 'r') as f:
    translations = json.load(f)


def translate(text):
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
