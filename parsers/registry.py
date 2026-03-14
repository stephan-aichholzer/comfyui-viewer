"""Parser registry with auto-detection and priority-based dispatch."""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Optional, Callable
import json
import os
from datetime import datetime
from PIL import Image


@dataclass
class MetadataResult:
    positive_prompt: Optional[str] = None
    negative_prompt: Optional[str] = None
    model: Optional[str] = None
    architecture: Optional[str] = None
    sampler: Optional[str] = None
    scheduler: Optional[str] = None
    steps: Optional[int] = None
    cfg: Optional[float] = None
    guidance: Optional[float] = None
    denoise: Optional[float] = None
    seed: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    vae: Optional[str] = None
    source_image: Optional[str] = None
    created: Optional[str] = None
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        extra = d.pop("extra", {})
        # Remove None values for cleaner output
        d = {k: v for k, v in d.items() if v is not None}
        if extra:
            d["extra"] = extra
        return d


# Registry: list of (priority, name, detect_fn, parse_fn)
_parsers: list[tuple[int, str, Callable, Callable]] = []


def register_parser(name: str, priority: int = 0):
    """Decorator to register a parser.

    The decorated function receives (nodes: dict, img_width: int, img_height: int)
    and must return MetadataResult or None.

    It must have a .can_parse(nodes) classmethod/attribute or we use a separate approach:
    Pass a (detect_fn, parse_fn) tuple.
    """
    def decorator(cls):
        _parsers.append((priority, name, cls.can_parse, cls.parse))
        _parsers.sort(key=lambda x: -x[0])  # Higher priority first
        return cls
    return decorator


def extract_nodes(filepath: str) -> Optional[dict]:
    """Extract the prompt node dict from a PNG file."""
    try:
        img = Image.open(filepath)
        prompt_text = img.info.get("prompt")
        if not prompt_text:
            return None
        return json.loads(prompt_text)
    except Exception:
        return None


def parse_metadata(filepath: str) -> Optional[dict]:
    """Parse metadata from a ComfyUI PNG file.

    Tries each registered parser in priority order.
    Returns the first successful result as a dict.
    """
    try:
        img = Image.open(filepath)
        width, height = img.size
        prompt_text = img.info.get("prompt")
        if not prompt_text:
            return None
        nodes = json.loads(prompt_text)
    except Exception:
        return None

    for _priority, _name, detect_fn, parse_fn in _parsers:
        try:
            if detect_fn(nodes):
                result = parse_fn(nodes, width, height)
                if result is not None:
                    _enrich_common(result, nodes, filepath)
                    return result.to_dict()
        except Exception:
            continue

    # Fallback: try generic extraction
    result = _generic_parse(nodes, width, height)
    if result:
        return result
    return None


def _enrich_common(result: MetadataResult, nodes: dict, filepath: str):
    """Add common fields that apply across all parsers."""
    # File creation/modification date
    try:
        mtime = os.path.getmtime(filepath)
        result.created = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        pass

    # VAE (from any VAELoader node)
    if result.vae is None:
        for node in nodes.values():
            if node.get("class_type") == "VAELoader":
                vae = node.get("inputs", {}).get("vae_name")
                if vae:
                    result.vae = vae
                    break



def _generic_parse(nodes: dict, width: int, height: int) -> Optional[dict]:
    """Fallback parser that extracts what it can from any workflow."""
    result = MetadataResult(width=width, height=height)

    for nid, node in nodes.items():
        ct = node.get("class_type", "")
        inputs = node.get("inputs", {})

        if ct == "CLIPTextEncode" and isinstance(inputs.get("text"), str):
            if result.positive_prompt is None:
                result.positive_prompt = inputs["text"]
            elif result.negative_prompt is None:
                result.negative_prompt = inputs["text"]

        if "CheckpointLoader" in ct and inputs.get("ckpt_name"):
            result.model = inputs["ckpt_name"]

    if result.positive_prompt or result.model:
        result.architecture = "Unknown"
        return result.to_dict()

    return None
