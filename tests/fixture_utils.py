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


def load_directory_tree(directory: Path, load_snapshots: bool = False) -> dict:  # noqa: PLR0912
    """
    Load an entire directory tree into memory as a nested dict.

    Returns a dict where:
    - Keys are file/directory names
    - Values for files are dicts with 'content', 'path', 'stem', 'suffix'
      and optionally 'parsed' for JSON/YAML files
    - Values for directories are nested dicts of the same structure

    If load_snapshots=True, also looks for SVG snapshots in __snapshots__ directory.
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
            result[item.name] = load_directory_tree(item, load_snapshots)

    # Post-process for UI test cases with YAML configs and snapshots
    if load_snapshots:
        # Transform UI test case structure if it uses YAML configs
        for test_case_name in list(result.keys()):
            if (
                isinstance(result[test_case_name], dict)
                and "config.yaml" in result[test_case_name]
            ):
                config_data = result[test_case_name]["config.yaml"].get("parsed", {})

                # Transform to UI test case format
                result[test_case_name]["ui_config"] = config_data
                result[test_case_name]["steps"] = config_data.get("steps", [])

                # Load initial ledger content
                if "initial.ledger" in result[test_case_name]:
                    result[test_case_name]["initial_ledger"] = result[test_case_name][
                        "initial.ledger"
                    ]["content"]

                # Load expected file contents for assert_file steps
                for step in result[test_case_name]["steps"]:
                    if step.get("action") == "assert_file":
                        expected_file = step["data"]["file"]
                        if expected_file in result[test_case_name]:
                            step["expected_content"] = result[test_case_name][
                                expected_file
                            ]["content"]

        # Look for snapshots directory relative to the test root
        # For ui_flows/test_cases, we want tests/__snapshots__/ui_flows/__init__
        if directory.name == "test_cases" and directory.parent.name == "ui_flows":
            test_root = directory.parent.parent  # tests/
            snapshots_dir = test_root / "__snapshots__" / "ui_flows" / "__init__"
        else:
            test_root = (
                directory.parent.parent.parent
                if directory.name == "test_cases"
                else directory.parent.parent
            )
            snapshots_dir = (
                test_root / "__snapshots__" / directory.parent.name / "__init__"
            )

        if snapshots_dir.exists():
            for svg_file in snapshots_dir.glob("*.svg"):
                # Try to match SVG files to test cases
                svg_content = svg_file.read_text(encoding="utf-8")

                # Parse filename: test_ui_flow[test_case_name]_snapshot_name.svg
                stem = svg_file.stem
                if "[" in stem and "]_" in stem:
                    # Extract test case name and snapshot name
                    bracket_start = stem.find("[")
                    bracket_end = stem.find("]_")
                    if bracket_start != -1 and bracket_end != -1:
                        test_case_name = stem[bracket_start + 1 : bracket_end]
                        snapshot_name = stem[bracket_end + 2 :]  # After "]_"

                        # Find matching test case and step
                        if test_case_name in result and isinstance(
                            result[test_case_name], dict
                        ):
                            for step in result[test_case_name].get("steps", []):
                                if (
                                    step.get("action") == "snapshot"
                                    and step.get("data", {}).get("name")
                                    == snapshot_name
                                ):
                                    step["svg_content"] = svg_content

    return result
