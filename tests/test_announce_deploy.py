from app.announce_deploy import build_message


def test_build_message_includes_service_sha_and_subject():
    """The announcement names which service was deployed, its SHA, and the commit subject."""
    message = build_message("nllb", "f179b74", "fix(core): protect emoji anywhere")

    assert "nllb" in message
    assert "f179b74" in message
    assert "fix(core): protect emoji anywhere" in message


def test_build_message_starts_with_the_deploy_emoji():
    """Consistent with every other admin-action log message in this bot."""
    message = build_message("bot", "abc1234", "feat(core): something")

    assert message.startswith("🚀")
