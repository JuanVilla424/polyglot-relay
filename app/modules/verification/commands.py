from discord import app_commands


def register(_tree: app_commands.CommandTree) -> None:
    """No slash/context-menu commands yet -- the whole flow is reaction-driven."""
