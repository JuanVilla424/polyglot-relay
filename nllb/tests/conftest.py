import os
from pathlib import Path

# server.py loads the glossary at import time -- point it at the repo's example
# glossary (the game glossary these pipeline tests were written against) before
# the first `import server`. Force-set (not setdefault): a stray GLOSSARY_PATH
# in the environment would silently change what every assertion runs against.
os.environ["GLOSSARY_PATH"] = str(
    Path(__file__).resolve().parent.parent.parent / "config" / "glossary.example.json"
)
