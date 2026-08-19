import logging
from typing import Any

from . import achievement_catalog as catalog_module
from . import achievements as achievement_module
from . import quality_achievements as quality_module

_INSTALLED = False


def install_achievement_evaluation_guard() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    original = achievement_module.evaluate_user_achievements

    def guarded_evaluate(*args: Any, **kwargs: Any):
        try:
            return original(*args, **kwargs)
        except (ValueError, TypeError, ArithmeticError):
            # Achievement configuration must never make the underlying price
            # contribution transaction fail. Invalid new criteria are rejected by
            # the admin API; this guard only protects against legacy bad rows.
            logging.exception("achievement_evaluation_skipped_invalid_definition")
            return []

    achievement_module.evaluate_user_achievements = guarded_evaluate
    catalog_module.evaluate_user_achievements = guarded_evaluate
    quality_module.evaluate_user_achievements = guarded_evaluate
    _INSTALLED = True
