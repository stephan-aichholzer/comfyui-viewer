# ComfyUI Viewer

A fast, lightweight web-based image viewer for ComfyUI outputs. Browse folders, view images in a fullscreen lightbox with keyboard navigation, and inspect parsed metadata (prompts, models, parameters) with one-click copy.

## Features

- **Thumbnail grid** with lazy loading and folder navigation
- **Fullscreen lightbox** with arrow key navigation and image preloading
- **Metadata side panel** (open by default, collapsible via edge tab) showing parsed ComfyUI workflow info:
  - Positive / negative prompts with copy buttons
  - Model name and architecture
  - Sampler, scheduler, steps, CFG, guidance, seed, dimensions
  - VAE, creation date
- **Always-visible filenames** on thumbnails
- **Configurable sorting** by name or date modified (ascending/descending)
- **Extensible parser system** — add support for new workflow types by dropping in a parser file

## Supported Workflows

| Architecture | Node Pattern | Status |
|---|---|---|
| Flux2 | SamplerCustomAdvanced + KSamplerSelect | Supported |
| SDXL / SD 1.5 | KSampler + CheckpointLoaderSimple | Supported |
| Generic fallback | Any CLIPTextEncode + CheckpointLoader | Basic support |

## Quick Start

```bash
pip install -r requirements.txt
python app.py
```

Open [http://localhost:8899](http://localhost:8899) in your browser.

### Configuration

| Environment Variable | Default | Description |
|---|---|---|
| `COMFYUI_IMAGES` | `./images` | Root directory containing your ComfyUI outputs |
| `COMFYUI_THUMBS` | `./.thumbnails` | Thumbnail cache directory (auto-created) |

Example:

```bash
COMFYUI_IMAGES=/path/to/comfyui/output python app.py
```

## Keyboard Shortcuts

| Key | Action |
|---|---|
| Left / Right arrow | Previous / next image |
| I | Toggle info panel |
| Escape | Close info panel or lightbox |

## Adding a New Parser

See [ARCHITECTURE.md](ARCHITECTURE.md) for details on the parser system.

1. Create a new file in `parsers/` (e.g., `parsers/flux1.py`)
2. Implement a class with `can_parse(nodes)` and `parse(nodes, width, height)` methods
3. Decorate it with `@register_parser(name="flux1", priority=15)`
4. Import it in `parsers/__init__.py`

## Requirements

- Python 3.10+
- FastAPI
- Uvicorn
- Pillow
