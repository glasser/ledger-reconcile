#!/usr/bin/env python3
# File watcher for monitoring ledger file changes

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.api import BaseObserver


class LedgerFileWatcher:
    """Watches ledger file for external changes and notifies callbacks."""

    def __init__(self, file_path: Path, on_change: Callable[[], None]) -> None:
        self.file_path = file_path
        self.on_change = on_change
        self.observer: BaseObserver | None = None
        self.last_modification_time = 0.0
        self.ignore_next_change = False

    def start(self) -> None:
        """Start watching the file for changes."""
        if self.observer is not None:
            return

        self.last_modification_time = self._get_modification_time()

        event_handler = LedgerFileEventHandler(self)
        self.observer = Observer()
        if self.observer is not None:
            self.observer.schedule(
                event_handler, str(self.file_path.parent), recursive=False
            )
            self.observer.start()

    def stop(self) -> None:
        """Stop watching the file for changes."""
        if self.observer is not None:
            self.observer.stop()
            self.observer.join()
            self.observer = None

    def mark_internal_change(self) -> None:
        """Mark that we're making an internal change - ignore the next file event."""
        self.ignore_next_change = True
        # Update our tracking of the modification time
        self.last_modification_time = self._get_modification_time()

    def _get_modification_time(self) -> float:
        """Get the current modification time of the file."""
        try:
            return self.file_path.stat().st_mtime
        except FileNotFoundError:
            return 0.0

    def _handle_file_change(self) -> None:
        """Handle a file change event."""
        current_mod_time = self._get_modification_time()

        # Check if this is a change we made ourselves
        if self.ignore_next_change:
            self.ignore_next_change = False
            self.last_modification_time = current_mod_time
            return

        # Check if the file was actually modified
        if current_mod_time <= self.last_modification_time:
            return

        self.last_modification_time = current_mod_time

        # Give a small delay to ensure the write is complete
        time.sleep(0.1)

        # Notify the callback
        self.on_change()


class LedgerFileEventHandler(FileSystemEventHandler):
    """Event handler for file system events."""

    def __init__(self, watcher: LedgerFileWatcher):
        self.watcher = watcher
        super().__init__()

    def on_modified(self, event: FileSystemEvent) -> None:
        """Handle file modification events."""
        if event.is_directory:
            return

        # Resolve both paths to handle symlinks (e.g., /var -> /private/var on macOS)
        event_path = Path(str(event.src_path)).resolve()
        watched_path = self.watcher.file_path.resolve()

        if event_path == watched_path:
            self.watcher._handle_file_change()

    def on_moved(self, event: FileSystemEvent) -> None:
        """Handle file move events (important for atomic rewrites)."""
        if event.is_directory:
            return

        # Check if destination matches our watched file (atomic rewrite pattern)
        if hasattr(event, "dest_path"):
            dest_path = Path(str(event.dest_path)).resolve()
            watched_path = self.watcher.file_path.resolve()

            if dest_path == watched_path:
                self.watcher._handle_file_change()

    def on_created(self, event: FileSystemEvent) -> None:
        """Handle file creation events (may occur during atomic rewrites)."""
        if event.is_directory:
            return

        # Resolve both paths to handle symlinks (e.g., /var -> /private/var on macOS)
        event_path = Path(str(event.src_path)).resolve()
        watched_path = self.watcher.file_path.resolve()

        if event_path == watched_path:
            self.watcher._handle_file_change()


class SafeFileEditor:
    """Provides safe file editing with race condition prevention."""

    def __init__(self, file_path: Path):
        self.file_path = file_path
        self._last_read_time = 0.0

    def read_lines_safely(self) -> tuple[list[str], float]:
        """Read file lines and return them with the read timestamp."""
        try:
            with self.file_path.open(encoding="utf-8") as f:
                lines = f.readlines()
        except FileNotFoundError:
            return [], time.time()
        else:
            read_time = time.time()
            self._last_read_time = read_time
            return lines, read_time

    def write_lines_safely(self, lines: list[str], read_time: float) -> bool:
        """Write lines to file, but only if the file hasn't changed since read_time.

        Returns True if the write was successful, False if the file was modified
        since the read and the write was skipped to avoid race conditions.
        """
        try:
            # Check if the file was modified since we read it
            current_mod_time = self.file_path.stat().st_mtime
            if current_mod_time > read_time:
                # File was modified since we read it - abort to avoid race condition
                return False
        except FileNotFoundError:
            # File doesn't exist yet, safe to write
            pass

        # Write the file atomically
        temp_file = self.file_path.with_suffix(self.file_path.suffix + ".tmp")
        try:
            with temp_file.open("w", encoding="utf-8") as f:
                f.writelines(lines)

            # Atomic rename
            temp_file.replace(self.file_path)
        except OSError:
            # Clean up temp file if something went wrong
            if temp_file.exists():
                temp_file.unlink()
            return False
        else:
            return True
