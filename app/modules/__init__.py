from app.modules import events, translation

# Registry of every module this bot hosts. Adding a future module is one
# import + one entry here -- no dynamic plugin loader, since this is a
# handful of built-in modules, not a general plugin system.
MODULES = {"translation": translation, "events": events}
