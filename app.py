"""ComfyUI Image Viewer — FastAPI backend."""

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
        return JSONResponse({"error": "No ComfyUI metadata found"}, status_code=200)

    return result


# Serve frontend
app.mount("/", StaticFiles(directory="static", html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8899)
