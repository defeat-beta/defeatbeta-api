from contextlib import redirect_stdout
import sys

__all__ = ["main"]

with redirect_stdout(sys.stderr):
    from .server import main
