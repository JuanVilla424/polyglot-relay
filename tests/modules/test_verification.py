import asyncio
from unittest.mock import AsyncMock, MagicMock

import discord

from app.modules.verification import handlers, logic


def _make_role(role_id):
    role = MagicMock()
    role.id = role_id
    return role


def _make_member(user_id, role_ids=()):
    member = MagicMock()
    member.id = user_id
    member.roles = [_make_role(rid) for rid in role_ids]
    member.add_roles = AsyncMock()
    member.mention = f"<@{user_id}>"
    return member


def _make_attachment(content_type):
    attachment = MagicMock()
    attachment.content_type = content_type
    return attachment


def _make_message(author, attachments=(), message_id=1):
    message = MagicMock()
    message.id = message_id
    message.author = author
    message.attachments = list(attachments)
    message.add_reaction = AsyncMock()
    return message


def _make_guild(roles_by_id, member_by_id):
    guild = MagicMock()
    guild.get_role.side_effect = roles_by_id.get
    guild.get_member.side_effect = member_by_id.get
    return guild


# pylint: disable-next=too-many-arguments,too-many-positional-arguments
def _make_reaction_payload(user_id, guild_id, channel_id, message_id, emoji, member=None):
    payload = MagicMock()
    payload.user_id = user_id
    payload.guild_id = guild_id
    payload.channel_id = channel_id
    payload.message_id = message_id
    payload.emoji = discord.PartialEmoji(name=emoji)
    payload.member = member
    return payload


# --- logic.is_configured / is_approver / has_image_attachment ------------------------


def test_is_configured_true_when_everything_is_set(monkeypatch):
    """All four required settings present -> configured."""
    monkeypatch.setattr(logic, "VERIFY_CHANNEL_ID", 1)
    monkeypatch.setattr(logic, "VERIFIED_ROLE_ID", 2)
    monkeypatch.setattr(logic, "MEMBER_ROLE_ID", 3)
    monkeypatch.setattr(logic, "VERIFY_APPROVER_ROLE_IDS", [4])

    assert logic.is_configured() is True


def test_is_configured_false_when_anything_is_missing(monkeypatch):
    """Any one of the four settings missing -> not configured."""
    monkeypatch.setattr(logic, "VERIFY_CHANNEL_ID", 1)
    monkeypatch.setattr(logic, "VERIFIED_ROLE_ID", None)
    monkeypatch.setattr(logic, "MEMBER_ROLE_ID", 3)
    monkeypatch.setattr(logic, "VERIFY_APPROVER_ROLE_IDS", [4])

    assert logic.is_configured() is False


def test_is_approver_true_with_an_authorized_role(monkeypatch):
    """A member holding one of the configured approver roles is authorized."""
    monkeypatch.setattr(logic, "VERIFY_APPROVER_ROLE_IDS", [10, 20])

    assert logic.is_approver(_make_member(1, role_ids=[20])) is True


def test_is_approver_false_without_an_authorized_role(monkeypatch):
    """A member without any configured approver role is not authorized."""
    monkeypatch.setattr(logic, "VERIFY_APPROVER_ROLE_IDS", [10, 20])

    assert logic.is_approver(_make_member(1, role_ids=[99])) is False


def test_has_image_attachment_true_for_an_image():
    """A message with an image attachment is recognized as a photo."""
    message = _make_message(_make_member(1), attachments=[_make_attachment("image/png")])

    assert logic.has_image_attachment(message) is True


def test_has_image_attachment_false_with_no_attachments():
    """A message with no attachments at all isn't a photo."""
    message = _make_message(_make_member(1), attachments=[])

    assert logic.has_image_attachment(message) is False


def test_has_image_attachment_false_for_a_non_image_attachment():
    """A non-image attachment (e.g. a PDF) doesn't count as a photo."""
    message = _make_message(_make_member(1), attachments=[_make_attachment("application/pdf")])

    assert logic.has_image_attachment(message) is False


# --- logic.approve_and_assign_roles ---------------------------------------------------


