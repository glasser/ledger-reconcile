# Generic utilities for loading directory trees into memory
# Used by tests and preview generators

import json
from pathlib import Path

import yaml

# Sentinel object to distinguish None values from "no parsed content"
_SENTINEL = object()


def load_file_content(file_path: Path) -> str:
    """Load file content as string."""
    return file_path.read_text(encoding="utf-8")


def load_structured_content(file_path: Path):
    """Load structured content (JSON/YAML) if possible."""
    if file_path.suffix == ".json":
        with file_path.open(encoding="utf-8") as f:
            return json.load(f)
    elif file_path.suffix in [".yaml", ".yml"]:
        with file_path.open(encoding="utf-8") as f:
            return yaml.safe_load(f)
    else:
        return _SENTINEL


def load_directory_tree(directory: Path) -> dict:
    """
    Load an entire directory tree into memory as a nested dict.

    Returns a dict where:
    - Keys are file/directory names
    - Values for files are dicts with 'content', 'path', 'stem', 'suffix'
      and optionally 'parsed' for JSON/YAML files
    - Values for directories are nested dicts of the same structure
    """
    if not directory.is_dir():
        raise ValueError(f"{directory} is not a directory")

    result = {}

    for item in directory.iterdir():
        if item.name.startswith("."):
            continue  # Skip hidden files

        if item.is_file():
            file_data = {
                "path": item,
                "content": load_file_content(item),
                "stem": item.stem,
                "suffix": item.suffix,
            }

            # Try to parse structured content
            structured = load_structured_content(item)
            if structured is not _SENTINEL:
                file_data["parsed"] = structured

            result[item.name] = file_data

        elif item.is_dir():
            result[item.name] = load_directory_tree(item)

    return result
