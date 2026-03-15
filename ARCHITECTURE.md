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
│   ├── flux2.py            # Flux1/Flux2/ZImage parser (SamplerCustomAdvanced)
│   └── sdxl_sd.py          # SDXL/SD/Pony parser (KSampler)
├── images/                 # Image root (not in repo)
└── .thumbnails/            # Cached thumbnails (auto-generated)
```

## Backend (`app.py`)

FastAPI application serving five API endpoints and the static frontend.

### API Endpoints

| Endpoint | Purpose |
|---|---|
| `GET /api/browse?path=&sort=&order=` | List folders and images in a directory. Returns JSON with `folders`, `images`, `current_path`, and `parent_path`. Uses `os.scandir()` for performance. |
| `GET /api/tree?path=` | List subfolders for tree sidebar (lazy loading). Returns folder names, paths, and whether each has children (for expand arrows). |
| `GET /api/thumbnail/{path}` | Serve a thumbnail. Generated on first request using Pillow (300x300 LANCZOS, saved as JPEG quality 85). Cached in `.thumbnails/` mirroring the source directory structure. Regenerated if source file is newer. |
| `GET /api/image/{path}` | Serve the full-resolution image via `FileResponse`. |
| `GET /api/metadata/{path}` | Parse ComfyUI metadata from PNG text chunks and return structured JSON. For non-ComfyUI images, returns basic file info (dimensions, creation date). |

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
5. For non-PNG or non-ComfyUI files, the API endpoint returns basic file info (dimensions + timestamp)

### Architecture Detection

Parsers detect the architecture using a two-step approach:
1. **CLIPLoader/DualCLIPLoader `type` field** — `flux2`, `flux`, `qwen_image`, etc.
2. **Model name heuristics** — fallback when the CLIP type is ambiguous

This allows a single parser (e.g., `flux2.py`) to correctly identify Flux1, Flux2, and ZImage workflows.

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
    vae: Optional[str]           # VAE model name (from VAELoader)
    source_image: Optional[str]  # Input image for img2img workflows
    created: Optional[str]       # File modification timestamp
    extra: dict                  # Any parser-specific additional fields
```

### Common Enrichment

After a parser returns its result, `_enrich_common()` adds cross-parser fields automatically:
- **created** — file modification timestamp
- **vae** — from any `VAELoader` node in the workflow

This avoids duplicating logic across parsers.

### Adding a Parser

Example for a new workflow type:

```python
# parsers/my_arch.py
from .registry import register_parser, MetadataResult

@register_parser(name="my_arch", priority=15)
class MyArchParser:

    @staticmethod
    def can_parse(nodes: dict) -> bool:
        for node in nodes.values():
            if node.get("class_type") == "SomeSpecificNode":
                return True
        return False

    @staticmethod
    def parse(nodes: dict, width: int, height: int) -> MetadataResult:
        result = MetadataResult(width=width, height=height, architecture="MyArch")
        # ... extract fields from nodes ...
        return result
```

Then add `from . import my_arch` to `parsers/__init__.py`.

### Priority Guidelines

Higher priority parsers are tried first. Use this when a more specific parser should take precedence over a general one:

| Priority | Use Case |
|---|---|
| 20+ | Specific architectures with unique node types (e.g., Flux2, ZImage) |
| 10-19 | Common architectures (e.g., SDXL, SD 1.5, Pony) |
| 0-9 | Broad/fallback parsers |

### ComfyUI Metadata Format

ComfyUI stores data in PNG text chunks:

- **`prompt`** — JSON dict of nodes keyed by node ID. Each node has `class_type` and `inputs`. Input values are either literals or `[source_node_id, output_index]` references pointing to another node's output.
- **`workflow`** — Full UI workflow (node positions, links, groups). Not used by parsers but available for future features.

## Frontend (`static/index.html`)

Single HTML file with embedded CSS and JS. No build step, no dependencies.

### Layout

- **Top bar** — breadcrumb path navigation + sort controls (field + direction)
- **Left sidebar** — collapsible folder tree with lazy-loading. Folders expand on click, showing subfolders. Active folder is highlighted. Toggle via edge tab.
- **Content area** — CSS Grid of thumbnail cards with always-visible filenames

### Lightbox

- Full-viewport overlay with keyboard navigation (left/right arrows, wraps around)
- Preloads previous and next images via `new Image()` for instant response
- **Filmstrip** at the bottom showing all images with smooth CSS transform scrolling — current image centered, dynamically adapts to screen width
- **Info panel** (380px, right side) — open by default, collapsible via edge tab. Shows parsed metadata with copy buttons. Pushes image and filmstrip left when open.

### State

Simple object (`state`) tracking current path, image list, lightbox index, sort settings, panel state, and a metadata cache. No framework — direct DOM manipulation.