def test_approve_and_assign_roles_happy_path(monkeypatch):
    """The full happy path: both roles granted, bot confirms, log channel notified."""
    monkeypatch.setattr(logic, "VERIFIED_ROLE_ID", 100)
    monkeypatch.setattr(logic, "MEMBER_ROLE_ID", 200)
    verified_role = _make_role(100)
    member_role = _make_role(200)
    author = _make_member(2, role_ids=[])
    guild = _make_guild({100: verified_role, 200: member_role}, {2: author})
    message = _make_message(author, attachments=[_make_attachment("image/png")])
    message.guild = guild
    approver = _make_member(999)
    report_mock = AsyncMock()
    monkeypatch.setattr(logic, "report_to_log_channel", report_mock)

    asyncio.run(logic.approve_and_assign_roles(MagicMock(), message, approver))

    author.add_roles.assert_awaited_once()
    called_roles = author.add_roles.call_args.args
    assert verified_role in called_roles
    assert member_role in called_roles
    message.add_reaction.assert_awaited_once_with(logic.APPROVAL_EMOJI)
    report_mock.assert_awaited_once()


def test_approve_and_assign_roles_is_idempotent_when_already_verified(monkeypatch):
    """An author who already has both roles doesn't get a redundant add_roles call."""
    monkeypatch.setattr(logic, "VERIFIED_ROLE_ID", 100)
    monkeypatch.setattr(logic, "MEMBER_ROLE_ID", 200)
    verified_role = _make_role(100)
    member_role = _make_role(200)
    author = _make_member(2, role_ids=[100, 200])
    guild = _make_guild({100: verified_role, 200: member_role}, {2: author})
    message = _make_message(author, attachments=[_make_attachment("image/png")])
    message.guild = guild
    approver = _make_member(999)
    monkeypatch.setattr(logic, "report_to_log_channel", AsyncMock())

    asyncio.run(logic.approve_and_assign_roles(MagicMock(), message, approver))

    author.add_roles.assert_not_awaited()


def test_approve_and_assign_roles_reports_instead_of_failing_silently(monkeypatch):
    """Real-world case: the bot's role hierarchy/Manage Roles permission isn't
    set up yet -- must show up in the log channel, not just vanish.
    """
    monkeypatch.setattr(logic, "VERIFIED_ROLE_ID", 100)
    monkeypatch.setattr(logic, "MEMBER_ROLE_ID", 200)
    verified_role = _make_role(100)
    member_role = _make_role(200)
    author = _make_member(2, role_ids=[])
    response = MagicMock(status=403, reason="Forbidden")
    author.add_roles = AsyncMock(side_effect=discord.Forbidden(response, "missing access"))
    guild = _make_guild({100: verified_role, 200: member_role}, {2: author})
    message = _make_message(author, attachments=[_make_attachment("image/png")])
    message.guild = guild
    approver = _make_member(999)
    report_mock = AsyncMock()
    monkeypatch.setattr(logic, "report_to_log_channel", report_mock)

    asyncio.run(logic.approve_and_assign_roles(MagicMock(), message, approver))  # must not raise

    report_mock.assert_awaited_once()
    sent_text = report_mock.call_args.args[1].lower()
    assert "manage roles" in sent_text or "hierarchy" in sent_text


# --- handlers.handle_reaction_add -----------------------------------------------------


def test_handle_reaction_add_ignores_when_not_configured(monkeypatch):
    """The module isn't fully configured yet -> unclaimed."""
    monkeypatch.setattr(logic, "VERIFY_CHANNEL_ID", None)
    payload = _make_reaction_payload(1, 1, 10, 20, "✅")

    claimed = asyncio.run(handlers.handle_reaction_add(MagicMock(), payload))

    assert claimed is False


def test_handle_reaction_add_ignores_a_non_approval_emoji(monkeypatch):
    """A reaction with any emoji other than the approval one is unclaimed."""
    monkeypatch.setattr(logic, "VERIFY_CHANNEL_ID", 10)
    monkeypatch.setattr(logic, "VERIFIED_ROLE_ID", 100)
    monkeypatch.setattr(logic, "MEMBER_ROLE_ID", 200)
    monkeypatch.setattr(logic, "VERIFY_APPROVER_ROLE_IDS", [500])
    payload = _make_reaction_payload(1, 1, 10, 20, "👍")

    claimed = asyncio.run(handlers.handle_reaction_add(MagicMock(), payload))

    assert claimed is False


