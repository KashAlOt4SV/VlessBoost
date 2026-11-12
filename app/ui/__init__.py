"""VEIL native Qt desktop shell."""

from app.ui.veil import VeilWindow as BoosterApp, run_app
from app.log_utils import trim_log_file

__all__ = ["BoosterApp", "run_app", "trim_log_file"]
