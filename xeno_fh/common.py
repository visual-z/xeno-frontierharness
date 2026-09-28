"""Pieces shared by the Harbor and Pier adapters.

xeno is a Bun program. Trial containers restrict egress, so nothing is
downloaded during a trial: install-xeno.sh stages Bun (glibc and musl builds)
and the published package with its dependencies under STAGE on the Runta
host before the golden checkpoint, and the adapter uploads that directory into
the task container.

Every xeno write goes under /logs/agent (--state-dir), never the task
workspace, so model.patch and verifiers see only the agent's edits.
"""
from __future__ import annotations

import json
import shlex
from pathlib import Path

STAGE = Path("/work/xeno-stage")
REMOTE = "/installed-agent/xeno"
LOG_NAME = "xeno.jsonl"
STATE_DIR = "/logs/agent/xeno-state"
CONFIG_DIR = "/logs/agent/xeno-config"

# FrontierHarness model routes -> the xeno catalog entry that serves them.
# The benchmark model is Kimi K3; `kimi-coding` is Kimi's coding endpoint,
# whose wire id for K3 is `k3`. The route keeps `kimi-k3` so the eval's
# model check and pricing table recognise it.
PROVIDERS = {
    "kimi-coding": {
        "host": "api.kimi.com",
        "key_env": "KIMI_CODING_API_KEY",
        "models": {
            "kimi-k3": {
                "id": "k3", "name": "Kimi K3 (Kimi Coding)", "api": "openai-completions", "provider": "kimi-coding",
                "baseUrl": "https://api.kimi.com/coding/v1", "reasoning": True,
                "contextWindow": 1048576, "maxTokens": 131072,
                "compat": {"supportsDeveloperRole": False, "maxTokensField": "max_completion_tokens",
                           "supportsReasoningEffort": True, "supportsUsageInStreaming": True,
                           "requiresReasoningContentOnAssistantMessages": False, "thinkingFormat": "openai"},
                "thinkingLevelMap": {"low": "low", "medium": "high", "high": "high", "xhigh": "max", "max": "max"},
            },
        },
    },
}


def resolve(model_name: str | None) -> tuple[dict, dict]:
    if not model_name or "/" not in model_name:
        raise ValueError("model must be provider/model, e.g. kimi-coding/kimi-k3")
    provider, model = model_name.split("/", 1)
    route = PROVIDERS.get(provider)
    if route is None or model not in route["models"]:
        raise ValueError(f"no xeno route for {model_name}; known: " +
                         ", ".join(f"{p}/{m}" for p, r in PROVIDERS.items() for m in r["models"]))
    return route, route["models"][model]


def models_json(spec: dict) -> str:
    return json.dumps({"models": [spec]}, indent=2) + "\n"


def install_command() -> str:
    # Pick the Bun build this container's libc can run.
    return (
        "set -eu; "
        f"if ldd --version 2>&1 | grep -qi musl; then cp {REMOTE}/bun-musl {REMOTE}/bun; "
        f"else cp {REMOTE}/bun-glibc {REMOTE}/bun; fi; "
        f"chmod +x {REMOTE}/bun; {REMOTE}/bun --version"
    )


def run_command(instruction: str, wire_model: str, max_turns: int, time_budget: int | None) -> str:
    cli = f"{REMOTE}/node_modules/@visual-z/xeno/src/apps/cli.ts"
    flags = [
        "-w", '"$PWD"', "-m", shlex.quote(wire_model), "--mode", "json",
        "--allow-tools", "bash,exec_command", "--path-root", "/",
        "--state-dir", STATE_DIR, "--max-turns", str(max_turns),
    ]
    if time_budget:
        flags += ["--time-budget", str(time_budget)]
    return (
        f"mkdir -p {STATE_DIR} && "
        f"XENO_CONFIG_DIR={CONFIG_DIR} {REMOTE}/bun {cli} {' '.join(flags)} -p {shlex.quote(instruction)} "
        f"</dev/null 2>/logs/agent/xeno.stderr | tee /logs/agent/{LOG_NAME}"
    )


def usage_totals(log: Path) -> tuple[int, int, int, int]:
    """(prompt incl. cache reads, cache reads, cache writes, output) from xeno --mode json."""
    prompt = cached = written = output = 0
    if not log.exists():
        return 0, 0, 0, 0
    for line in log.read_text(errors="replace").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict) or event.get("type") != "usage":
            continue
        u = event.get("usage") or {}
        read = int(u.get("cache_read_input_tokens") or 0)
        write = int(u.get("cache_creation_input_tokens") or 0)
        prompt += int(u.get("input_tokens") or 0) + read + write
        cached += read
        written += write
        output += int(u.get("output_tokens") or 0)
    return prompt, cached, written, output