def test_handle_reaction_add_ignores_the_wrong_channel(monkeypatch):
    """An approval emoji outside the configured verify channel is unclaimed."""
    monkeypatch.setattr(logic, "VERIFY_CHANNEL_ID", 10)
    monkeypatch.setattr(logic, "VERIFIED_ROLE_ID", 100)
    monkeypatch.setattr(logic, "MEMBER_ROLE_ID", 200)
    monkeypatch.setattr(logic, "VERIFY_APPROVER_ROLE_IDS", [500])
    payload = _make_reaction_payload(1, 1, 999, 20, "✅")

    claimed = asyncio.run(handlers.handle_reaction_add(MagicMock(), payload))

    assert claimed is False


def test_handle_reaction_add_ignores_a_non_approver(monkeypatch):
    """A reactor without any approver role can't trigger verification."""
    monkeypatch.setattr(logic, "VERIFY_CHANNEL_ID", 10)
    monkeypatch.setattr(logic, "VERIFIED_ROLE_ID", 100)
    monkeypatch.setattr(logic, "MEMBER_ROLE_ID", 200)
    monkeypatch.setattr(logic, "VERIFY_APPROVER_ROLE_IDS", [500])
    reactor = _make_member(1, role_ids=[999])
    payload = _make_reaction_payload(1, 1, 10, 20, "✅", member=reactor)

    claimed = asyncio.run(handlers.handle_reaction_add(MagicMock(), payload))

    assert claimed is False


def test_handle_reaction_add_ignores_a_message_without_an_image(monkeypatch):
    """An approver reacting on a message with no photo doesn't trigger anything."""
    monkeypatch.setattr(logic, "VERIFY_CHANNEL_ID", 10)
    monkeypatch.setattr(logic, "VERIFIED_ROLE_ID", 100)
    monkeypatch.setattr(logic, "MEMBER_ROLE_ID", 200)
    monkeypatch.setattr(logic, "VERIFY_APPROVER_ROLE_IDS", [500])
    reactor = _make_member(1, role_ids=[500])
    author = _make_member(2)
    message = _make_message(author, attachments=[])
    channel = MagicMock(spec=discord.TextChannel)
    channel.fetch_message = AsyncMock(return_value=message)
    client = MagicMock(get_channel=MagicMock(return_value=channel))
    payload = _make_reaction_payload(1, 1, 10, 20, "✅", member=reactor)

    claimed = asyncio.run(handlers.handle_reaction_add(client, payload))

    assert claimed is False


def test_handle_reaction_add_approves_on_the_happy_path(monkeypatch):
    """An authorized approver reacting on a real photo grants both roles."""
    monkeypatch.setattr(logic, "VERIFY_CHANNEL_ID", 10)
    monkeypatch.setattr(logic, "VERIFIED_ROLE_ID", 100)
    monkeypatch.setattr(logic, "MEMBER_ROLE_ID", 200)
    monkeypatch.setattr(logic, "VERIFY_APPROVER_ROLE_IDS", [500])
    monkeypatch.setattr(logic, "report_to_log_channel", AsyncMock())
    verified_role = _make_role(100)
    member_role = _make_role(200)
    author = _make_member(2, role_ids=[])
    guild = _make_guild({100: verified_role, 200: member_role}, {2: author})
    reactor = _make_member(1, role_ids=[500])
    message = _make_message(author, attachments=[_make_attachment("image/png")])
    message.guild = guild
    channel = MagicMock(spec=discord.TextChannel)
    channel.fetch_message = AsyncMock(return_value=message)
    client = MagicMock(get_channel=MagicMock(return_value=channel))
    payload = _make_reaction_payload(2, 1, 10, 20, "✅", member=reactor)

    claimed = asyncio.run(handlers.handle_reaction_add(client, payload))

    assert claimed is True
    author.add_roles.assert_awaited_once()
