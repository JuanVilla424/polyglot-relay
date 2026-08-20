from app.modules import activity, events, polls, translation, verification

# Registry of every module this bot hosts. Adding a future module is one
# import + one entry here -- no dynamic plugin loader, since this is a
# handful of built-in modules, not a general plugin system.
#
# `activity` must stay first: its handle_reaction_add records activity but
# always returns False (never "claims" the reaction), so every other
# module's own claiming handler still needs to run afterward in the same
# dispatch pass -- see app/main.py's on_raw_reaction_add.
MODULES = {
    "activity": activity,
    "translation": translation,
    "events": events,
    "verification": verification,
    "polls": polls,
}
