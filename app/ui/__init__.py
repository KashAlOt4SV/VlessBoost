"""VLESS Boost UI package — CustomTkinter shell over existing business logic."""

from app.ui.app import BoosterApp, run_app
from app.ui.helpers import trim_log_file

__all__ = ["BoosterApp", "run_app", "trim_log_file"]
