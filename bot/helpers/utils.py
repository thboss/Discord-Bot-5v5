# utils.py

import math
import os
import re
import json
import asyncio

from datetime import datetime, timedelta, timezone
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


def timedelta_str(tdelta):
    """ Convert time delta object to a worded string representation with only days, hours and minutes. """
    conversions = (('days', 86400), ('hours', 3600), ('minutes', 60))
    secs_left = int(tdelta.total_seconds())
    unit_strings = []

    for unit, conversion in conversions:
        unit_val, secs_left = divmod(secs_left, conversion)

        if unit_val != 0 or (unit == 'minutes' and len(unit_strings) == 0):
            unit_strings.append(f'{unit_val} {unit}')

    return ', '.join(unit_strings)

def unbantime(arg):
    # Parse the time arguments
    time_units = ('days', 'hours', 'minutes')
    time_delta_values = {}  # Holds the values for each time unit arg

    for match in time_arg_pattern.finditer(arg):  # Iterate over the time argument matches
        for time_unit in time_units:  # Figure out which time unit this match is for
            time_value = match.group(time_unit)  # Get the value for this unit

            if time_value is not None:  # Check if there is an actual group value
                time_delta_values[time_unit] = int(time_value)
                break  # There is only ever one group value per match

    # Set unban time if there were time arguments
    time_delta = timedelta(**time_delta_values)
    unban_time = None if time_delta_values == {} else datetime.now(timezone.utc) + time_delta
    return time_delta, unban_time


class Timer:
    def __init__(self, timeout, callback):
        self._timeout = timeout
        self._callback = callback
        self._task = asyncio.ensure_future(self._job())

    async def _job(self):
        await asyncio.sleep(self._timeout)
        await self._callback()

    def cancel(self):
        self._task.cancel()


class Map:
    """ A group of attributes representing a map. """

    def __init__(self, name, dev_name, emoji, image_url):
        """ Set attributes. """
        self.name = name
        self.dev_name = dev_name
        self.emoji = emoji
        self.image_url = image_url
