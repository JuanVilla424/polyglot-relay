import asyncio
from unittest.mock import AsyncMock, MagicMock

import discord

from app import main as bot_main
from app import storage


def _use_tmp_store(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    monkeypatch.setattr(storage, "USER_LANGUAGES_PATH", tmp_path / "user_languages.json")


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


def test_setlanguage_rejects_unsupported_code(tmp_path, monkeypatch):
    """Unmapped language codes are rejected before ever touching storage."""
    _use_tmp_store(tmp_path, monkeypatch)
    interaction = MagicMock()
    interaction.guild_id = 1
    interaction.user.id = 100
    interaction.response.send_message = AsyncMock()

    asyncio.run(bot_main.setlanguage.callback(interaction, "xx"))

    interaction.response.send_message.assert_awaited_once()
    assert storage.get_user_language(1, 100) is None


def test_setlanguage_stores_supported_code(tmp_path, monkeypatch):
    """A supported code is normalized to lowercase and persisted."""
    _use_tmp_store(tmp_path, monkeypatch)
    interaction = MagicMock()
    interaction.guild_id = 1
    interaction.user.id = 100
    interaction.response.send_message = AsyncMock()

    asyncio.run(bot_main.setlanguage.callback(interaction, "ES"))

    assert storage.get_user_language(1, 100) == "es"
