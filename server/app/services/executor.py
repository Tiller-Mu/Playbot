"""测试执行服务 - 调用 pytest + playwright 执行测试。"""
import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.websocket import ws_manager
from app.models.database import TestCase, Execution, ExecutionDetail, async_session

log = logging.getLogger(__name__)


async def run_tests(
    execution_id: str,
    case_ids: list[str],
    project_base_url: str,
    headless: bool = True,
):
    """Execute test cases using pytest + playwright in a subprocess."""
    async with async_session() as db:
        execution = await db.get(Execution, execution_id)
        if not execution:
            return

        try:
            await _do_run(db, execution, case_ids, project_base_url, headless)
        except Exception as exc:
            log.exception("Test execution failed: %s", exc)
            execution.status = "error"
            execution.end_time = datetime.now(timezone.utc)
            await db.commit()
            await ws_manager.broadcast(
                {"type": "execution:complete", "execution_id": execution_id, "status": "error"},
                channel=f"execution:{execution_id}",
            )


async def _do_run(
    db: AsyncSession,
    execution: Execution,
    case_ids: list[str],
    project_base_url: str,
    headless: bool,
):
    execution_id = execution.id

    # Load test cases
    result = await db.execute(
        select(TestCase).where(TestCase.id.in_(case_ids))
    )
    test_cases = list(result.scalars().all())

    if not test_cases:
        execution.status = "error"
        await db.commit()
        return

    # Create temp test directory for this execution
    exec_dir = settings.tests_dir / execution_id
    exec_dir.mkdir(parents=True, exist_ok=True)
    results_dir = exec_dir / "results"
    results_dir.mkdir(exist_ok=True)

    # Write conftest.py with base_url
    conftest = exec_dir / "conftest.py"
    conftest.write_text(
        f'import pytest\n\n'
        f'@pytest.fixture(scope="session")\n'
        f'def browser_context_args(browser_context_args):\n'
        f'    return {{**browser_context_args, "base_url": "{project_base_url}"}}\n',
        encoding="utf-8",
    )

    # Write each test case to a file
    case_file_map: dict[str, str] = {}
    for tc in test_cases:
        filename = f"test_{tc.id.replace('-', '_')}.py"
        filepath = exec_dir / filename
        filepath.write_text(tc.script_content or "# empty test", encoding="utf-8")
        case_file_map[filename] = tc.id

    # Update execution status
    execution.status = "running"
    execution.start_time = datetime.now(timezone.utc)
    execution.total_cases = len(test_cases)
    await db.commit()

    await ws_manager.broadcast(
        {"type": "execution:start", "execution_id": execution_id, "total": len(test_cases)},
        channel=f"execution:{execution_id}",
    )

    # Build pytest command
    python_bin = sys.executable  # Use the same Python as the server
    report_path = results_dir / "report.json"
    cmd_parts = [
        python_bin, "-m", "pytest", str(exec_dir),
        "--tb=short", "-v",
        "--screenshot", "on",
        "--output", str(results_dir),
        "--json-report", f"--json-report-file={report_path}",
    ]
    if not headless:
        cmd_parts.append("--headed")

    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    # Ensure user-installed packages are discoverable
    env["PATH"] = os.path.expanduser("~/.local/bin") + ":" + env.get("PATH", "")

    log.info("Running: %s", " ".join(cmd_parts))

    process = await asyncio.create_subprocess_exec(
        *cmd_parts,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    stdout, stderr = await process.communicate()

    log.info("pytest exit code: %s", process.returncode)
    if stderr:
        log.debug("pytest stderr:\n%s", stderr.decode(errors="replace")[:2000])

    # Parse results
    if report_path.exists():
        try:
            report = json.loads(report_path.read_text())
            await _process_report(db, execution, report, case_file_map, results_dir)
        except Exception as exc:
            log.exception("Failed to process report: %s", exc)
            execution.status = "error"
    else:
        log.warning("No report.json found, falling back to exit code")
        execution.status = "passed" if process.returncode == 0 else "failed"

    execution.end_time = datetime.now(timezone.utc)
    if execution.status == "running":
        execution.status = "passed" if execution.failed_count == 0 else "failed"
    await db.commit()

    await ws_manager.broadcast(
        {
            "type": "execution:complete",
            "execution_id": execution_id,
            "status": execution.status,
            "passed": execution.passed_count,
            "failed": execution.failed_count,
        },
        channel=f"execution:{execution_id}",
    )


async def _process_report(
    db: AsyncSession,
    execution: Execution,
    report: dict,
    case_file_map: dict,
    results_dir: Path,
):
    """Process pytest-json-report output."""
    tests = report.get("tests", [])
    passed = 0
    failed = 0
    skipped = 0
    # Track which case_ids we've already recorded (pytest-playwright may
    # produce multiple nodeid entries per file, e.g. [chromium], [firefox]).
    seen_cases: set[str] = set()

    for test in tests:
        nodeid = test.get("nodeid", "")
        # nodeid example: "test_abc_def.py::test_func[chromium]"
        # Extract filename portion before "::"
        filename = nodeid.split("::")[0].split("/")[-1]
        case_id = case_file_map.get(filename)
        if not case_id or case_id in seen_cases:
            continue
        seen_cases.add(case_id)

        outcome = test.get("outcome", "unknown")
        status = {"passed": "passed", "failed": "failed", "skipped": "skipped"}.get(
            outcome, "failed"
        )

        if status == "passed":
            passed += 1
        elif status == "failed":
            failed += 1
        else:
            skipped += 1

        error_msg = None
        call_info = test.get("call", {})
        if "longrepr" in call_info:
            error_msg = call_info["longrepr"]
        elif "crash" in call_info:
            crash = call_info["crash"]
            error_msg = f"{crash.get('path', '')}:{crash.get('lineno', '')} - {crash.get('message', '')}"

        detail = ExecutionDetail(
            execution_id=execution.id,
            test_case_id=case_id,
            status=status,
            error_message=error_msg,
            duration_ms=(call_info.get("duration", 0)) * 1000,
        )
        db.add(detail)

        await ws_manager.broadcast(
            {
                "type": "execution:progress",
                "execution_id": execution.id,
                "case_id": case_id,
                "status": status,
                "error": error_msg,
            },
            channel=f"execution:{execution.id}",
        )

    execution.passed_count = passed
    execution.failed_count = failed
    execution.skipped_count = skipped
