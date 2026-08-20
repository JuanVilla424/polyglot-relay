import discord

from app.modules.activity import storage

DEFAULT_INACTIVE_DAYS = 7
DIGEST_INTERVAL_DAYS = 7
_SECONDS_PER_DAY = 86400


def is_digest_due(last_sent: int, now: int) -> bool:
    """Whether at least DIGEST_INTERVAL_DAYS have passed since the last digest."""
    return now - last_sent >= DIGEST_INTERVAL_DAYS * _SECONDS_PER_DAY


async def build_activity_report(guild: discord.Guild, inactive_days: int) -> str:
    """List members inactive for at least inactive_days, plus members never
    recorded at all (joined before the module was enabled, or truly never
    active) -- kept as separate sections since they mean different things.
    """
    now = int(discord.utils.utcnow().timestamp())
    last_active = storage.get_last_active(guild.id)
    threshold_seconds = inactive_days * _SECONDS_PER_DAY

    inactive = []
    never_recorded = []
    for member in guild.members:
        if member.bot:
            continue
        last_seen = last_active.get(member.id)
        if last_seen is None:
            never_recorded.append(member)
        elif now - last_seen >= threshold_seconds:
            inactive.append(((now - last_seen) // _SECONDS_PER_DAY, member))

    if not inactive and not never_recorded:
        return f"Everyone's been active in the last {inactive_days} days."

    lines = []
    if inactive:
        inactive.sort(key=lambda pair: pair[0], reverse=True)
        lines.append(f"**Inactive ({inactive_days}+ days)**")
        lines.extend(f"<@{member.id}> — {days} days" for days, member in inactive)
    if never_recorded:
        if lines:
            lines.append("")
        lines.append("**No activity recorded yet**")
        lines.extend(f"<@{member.id}>" for member in never_recorded)
    return "\n".join(lines)
