#!/usr/bin/env python3
# UI flow testing framework

import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from jinja2 import Template
from mashumaro import DataClassDictMixin
from rich.console import Console
from syrupy.extensions.image import SVGImageSnapshotExtension
from textual.pilot import Pilot
from textual.widgets import DataTable, Label

from ledger_reconcile.reconcile_interface import ReconcileApp
from tests.fixture_utils import load_directory_tree


@dataclass
class UISnapshotDiff:
    """Represents a UI snapshot failure for reporting."""

    test_name: str
    step_name: str
    step_description: str
    actual_svg: str
    expected_svg: str
    test_file_path: Path
    test_function_name: str
    docstring: str


class CustomLocationSVGExtension(SVGImageSnapshotExtension):
    """SVG extension with custom location for test case directories."""

    @classmethod
    def get_location(cls, *, test_location, index) -> str:
        """Returns full filepath where snapshot data is stored."""
        # Extract test case name from parametrized test
        nodename = test_location.nodename
        if nodename:
            match = re.search(r"\[(.*?)\]", nodename)
            if match and isinstance(index, str):
                test_case_name = match.group(1)
                test_dir = Path(test_location.filepath).parent
                snapshot_dir = (
                    test_dir / "test_cases" / test_case_name / "__snapshots__"
                )
                return str(snapshot_dir / f"{index}.{cls._file_extension}")
        # Fallback to default behavior
        return super().get_location(test_location=test_location, index=index)


# Global stash key instances
_UI_SNAPSHOT_FAILURES_KEY = pytest.StashKey[list[UISnapshotDiff]]()
_UI_SNAPSHOT_REPORT_PATH_KEY = pytest.StashKey[Path]()


@pytest.fixture
def snapshot(snapshot):
    """Configure snapshot to use SVG extension."""
    return snapshot.with_defaults(extension_class=CustomLocationSVGExtension)


@dataclass
class UITestStep(DataClassDictMixin):
    """Represents a single step in a UI test flow."""

    action: str  # 'key', 'snapshot', 'assert_file', 'wait'
    data: dict[str, Any]  # Action-specific data
    description: str = ""


@dataclass
class UITestCase(DataClassDictMixin):
    """Represents a complete UI test case."""

    name: str
    description: str
    account: str
    target_amount: str
    steps: list[UITestStep]


