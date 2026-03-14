# Architecture

## Overview

ComfyUI Viewer is a single-page web application with a Python backend. It is intentionally minimal — one backend file, one frontend file, and a small parser package.

```
comfyui_viewer/
├── app.py                  # FastAPI backend
├── static/
│   └── index.html          # Frontend (HTML + CSS + JS, single file)
├── parsers/                # Metadata parser package
│   ├── __init__.py         # Auto-imports all parsers
│   ├── registry.py         # Parser registry + MetadataResult dataclass
│   ├── flux2.py            # Flux2 workflow parser
│   └── sdxl_sd.py          # SDXL / SD 1.5 workflow parser
├── images/                 # Image root (not in repo)
└── .thumbnails/            # Cached thumbnails (auto-generated)
```

## Backend (`app.py`)

FastAPI application serving four API endpoints and the static frontend.

### API Endpoints

| Endpoint | Purpose |
|---|---|
| `GET /api/browse?path=&sort=&order=` | List folders and images in a directory. Returns JSON with `folders`, `images`, `current_path`, and `parent_path`. Uses `os.scandir()` for performance. |
| `GET /api/thumbnail/{path}` | Serve a thumbnail. Generated on first request using Pillow (300x300 LANCZOS, saved as JPEG quality 85). Cached in `.thumbnails/` mirroring the source directory structure. Regenerated if source file is newer. |
| `GET /api/image/{path}` | Serve the full-resolution image via `FileResponse`. |
| `GET /api/metadata/{path}` | Parse ComfyUI metadata from PNG text chunks and return structured JSON. |

### Path Security

All path parameters are resolved against `BASE_DIR` using `Path.resolve()`. Any path that escapes the base directory returns 403.

## Parser System (`parsers/`)

The parser package uses a registry pattern with priority-based dispatch.

### How It Works

1. Each parser module decorates a class with `@register_parser(name, priority)`
2. The class must implement:
   - `can_parse(nodes: dict) -> bool` — inspect the node dict and return True if this parser handles it
   - `parse(nodes: dict, width: int, height: int) -> MetadataResult` — extract metadata and return a result
3. When metadata is requested, `parse_metadata()` opens the PNG, reads the `prompt` text chunk, parses the JSON node dict, and tries each registered parser in priority order (highest first)
4. If no parser matches, a generic fallback extracts whatever it can

### MetadataResult

Dataclass with standardized fields:

```python
@dataclass
class MetadataResult:
    positive_prompt: Optional[str]
    negative_prompt: Optional[str]
    model: Optional[str]
    architecture: Optional[str]
    sampler: Optional[str]
    scheduler: Optional[str]
    steps: Optional[int]
    cfg: Optional[float]
    guidance: Optional[float]    # Flux-style guidance (distinct from CFG)
    denoise: Optional[float]
    seed: Optional[int]
    width: Optional[int]
    height: Optional[int]
    extra: dict                  # Any parser-specific additional fields
```

### Adding a Parser

Example for a hypothetical "Flux1" workflow:

```python
# parsers/flux1.py
from .registry import register_parser, MetadataResult

@register_parser(name="flux1", priority=15)
class Flux1Parser:

    @staticmethod
    def can_parse(nodes: dict) -> bool:
        # Return True if the node graph matches Flux1 patterns
        for node in nodes.values():
            if node.get("class_type") == "SomeFlux1SpecificNode":
                return True
        return False

    @staticmethod
    def parse(nodes: dict, width: int, height: int) -> MetadataResult:
        result = MetadataResult(width=width, height=height, architecture="Flux1")
        # ... extract fields from nodes ...
        return result
```

Then add `from . import flux1` to `parsers/__init__.py`.

### Priority Guidelines

Higher priority parsers are tried first. Use this when a more specific parser should take precedence over a general one:

| Priority | Use Case |
|---|---|
| 20+ | Specific architectures with unique node types (e.g., Flux2) |
| 10-19 | Common architectures (e.g., SDXL, SD 1.5) |
| 0-9 | Broad/fallback parsers |

### ComfyUI Metadata Format

ComfyUI stores data in PNG text chunks:

- **`prompt`** — JSON dict of nodes keyed by node ID. Each node has `class_type` and `inputs`. Input values are either literals or `[source_node_id, output_index]` references pointing to another node's output.
- **`workflow`** — Full UI workflow (node positions, links, groups). Not used by parsers but available for future features.

## Frontend (`static/index.html`)

Single HTML file with embedded CSS and JS. No build step, no dependencies.

### Views

- **Grid view** — Top bar with breadcrumb navigation and sort controls. Folder cards followed by a CSS Grid of thumbnail cards. Thumbnails use native `loading="lazy"`.
- **Lightbox** — Fixed overlay. Single `<img>` element swapped on navigation. Preloads previous and next images via `new Image()` for instant arrow-key response.
- **Info panel** — Fixed 380px panel sliding in from the right. Pushes the lightbox image container left via margin. Fetches metadata on open and caches it client-side.

### State

Simple object (`state`) tracking current path, image list, lightbox index, sort settings, panel state, and a metadata cache. No framework — direct DOM manipulation.
