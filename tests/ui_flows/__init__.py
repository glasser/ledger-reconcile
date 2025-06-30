#!/usr/bin/env python3
# UI flow testing framework

import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
import yaml
from jinja2 import Template
from syrupy.extensions.single_file import SingleFileSnapshotExtension
from textual.pilot import Pilot

from ledger_reconcile.reconcile_interface import ReconcileApp


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


class SVGSnapshotExtension(SingleFileSnapshotExtension):
    """Custom extension for SVG snapshots."""

    _file_extension = "svg"

    def serialize(self, data, **_kwargs):
        """Serialize SVG content as text."""
        if isinstance(data, str):
            return data.encode("utf-8")
        return str(data).encode("utf-8")


# Single global stash key instance
_UI_SNAPSHOT_FAILURES_KEY = pytest.StashKey[list[UISnapshotDiff]]()


def collect_snapshot_failure(
    request,
    test_name: str,
    step_name: str,
    step_description: str,
    actual_svg: str,
    expected_svg: str,
    test_file_path: Path,
    test_function_name: str,
    docstring: str,
):
    """Collect a snapshot failure for later reporting."""
    failure = UISnapshotDiff(
        test_name=test_name,
        step_name=step_name,
        step_description=step_description,
        actual_svg=actual_svg,
        expected_svg=expected_svg,
        test_file_path=test_file_path,
        test_function_name=test_function_name,
        docstring=docstring,
    )

    # Store in pytest's session stash
    failures = request.session.stash.setdefault(_UI_SNAPSHOT_FAILURES_KEY, [])
    failures.append(failure)


@pytest.fixture
def snapshot(snapshot):
    """Configure snapshot to use SVG extension."""
    return snapshot.with_defaults(extension_class=SVGSnapshotExtension)


@dataclass
class UITestStep:
    """Represents a single step in a UI test flow."""

    action: str  # 'key', 'snapshot', 'assert_file', 'wait'
    data: dict[str, Any]  # Action-specific data
    description: str = ""


@dataclass
class UITestCase:
    """Represents a complete UI test case."""

    name: str
    description: str
    initial_ledger: str
    account: str
    target_amount: str
    steps: list[UITestStep]


def load_ui_test_case(test_dir: Path) -> UITestCase:
    """Load a UI test case from a directory containing config.yaml and other files."""
    config_path = test_dir / "config.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"No config.yaml found in {test_dir}")

    with config_path.open() as f:
        config = yaml.safe_load(f)

    # Load initial ledger file
    initial_ledger_path = test_dir / "initial.ledger"
    if not initial_ledger_path.exists():
        raise FileNotFoundError(f"No initial.ledger found in {test_dir}")

    with initial_ledger_path.open() as f:
        initial_ledger = f.read()

    # Parse steps
    steps = []
    for step_data in config.get("steps", []):
        step = UITestStep(
            action=step_data["action"],
            data=step_data.get("data", {}),
            description=step_data.get("description", ""),
        )
        steps.append(step)

    return UITestCase(
        name=config["name"],
        description=config.get("description", ""),
        initial_ledger=initial_ledger,
        account=config["account"],
        target_amount=config["target_amount"],
        steps=steps,
    )


class UITestRunner:
    """Runs UI test cases with event simulation and assertions."""

    def __init__(self, test_case: UITestCase, test_dir: Path):
        self.test_case = test_case
        self.test_dir = test_dir
        self.temp_ledger_file: Path | None = None
        self.app: ReconcileApp | None = None
        self.pilot: Pilot | None = None

    async def setup(self):
        """Set up the test environment."""
        # Create temporary ledger file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ledger", delete=False) as f:
            f.write(self.test_case.initial_ledger)
            self.temp_ledger_file = Path(f.name)

        # Create the app
        self.app = ReconcileApp(
            self.temp_ledger_file, self.test_case.account, self.test_case.target_amount
        )

    async def cleanup(self):
        """Clean up test environment."""
        if self.temp_ledger_file and self.temp_ledger_file.exists():
            self.temp_ledger_file.unlink()

    async def run_step(self, step: UITestStep) -> dict[str, Any]:  # noqa: PLR0912, PLR0915
        """Run a single test step and return any results."""
        result = {"step": step.action, "description": step.description}

        if step.action == "key":
            # Simulate key press
            key = step.data["key"]
            if self.pilot:
                await self.pilot.press(key)
            result["key"] = key

        elif step.action == "wait":
            # Wait for specified duration
            duration = step.data.get("duration", 0.1)
            if self.pilot:
                await self.pilot.pause(duration)
            result["duration"] = duration

        elif step.action == "snapshot":
            # Take a screenshot snapshot
            snapshot_name = step.data.get("name", "snapshot")
            result["snapshot_name"] = snapshot_name
            if self.app:
                result["screenshot"] = self.app.export_screenshot()
            else:
                result["screenshot"] = ""

        elif step.action == "assert_file":
            # Assert ledger file matches expected content
            expected_file = step.data["file"]
            expected_path = self.test_dir / expected_file

            if not expected_path.exists():
                raise FileNotFoundError(f"Expected file not found: {expected_path}")

            with expected_path.open() as f:
                expected_content = f.read()

            if self.temp_ledger_file:
                with self.temp_ledger_file.open() as f:
                    actual_content = f.read()
            else:
                actual_content = ""

            result["expected_file"] = expected_file
            result["file_matches"] = expected_content.strip() == actual_content.strip()
            result["actual_content"] = actual_content
            result["expected_content"] = expected_content

        elif step.action == "assert_ui":
            # Assert UI state (e.g., specific text visible, table contents)
            assertion_type = step.data["type"]

            if assertion_type == "table_rows":
                # Check number of rows in the table
                if self.app:
                    from textual.widgets import DataTable

                    table = self.app.query_one("#transactions-table", DataTable)
                    expected_rows = step.data["count"]
                    actual_rows = table.row_count
                    result["expected_rows"] = expected_rows  # type: ignore[assignment]
                    result["actual_rows"] = actual_rows  # type: ignore[assignment]
                    result["assertion_passed"] = expected_rows == actual_rows  # type: ignore[assignment]
                else:
                    result["assertion_passed"] = False  # type: ignore[assignment]

            elif assertion_type == "balance":
                # Check displayed balance
                if self.app:
                    from textual.widgets import Label

                    balance_label = self.app.query_one("#balance-label", Label)
                    expected_balance = step.data["value"]
                    actual_balance = balance_label.renderable
                    result["expected_balance"] = expected_balance
                    result["actual_balance"] = str(actual_balance)
                    result["assertion_passed"] = expected_balance in str(actual_balance)  # type: ignore[assignment]
                else:
                    result["assertion_passed"] = False  # type: ignore[assignment]

        return result

    async def run_test(self) -> dict[str, Any]:
        """Run the complete test case."""
        await self.setup()

        try:
            results = {
                "test_name": self.test_case.name,
                "description": self.test_case.description,
                "account": self.test_case.account,
                "target_amount": self.test_case.target_amount,
                "steps": [],
            }

            for step in self.test_case.steps:
                step_result = await self.run_step(step)
                results["steps"].append(step_result)

            return results

        finally:
            await self.cleanup()