class UITestRunner:
    """Runs UI test cases with event simulation and assertions."""

    def __init__(
        self,
        test_case: UITestCase,
        test_case_tree: dict,
        pilot: Pilot,
        app: ReconcileApp,
        temp_ledger_file: Path,
        snapshot,
        request,
    ):
        self.test_case = test_case
        self.test_case_tree = test_case_tree
        self.pilot = pilot
        self.app = app
        self.temp_ledger_file = temp_ledger_file
        self.snapshot = snapshot
        self.request = request

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - clean up test environment."""
        if self.temp_ledger_file.exists():
            self.temp_ledger_file.unlink()

    async def run(self, step: UITestStep, step_index: int) -> None:
        """Run a single test step."""
        action_method = getattr(self, f"run_{step.action}", None)
        if not action_method:
            raise ValueError(f"Unknown action: {step.action}")

        await action_method(step, step_index)

    async def run_key(self, step: UITestStep, _step_index: int) -> None:
        """Simulate key press."""
        key = step.data["key"]
        await self.pilot.press(key)

    async def run_wait(self, step: UITestStep, _step_index: int) -> None:
        """Wait for specified duration."""
        duration = step.data.get("duration", 0.1)
        await self.pilot.pause(duration)

    async def run_snapshot(self, step: UITestStep, step_index: int) -> None:
        """Take a screenshot snapshot and assert it matches."""
        snapshot_name = step.data.get("name", f"step_{step_index}")
        svg_content = self.app.export_screenshot()

        try:
            assert svg_content == self.snapshot(name=snapshot_name)
        except AssertionError:
            # Capture the failure details for reporting
            expected_svg = ""

            # Try to read the expected snapshot from tree data
            try:
                snapshots_dir = self.test_case_tree.get("__snapshots__", {})
                snapshot_file_data = snapshots_dir.get(f"{snapshot_name}.svg")
                if snapshot_file_data and "content" in snapshot_file_data:
                    expected_svg = snapshot_file_data["content"]
            except (KeyError, TypeError):
                # Ignore data access errors
                pass

            # Collect the failure for report generation
            test_case_name = self.test_case.name
            failure = UISnapshotDiff(
                test_name=f"test_ui_flow[{test_case_name}]",
                step_name=snapshot_name,
                step_description=step.description,
                actual_svg=svg_content,
                expected_svg=expected_svg,
                test_file_path=Path(__file__),
                test_function_name="test_ui_flow",
                docstring=test_ui_flow.__doc__ or "",
            )
            failures = self.request.session.stash.setdefault(
                _UI_SNAPSHOT_FAILURES_KEY, []
            )
            failures.append(failure)

            raise  # Re-raise the assertion error

    async def run_assert_file(self, step: UITestStep, step_index: int) -> None:
        """Assert ledger file matches expected content."""
        expected_file = step.data["file"]
        expected_file_data = self.test_case_tree.get(expected_file)

        if not expected_file_data or "content" not in expected_file_data:
            raise FileNotFoundError(f"Expected file not found: {expected_file}")

        expected_content = expected_file_data["content"]

        with self.temp_ledger_file.open() as f:
            actual_content = f.read()

        assert expected_content == actual_content, (
            f"File content mismatch at step {step_index}: {step.description}"
        )

    async def run_assert_ui(self, step: UITestStep, step_index: int) -> None:
        """Assert UI state (e.g., specific text visible, table contents)."""
        assertion_type = step.data["type"]

        if assertion_type == "table_rows":
            # Check number of rows in the table
            table = self.app.query_one("#transactions-table", DataTable)
            expected_rows = step.data["count"]
            actual_rows = table.row_count
            assert expected_rows == actual_rows, (
                f"Expected {expected_rows} table rows, got {actual_rows} at step {step_index}: {step.description}"
            )

        elif assertion_type == "balance":
            # Check displayed balance
            balance_label = self.app.query_one("#balance-label", Label)
            expected_balance = step.data["value"]
            actual_balance = str(balance_label.renderable)
            assert expected_balance in actual_balance, (
                f"Expected balance '{expected_balance}' not found in '{actual_balance}' at step {step_index}: {step.description}"
            )

    async def run_modify_file(self, step: UITestStep, _step_index: int) -> None:
        """Modify the ledger file externally to test file watcher functionality."""
        new_content_file = step.data["content_file"]
        new_content_data = self.test_case_tree.get(new_content_file)

        if not new_content_data or "content" not in new_content_data:
            raise FileNotFoundError(f"Content file not found: {new_content_file}")

        new_content = new_content_data["content"]

        # Write new content to the ledger file (simulating external modification)
        with self.temp_ledger_file.open("w") as f:
            f.write(new_content)

        # Force filesystem sync
        os.sync()

        # Wait a moment for the file watcher to detect the change
        await self.pilot.pause(0.5)


# Test discovery and execution
def discover_ui_test_cases(base_dir: Path) -> list[tuple[str, dict]]:
    """Discover all UI test case data using load_directory_tree."""
    if not base_dir.exists():
        return []

    tree = load_directory_tree(base_dir)
    test_cases = []

    for name, content in tree.items():
        if isinstance(content, dict) and "config.yaml" in content:
            test_cases.append((name, content))

    return sorted(test_cases, key=lambda x: x[0])


def pytest_generate_tests(metafunc):
    """Generate pytest tests for each UI test case."""
    if "test_case_data" in metafunc.fixturenames:
        test_dir = Path(__file__).parent / "test_cases"
        if test_dir.exists():
            test_cases = discover_ui_test_cases(test_dir)
            metafunc.parametrize(
                "test_case_data",
                [content for _name, content in test_cases],
                ids=[name for name, _content in test_cases],
            )


@pytest.mark.asyncio
async def test_ui_flow(test_case_data, snapshot, request):
    """Run a UI flow test case with snapshot testing."""
    # Parse the test case from the injected tree data
    config_file = test_case_data.get("config.yaml")
    if not config_file or "parsed" not in config_file:
        raise FileNotFoundError("No config.yaml found in test case data")

    config = config_file["parsed"]
    test_case = UITestCase.from_dict(config)

    # Create app for pilot
    initial_ledger_file = test_case_data.get("initial.ledger")
    if not initial_ledger_file or "content" not in initial_ledger_file:
        raise FileNotFoundError("No initial.ledger found in test case data")

    initial_ledger = initial_ledger_file["content"]
    with tempfile.NamedTemporaryFile(mode="w", suffix=".ledger", delete=False) as f:
        f.write(initial_ledger)
        temp_file = Path(f.name)

    app = ReconcileApp(temp_file, test_case.account, test_case.target_amount)

    async with app.run_test() as pilot:
        with UITestRunner(
            test_case, test_case_data, pilot, app, temp_file, snapshot, request
        ) as runner:
            # Run each step
            for i, step in enumerate(test_case.steps):
                await runner.run(step, i)


def pytest_addoption(parser):
    """Add command line options for UI snapshot reports."""
    parser.addoption(
        "--ui-snapshot-report",
        action="store",
        default="ui_snapshot_report.html",
        help="UI snapshot test output HTML path.",
    )


def pytest_sessionfinish(session, exitstatus):  # noqa: ARG001
    """Generate HTML report for UI snapshot failures at end of test session."""
    failures = session.stash.get(_UI_SNAPSHOT_FAILURES_KEY, [])

    if failures:
        report_path = Path(session.config.getoption("--ui-snapshot-report"))
        _generate_snapshot_report(failures, report_path)

        # Store data in config stash for terminal summary (accessible from config)
        session.config.stash[_UI_SNAPSHOT_FAILURES_KEY] = failures
        session.config.stash[_UI_SNAPSHOT_REPORT_PATH_KEY] = report_path


def pytest_terminal_summary(terminalreporter, exitstatus, config):  # noqa: ARG001
    """Add UI snapshot report info to terminal summary."""
    # Access data from config stash (no private attributes needed)
    failures = config.stash.get(_UI_SNAPSHOT_FAILURES_KEY, [])

    if failures:
        report_path = config.stash.get(_UI_SNAPSHOT_REPORT_PATH_KEY, None)
        console = Console(legacy_windows=False, force_terminal=True)
        with console.capture() as capture:
            console.print(
                f"[black on red]{len(failures)} mismatched UI Flow snapshots[/]\n"
                f"[b]View the [link=file://{report_path.absolute()}]failure report[/].\n"
            )
        terminalreporter.write_sep("-", title="UI Flows snapshot report")
        terminalreporter.write(capture.get())


def _generate_snapshot_report(failures: list[UISnapshotDiff], report_path: Path):
    """Generate HTML report showing snapshot failures with side-by-side comparison."""
    template_path = Path(__file__).parent / "snapshot_report_template.html.j2"

    with template_path.open("r", encoding="utf-8") as f:
        template_content = f.read()

    template = Template(template_content)
    rendered_report = template.render(failures=failures, now=datetime.now())

    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", encoding="utf-8") as f:
        f.write(rendered_report)
