"""Human-readable CLI; every mutation of an approval requires its current ID."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Annotated

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

from .model import ModelClient
from .runtime import Runtime, project_root, read_json
from .skill_registry import SkillRegistry

for _stream in (sys.stdout, sys.stderr):
    if not _stream.isatty() and hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

app = typer.Typer(help="有依据的短视频脚本 Agent：Python / LangGraph / Skills / 人工审核", pretty_exceptions_enable=False)
skills_app = typer.Typer(help="查看可按需加载的业务技能")
app.add_typer(skills_app, name="skills")
console = Console()


@app.callback()
def main(ctx: typer.Context, runs_dir: Annotated[Path | None, typer.Option(help="本地运行状态目录")] = None):
    load_dotenv(override=False)
    ctx.obj = {"runs_dir": runs_dir or Path(os.getenv("SCRIPT_AGENT_RUNS_DIR", ".runs"))}


def runtime(ctx: typer.Context, mode: str = "live") -> Runtime:
    if mode == "mock":
        from .mock_model import MockModel
        model = MockModel()
    elif mode == "live":
        model = ModelClient()
    else:
        raise ValueError("mode 必须为 live 或 mock。")
    return Runtime(model, ctx.obj["runs_dir"])


def show(state: dict, output_json: bool = False) -> None:
    if output_json:
        typer.echo(json.dumps(Runtime.output(state), ensure_ascii=False))
        return
    console.print(f"任务 [bold]{state['run_id']}[/bold]  状态={state['status']}  阶段={state['phase']}  模式={state['mode']}")
    console.print(f"模型请求 {state['model_calls']}/{state['max_model_calls']}；工具调用 {state['tool_calls']}/{state['max_tool_calls']}")
    if state.get("direction"):
        console.print("创作方向：", state["direction"]["angle"], markup=False)
    if state.get("script"):
        table = Table(title=state["script"]["title"])
        for label in ("镜头", "画面", "旁白", "字幕", "来源"):
            table.add_column(label)
        for scene in state["script"]["scenes"]:
            table.add_row(scene["scene_id"], scene["visual"], scene["narration"], scene["subtitle"], ",".join(scene["source_ids"]))
        console.print(table)
    for name, report in state.get("checks", {}).items():
        console.print(f"{name}：{'通过' if report.get('passed') else '未通过'}；版本 {report.get('script_version')}")
        if name == "duration":
            console.print(f"预计时长：{report.get('estimated_seconds', '未知')} 秒（估算）")
        for issue in report.get("issues", []):
            console.print("  - " + issue.get("message", str(issue)), markup=False)
    if state.get("pending_review"):
        pending = state["pending_review"]
        console.print(f"待处理：{pending['stage']}；review-id：{pending['review_id']}")
        console.print(pending["reason"], markup=False)
        console.print("使用 resume --run-id ... --review-id ... --decision approve|revise|cancel；澄清请求使用 reply。")
    if state.get("stop_reason"):
        console.print(state["stop_reason"]["message"], markup=False)
    if state["mode"] == "mock":
        console.print("[yellow]离线 Mock：只验证流程，不证明真实模型决策能力。[/yellow]")


def fail(exc: Exception):
    console.print(f"[red]错误：[/red]{str(exc)}", markup=False)
    raise typer.Exit(code=2)


@app.command()
def run(ctx: typer.Context,
        input: Annotated[Path, typer.Option(exists=True, dir_okay=False, help="创作请求 JSON")],
        mode: Annotated[str, typer.Option(help="live 或 mock")] = "live",
        output_json: Annotated[bool, typer.Option("--json", help="输出机器可读结果")] = False):
    """开始新任务，运行到人工中断或结束。"""
    try:
        show(runtime(ctx, mode).start(read_json(input), mode=mode), output_json)
    except Exception as exc:
        fail(exc)


@app.command()
def status(ctx: typer.Context, run_id: Annotated[str, typer.Option()], output_json: Annotated[bool, typer.Option("--json")] = False):
    """查询任务；此操作不请求模型。"""
    try:
        show(runtime(ctx).get(run_id), output_json)
    except Exception as exc:
        fail(exc)


@app.command()
def review(ctx: typer.Context, run_id: Annotated[str, typer.Option()], output_json: Annotated[bool, typer.Option("--json")] = False):
    """显示当前审核内容、检查结果及 review-id。"""
    status(ctx, run_id, output_json)


@app.command()
def resume(ctx: typer.Context,
           run_id: Annotated[str, typer.Option()],
           review_id: Annotated[str, typer.Option(help="必须为当前待处理请求 ID")],
           decision: Annotated[str, typer.Option(help="approve / revise / cancel / reply")],
           feedback: str = "",
           answers: Annotated[Path | None, typer.Option(help="澄清字段补充 JSON")] = None,
           output_json: Annotated[bool, typer.Option("--json")] = False):
    """批准、提交修改意见、取消，或补充需求后恢复。"""
    try:
        existing = runtime(ctx).get(run_id)
        service = runtime(ctx, existing["mode"])
        result = service.resume(run_id, decision, feedback=feedback,
                                answers=read_json(answers) if answers else None,
                                review_id=review_id)
        show(result, output_json)
    except Exception as exc:
        fail(exc)


@app.command()
def export(ctx: typer.Context, run_id: Annotated[str, typer.Option()],
           output: Annotated[Path, typer.Option(help="导出目录")]):
    """导出 JSON、Markdown、资料快照和 Trace，保留实际任务状态。"""
    try:
        state = runtime(ctx).export(run_id, output)
        console.print(f"已导出到 {output.resolve()}；实际状态：{state['status']}")
    except Exception as exc:
        fail(exc)


@skills_app.command("list")
def skills_list():
    """列出技能摘要；模型运行时才按需加载正文。"""
    table = Table("技能 ID", "版本", "适用场景")
    for skill in SkillRegistry(project_root() / "skills").catalog():
        table.add_row(skill["name"], skill["version"], skill["description"])
    console.print(table)


if __name__ == "__main__":
    app()
