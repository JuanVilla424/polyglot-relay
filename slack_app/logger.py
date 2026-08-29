import logging
import os
import sys


def setup_logger(name, level=logging.INFO, log_file=None):
    """Build a console+file logger, reusing handlers if already configured."""
    log = logging.getLogger(name)
    log.setLevel(level)

    if not log.handlers:
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(logging.Formatter("%(message)s"))
        log.addHandler(sh)

        if log_file:
            os.makedirs(os.path.dirname(log_file), exist_ok=True)
            fh = logging.FileHandler(log_file)
            fh.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
            log.addHandler(fh)

    return log


logger = setup_logger("polyglot-relay-slack", log_file="logs/slack.log")
