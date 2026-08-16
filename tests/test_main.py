import discord

from app import main as bot_main


def test_intents_enable_message_content():
    """Auto-translate needs the privileged message content intent enabled."""
    assert bot_main.intents.message_content is True


def test_client_and_tree_are_wired():
    """The command tree must be bound to the same client instance we run."""
    assert isinstance(bot_main.client, discord.Client)
    assert isinstance(bot_main.tree, discord.app_commands.CommandTree)
    assert bot_main.tree.client is bot_main.client


def test_commands_are_registered():
    """Both the slash command and the context menu command are registered."""
    names = {command.name for command in bot_main.tree.get_commands()}
    assert "setlanguage" in names
    assert "Translate Message" in names