# Test discovery and execution
def discover_ui_test_cases(base_dir: Path) -> list[Path]:
    """Discover all UI test case directories."""
    test_dirs = []
    for item in base_dir.iterdir():
        if item.is_dir() and (item / "config.yaml").exists():
            test_dirs.append(item)
    return sorted(test_dirs)


def pytest_generate_tests(metafunc):
    """Generate pytest tests for each UI test case."""
    if "test_case_dir" in metafunc.fixturenames:
        test_dir = Path(__file__).parent / "test_cases"
        if test_dir.exists():
            test_cases = discover_ui_test_cases(test_dir)
            metafunc.parametrize(
                "test_case_dir",
                test_cases,
                ids=[tc.name for tc in test_cases],
            )


@pytest.mark.asyncio
async def test_ui_flow(test_case_dir, snapshot, request):
    """Run a UI flow test case with snapshot testing."""
    # Load the test case
    test_case = load_ui_test_case(test_case_dir)
    runner = UITestRunner(test_case, test_case_dir)

    await runner.setup()

    try:
        # Start the app
        if not runner.app:
            raise RuntimeError("App not initialized")
        async with runner.app.run_test() as pilot:
            runner.pilot = pilot

            # Run each step
            for i, step in enumerate(test_case.steps):
                result = await runner.run_step(step)

                # If it's a snapshot step, use syrupy with SVG content
                if step.action == "snapshot":
                    snapshot_name = step.data.get("name", f"step_{i}")
                    # Get SVG content from the result
                    svg_content = result.get("screenshot", "")

                    try:
                        assert svg_content == snapshot(name=snapshot_name)
                    except AssertionError:
                        # Capture the failure details for reporting
                        expected_svg = ""
                        snapshot_file = None

                        # Try to read the expected snapshot file
                        try:
                            snapshot_file = (
                                Path(__file__).parent
                                / "__snapshots__"
                                / "__init__"
                                / f"test_ui_flow[{test_case_dir.name}][{snapshot_name}].svg"
                            )
                            if snapshot_file.exists():
                                expected_svg = snapshot_file.read_text()
                        except OSError:
                            # Ignore file reading errors
                            pass

                        # Collect the failure for report generation
                        collect_snapshot_failure(
                            request=request,
                            test_name=f"test_ui_flow[{test_case_dir.name}]",
                            step_name=snapshot_name,
                            step_description=step.description,
                            actual_svg=svg_content,
                            expected_svg=expected_svg,
                            test_file_path=Path(__file__),
                            test_function_name="test_ui_flow",
                            docstring=test_ui_flow.__doc__ or "",
                        )

                        # Generate report immediately for testing
                        failures = request.session.stash.get(
                            _UI_SNAPSHOT_FAILURES_KEY, []
                        )
                        if failures:
                            report_path = Path("ui_snapshot_report.html")
                            _generate_snapshot_report(failures, report_path)

                        raise  # Re-raise the assertion error

                # If it's an assert step, verify it passed
                elif step.action in ["assert_file", "assert_ui"]:
                    if step.action == "assert_file":
                        assert result["file_matches"], (
                            f"File content mismatch at step {i}: {step.description}"
                        )
                    elif step.action == "assert_ui":
                        assert result["assertion_passed"], (
                            f"UI assertion failed at step {i}: {step.description}"
                        )

    finally:
        await runner.cleanup()


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

        # Store for terminal summary
        session.config._ui_snapshot_failures = failures
        session.config._ui_snapshot_report_path = report_path


def pytest_terminal_summary(terminalreporter, exitstatus, config):  # noqa: ARG001
    """Add UI snapshot report info to terminal summary."""
    failures = getattr(config, "_ui_snapshot_failures", None)
    if failures:
        report_path = getattr(config, "_ui_snapshot_report_path", None)
        terminalreporter.write_line("")
        terminalreporter.write_line("=" * 60, red=True)
        terminalreporter.write_line(
            f"UI SNAPSHOT FAILURES: {len(failures)} mismatched snapshots", red=True
        )
        if report_path:
            terminalreporter.write_line(
                f"View report: {report_path.absolute()}", yellow=True
            )
        terminalreporter.write_line("=" * 60, red=True)


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
