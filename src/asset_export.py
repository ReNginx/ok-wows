"""Publish template exports without replacing images that readers may still hold."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import threading
import time

from ok.util.clazz import generate_label_enum


_export_lock = threading.Lock()


def _retry_file_operation(operation):
    # Windows thumbnails and antivirus scanners can hold newly written files briefly.
    for attempt in range(4):
        try:
            return operation()
        except PermissionError:
            if attempt == 3:
                raise
            time.sleep(0.1 * (attempt + 1))


def _digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def export_assets(coco_json, target_folder, image_folder, compressor, generate_label_enmu=None):
    """Build privately, publish immutable images, then atomically switch the index.

    Previous images stay available for in-flight readers. Only the small COCO index
    is replaced; if publishing it fails, the previous resource pack remains usable.
    """
    source = Path(coco_json).resolve()
    target = Path(target_folder).resolve()
    image_folder = Path(image_folder).resolve()
    if target == source.parent or target == image_folder:
        raise ValueError("The export destination must differ from the template source folder.")

    with _export_lock:
        data = json.loads(source.read_text(encoding="utf-8"))
        for item in data["images"]:
            image = image_folder / Path(item["file_name"]).name
            if not image.is_file():
                raise FileNotFoundError(f"Template image not found: {image}")

        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".asset-export-", dir=target.parent,
                                         ignore_cleanup_errors=True) as temporary:
            stage = Path(temporary)
            # Failures in the upstream compressor can only damage this private copy.
            staged_json = Path(_retry_file_operation(lambda: compressor(
                str(source), str(stage / "pack"), str(image_folder), None)))
            packed = json.loads(staged_json.read_text(encoding="utf-8"))
            destination = target / source.name

            # Reuse identical existing pages, including legacy 0.png/1.png names.
            existing = {}
            if destination.is_file():
                previous = json.loads(destination.read_text(encoding="utf-8"))
                for name in {item["file_name"] for item in previous["images"]}:
                    path = (target / name).resolve()
                    if path.is_relative_to(target) and path.is_file():
                        existing[_digest(path)] = name

            (target / "images").mkdir(parents=True, exist_ok=True)
            published = {}
            for item in packed["images"]:
                name = item["file_name"]
                if name not in published:
                    path = staged_json.parent / name
                    digest = _digest(path)
                    final_name = existing.get(digest, f"images/packed-{digest}.png")
                    final_path = target / final_name
                    if not final_path.exists():
                        # The temporary file is on the same volume as the destination.
                        pending = stage / f"{digest}.png"
                        shutil.copy2(path, pending)
                        _retry_file_operation(lambda: os.replace(pending, final_path))
                    elif _digest(final_path) != digest:
                        raise ValueError(f"Export image content changed: {final_path}")
                    published[name] = final_name
                item["file_name"] = published[name]

            pending_json = stage / source.name
            pending_json.write_text(json.dumps(packed, indent=4), encoding="utf-8")
            if generate_label_enmu:
                generate_label_enum(generate_label_enmu, [cat["name"] for cat in packed["categories"]])
            # No live image has been overwritten or deleted, even if this fails.
            _retry_file_operation(lambda: os.replace(pending_json, destination))
            return str(destination)
