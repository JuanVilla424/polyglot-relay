from discord import app_commands

from app import storage
from app.config import SUBJECT_ROLE_ID


def is_subject(member) -> bool:
    """True when member carries the quarantine role (SUBJECT_ROLE_ID).

    None-safe on both sides: an unset SUBJECT_ROLE_ID, a missing member
    (uncached, DM), or a user object without roles never quarantines anyone.
    """
    if SUBJECT_ROLE_ID is None or member is None:
        return False
    return any(role.id == SUBJECT_ROLE_ID for role in getattr(member, "roles", []))


class ModuleDisabledError(app_commands.CheckFailure):
    """Raised when a command's module isn't enabled for the guild it was run in."""

    def __init__(self, module_name: str):
        self.module_name = module_name
        super().__init__(f"The `{module_name}` module isn't enabled in this server.")


def module_enabled_predicate(module_name: str):
    """The bare async predicate, exposed separately so it's testable without
    going through discord.py's opaque `app_commands.check(...)` decorator.
    """

    async def predicate(interaction) -> bool:
        if interaction.guild_id is None:
            return True  # let the command's own guild-only check report that instead
        if not storage.is_module_enabled(interaction.guild_id, module_name):
            raise ModuleDisabledError(module_name)
        return True

    return predicate


def require_enabled(module_name: str):
    """Command check: reject with ModuleDisabledError unless the module is active here."""
    return app_commands.check(module_enabled_predicate(module_name))
