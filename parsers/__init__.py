"""
ComfyUI metadata parsers.

Each parser module registers itself via the registry.
To add a new parser, create a new file in this package and
use @register_parser(priority=N) to register it.
Higher priority parsers are tried first.
"""

from .registry import register_parser, parse_metadata, MetadataResult

# Import all parser modules so they auto-register
from . import sdxl_sd
from . import flux2
