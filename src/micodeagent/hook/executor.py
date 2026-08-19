"""Hook 动作执行器：shell / prompt / http / subagent"""

from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import dataclass

from micodeagent.hook.rule import ActionType, Payload, Rule


@dataclass
class ExecutionResult:
    """动作执行结果。"""

    err: Exception | None = None
    blocked: bool = False
    reason: str = ""
    prompt: str = ""


class Executor:
    """四类动作执行器。"""

    def __init__(self):
        self._http_client = None  # 惰性创建

    async def run(self, rule: Rule, payload: Payload, *, blocking: bool) -> ExecutionResult:
        action = rule.action
        if action.type == ActionType.SHELL:
            return await self._run_shell(action.shell, payload, blocking, action.shell.timeout)
        if action.type == ActionType.PROMPT:
            return ExecutionResult(prompt=action.prompt.text)
        if action.type == ActionType.HTTP:
            return await self._run_http(action.http, payload, blocking)
        if action.type == ActionType.SUBAGENT:
            return self._run_subagent(action.subagent)
        return ExecutionResult()

    async def _run_shell(self, sa, payload, blocking, timeout) -> ExecutionResult:
        try:
            proc = await asyncio.create_subprocess_shell(
                sa.command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            payload_json = _marshal_sorted(payload)
            stdout, stderr = await asyncio.wait_for(proc.communicate(payload_json), timeout=timeout)
        except asyncio.TimeoutError:
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                pass
            return ExecutionResult(err=TimeoutError(f"shell timeout after {timeout}s"))

        if blocking and proc.returncode == 2:
            reason = (stderr or stdout).decode("utf-8", errors="replace").rstrip("\n")
            return ExecutionResult(blocked=True, reason=reason)
        if proc.returncode == 0:
            return ExecutionResult()
        return ExecutionResult(
            err=RuntimeError(f"exit {proc.returncode}: {stderr.decode('utf-8', errors='replace')}")
        )

    async def _run_http(self, ha, payload, blocking) -> ExecutionResult:
        if self._http_client is None:
            import httpx

            self._http_client = httpx.AsyncClient()
        body = ha.body
        if body is None:
            body = json.dumps(payload, sort_keys=True)
        else:
            try:
                body = body.format_map(payload)
            except (KeyError, ValueError) as e:
                return ExecutionResult(err=e)

        try:
            import httpx

            resp = await self._http_client.request(
                ha.method, ha.url, content=body, headers=ha.headers, timeout=30.0
            )
        except httpx.HTTPError as e:
            return ExecutionResult(err=e)

        if 200 <= resp.status_code < 300:
            try:
                data = resp.json()
            except (json.JSONDecodeError, ValueError) as e:
                return ExecutionResult(err=e)
            if isinstance(data, dict) and data.get("decision") == "block":
                return ExecutionResult(blocked=True, reason=str(data.get("reason", "")))
        return ExecutionResult()

    def _run_subagent(self, sa) -> ExecutionResult:
        print(f"[hook subagent] not yet implemented, skipped: {sa.agent_name}", file=sys.stderr)
        return ExecutionResult()


def _marshal_sorted(p: Payload) -> bytes:
    """按 key 字典序序列化 payload。"""
    return json.dumps(p, sort_keys=True).encode("utf-8")
