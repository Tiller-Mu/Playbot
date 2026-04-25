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

    from app.models.database import Project
    project = await db.get(Project, execution.project_id)
    credentials_dict = {}
    if project:
        if project.username:
            credentials_dict["username"] = project.username
        if project.password:
            credentials_dict["password"] = project.password
        if project_base_url:
            credentials_dict["login_url"] = project_base_url
    import json
    credentials_json = json.dumps(credentials_dict, ensure_ascii=False)

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
        f'    return {{**browser_context_args, "base_url": "{project_base_url or ""}"}}\n',
        encoding="utf-8",
    )

    # Write each test case to a file
    case_file_map: dict[str, str] = {}
    for tc in test_cases:
        filename = f"test_{tc.id.replace('-', '_')}.py"
        filepath = exec_dir / filename
        
        # 提取被保留在 description 中的 JSON 格式的用例计划
        import json
        plan_json = "{}"
        try:
            if tc.description and "{" in tc.description:
                # 为了防止 Python 字符串转义错误，在写入模板时对 json 做一次 dumps
                parsed_desc = json.loads(tc.description)
                plan_json = json.dumps(parsed_desc, ensure_ascii=False)
        except Exception:
            pass

        # 生成使用动态 ExecutionEngine 的包装层代码
        bridge_script = f'''import pytest
import json
import logging
from playwright.sync_api import Page, expect
from app.services.execution_engine import PlaybotExecutionEngine, StepExecutionError

# {tc.title}
def test_playbot_case(page: Page):
    plan_data = json.loads(r\"\"\"{plan_json}\"\"\")
    steps = plan_data.get("steps", [])
    
    if not steps:
        pytest.skip("此用例没有具体的步骤规划")
        
    credentials = json.loads(r\"\"\"{credentials_json}\"\"\")
    engine = PlaybotExecutionEngine(page, credentials)
    try:
        engine.execute_plan(steps)
    except StepExecutionError as e:
        pytest.fail(f"Step {{e.step_index}} Failed: {{e.message}}")
'''
        filepath.write_text(bridge_script, encoding="utf-8")
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
    env["PATH"] = os.path.expanduser("~/.local/bin") + os.pathsep + env.get("PATH", "")

    log.info("Running: %s", " ".join(cmd_parts))
    log.info("Working dir: %s", settings.base_dir)

    import subprocess
    try:
        process = await asyncio.to_thread(
            subprocess.run,
            cmd_parts,
            capture_output=True,
            timeout=300,
            cwd=str(settings.base_dir),
            env=env,
        )
    except subprocess.TimeoutExpired:
        log.error("pytest subprocess timed out after 300s")
        execution.status = "error"
        execution.end_time = datetime.now(timezone.utc)
        await db.commit()
        await ws_manager.broadcast(
            {"type": "execution:complete", "execution_id": execution_id, "status": "error", "message": "执行超时（5分钟）"},
            channel=f"execution:{execution_id}",
        )
        return

    stdout, stderr = process.stdout, process.stderr

    log.info("pytest exit code: %s", process.returncode)
    if stdout:
        log.info("pytest stdout:\n%s", stdout.decode(errors="replace")[:3000])
    if stderr:
        log.warning("pytest stderr:\n%s", stderr.decode(errors="replace")[:3000])

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
        
        # Update testcase latest status
        tc = await db.get(TestCase, case_id)
        if tc:
            tc.latest_status = status
            tc.latest_error_message = error_msg

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
