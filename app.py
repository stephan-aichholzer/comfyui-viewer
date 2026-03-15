"""ComfyUI Image Viewer — FastAPI backend."""

import argparse
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image

from parsers import parse_metadata

BASE_DIR = Path(os.environ.get("COMFYUI_IMAGES", "./images")).resolve()
THUMB_DIR = Path(os.environ.get("COMFYUI_THUMBS", "./.thumbnails")).resolve()
THUMB_SIZE = (300, 300)
SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}

app = FastAPI()


def configure(image_root: str | None = None, thumb_dir: str | None = None):
    """Update BASE_DIR and THUMB_DIR at startup."""
    global BASE_DIR, THUMB_DIR
    if image_root:
        BASE_DIR = Path(image_root).resolve()
    if thumb_dir:
        THUMB_DIR = Path(thumb_dir).resolve()


def _safe_path(relative: str) -> Path:
    """Resolve a relative path safely within BASE_DIR."""
    if not relative:
        return BASE_DIR
    resolved = (BASE_DIR / relative).resolve()
    if not str(resolved).startswith(str(BASE_DIR)):
        raise HTTPException(status_code=403, detail="Access denied")
    return resolved


def _is_image(name: str) -> bool:
    return Path(name).suffix.lower() in SUPPORTED_EXTENSIONS


@app.get("/api/browse")
def browse(
    path: str = "",
    sort: str = Query("modified", pattern="^(modified|name)$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
):
    """List folders and images in a directory."""
    dir_path = _safe_path(path)
    if not dir_path.is_dir():
        raise HTTPException(status_code=404, detail="Directory not found")

    folders = []
    images = []

    try:
        entries = list(os.scandir(dir_path))
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied")

    for entry in entries:
        if entry.name.startswith("."):
            continue
        if entry.is_dir(follow_symlinks=False):
            rel = os.path.relpath(entry.path, BASE_DIR)
            folders.append({"name": entry.name, "path": rel})
        elif entry.is_file() and _is_image(entry.name):
            rel = os.path.relpath(entry.path, BASE_DIR)
            stat = entry.stat()
            images.append({
                "name": entry.name,
                "path": rel,
                "modified": stat.st_mtime,
            })

    folders.sort(key=lambda f: f["name"].lower())

    reverse = order == "desc"
    if sort == "modified":
        images.sort(key=lambda i: i["modified"], reverse=reverse)
    else:
        images.sort(key=lambda i: i["name"].lower(), reverse=reverse)

    parent_path = None
    if path:
        parent = str(Path(path).parent)
        parent_path = "" if parent == "." else parent

    return {
        "current_path": path,
        "parent_path": parent_path,
        "folders": folders,
        "images": images,
    }


@app.get("/api/tree")
def tree(path: str = ""):
    """List subfolders for tree navigation (lazy loading)."""
    dir_path = _safe_path(path)
    if not dir_path.is_dir():
        raise HTTPException(status_code=404, detail="Directory not found")

    folders = []
    try:
        for entry in os.scandir(dir_path):
            if entry.name.startswith("."):
                continue
            if entry.is_dir(follow_symlinks=False):
                rel = os.path.relpath(entry.path, BASE_DIR)
                # Check if this folder has subfolders (for expand arrow)
                has_children = False
                try:
                    for sub in os.scandir(entry.path):
                        if not sub.name.startswith(".") and sub.is_dir(follow_symlinks=False):
                            has_children = True
                            break
                except PermissionError:
                    pass
                folders.append({
                    "name": entry.name,
                    "path": rel,
                    "has_children": has_children,
                })
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied")

    folders.sort(key=lambda f: f["name"].lower())
    return {"path": path, "folders": folders}


@app.get("/api/thumbnail/{path:path}")
def thumbnail(path: str):
    """Serve a cached thumbnail, generating if needed."""
    src = _safe_path(path)
    if not src.is_file():
        raise HTTPException(status_code=404)

    # Thumbnail as JPEG for speed
    thumb_path = THUMB_DIR / (path + ".jpg")
    thumb_path.parent.mkdir(parents=True, exist_ok=True)

    # Regenerate if source is newer
    if not thumb_path.exists() or src.stat().st_mtime > thumb_path.stat().st_mtime:
        try:
            img = Image.open(src)
            img.thumbnail(THUMB_SIZE, Image.LANCZOS)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            img.save(thumb_path, "JPEG", quality=85)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Thumbnail error: {e}")

    return FileResponse(thumb_path, media_type="image/jpeg")


@app.get("/api/image/{path:path}")
def image(path: str):
    """Serve a full-resolution image."""
    src = _safe_path(path)
    if not src.is_file():
        raise HTTPException(status_code=404)

    suffix = src.suffix.lower()
    media_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }
    return FileResponse(src, media_type=media_types.get(suffix, "image/png"))


@app.get("/api/metadata/{path:path}")
def metadata(path: str):
    """Return parsed ComfyUI metadata."""
    src = _safe_path(path)
    if not src.is_file():
        raise HTTPException(status_code=404)

    result = parse_metadata(str(src))
    if result is None:
        result = {}

    # Always include basic file info
    if "width" not in result or "height" not in result:
        try:
            img = Image.open(src)
            result["width"] = img.size[0]
            result["height"] = img.size[1]
        except Exception:
            pass
    if "created" not in result:
        try:
            from datetime import datetime
            mtime = src.stat().st_mtime
            result["created"] = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            pass

    return result


# Serve frontend
app.mount("/", StaticFiles(directory="static", html=True), name="static")


if __name__ == "__main__":
    import uvicorn

    parser = argparse.ArgumentParser(description="ComfyUI Image Viewer")
    parser.add_argument("root", nargs="?", default=None,
                        help="Root directory containing images (default: ./images)")
    parser.add_argument("--thumbs", default=None,
                        help="Thumbnail cache directory (default: ./.thumbnails)")
    parser.add_argument("--host", default="0.0.0.0",
                        help="Bind address (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8899,
                        help="Port (default: 8899)")
    args = parser.parse_args()

    configure(args.root, args.thumbs)
    print(f"Serving images from: {BASE_DIR}")
    uvicorn.run(app, host=args.host, port=args.port)
