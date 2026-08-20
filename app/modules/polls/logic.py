from datetime import timedelta

import discord

MIN_POLL_ANSWERS = 2
MAX_POLL_ANSWERS = 10
MAX_ANSWER_LENGTH = 55
DEFAULT_POLL_DURATION_HOURS = 24
MAX_POLL_DURATION_HOURS = 168  # Discord's own cap: 1 week


def parse_poll_options(raw: str) -> list[str]:
    """Split a ";"-separated options string into a validated list of answers.

    discord.py itself doesn't enforce Discord's platform limits on the
    answers it's given (confirmed: add_answer accepts an over-length string
    without error, and only the live API would reject it later) -- so this
    validates count and per-answer length upfront, with a clear message,
    instead of letting a malformed poll fail deep inside the Discord API call.
    """
    options = [option.strip() for option in raw.split(";")]
    options = [option for option in options if option]

    if len(options) < MIN_POLL_ANSWERS:
        raise ValueError(f"A poll needs at least {MIN_POLL_ANSWERS} options.")
    if len(options) > MAX_POLL_ANSWERS:
        raise ValueError(f"A poll can have up to {MAX_POLL_ANSWERS} options.")
    for option in options:
        if len(option) > MAX_ANSWER_LENGTH:
            raise ValueError(f"`{option}` is over Discord's {MAX_ANSWER_LENGTH} characters limit.")

    return options


def build_poll(question: str, options: list[str], duration_hours: int) -> discord.Poll:
    """Build a native Discord poll -- local construction only, no network call."""
    poll = discord.Poll(question, timedelta(hours=duration_hours))
    for option in options:
        poll.add_answer(text=option)
    return poll
