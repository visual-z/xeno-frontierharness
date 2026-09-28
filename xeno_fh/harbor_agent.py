"""Harbor (Terminal-Bench) adapter: `-a xeno_fh.harbor_agent:Xeno`."""
from __future__ import annotations

import tempfile
from pathlib import Path

from harbor.agents.installed.base import BaseInstalledAgent, with_prompt_template
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext

from xeno_fh import common


class Xeno(BaseInstalledAgent):
    def __init__(self, *args, max_turns: int = 300, time_budget: int | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self._max_turns = int(max_turns)
        self._time_budget = int(time_budget) if time_budget else None

    @staticmethod
    def name() -> str:
        return "xeno"

    def get_version_command(self) -> str | None:
        return f"cat {common.REMOTE}/VERSION"

    def parse_version(self, stdout: str) -> str:
        return stdout.strip().splitlines()[-1].strip()

    async def install(self, environment: BaseEnvironment) -> None:
        await self.exec_as_root(environment, command=f"mkdir -p {common.REMOTE} && chmod 755 /installed-agent {common.REMOTE}")
        await environment.upload_dir(common.STAGE, common.REMOTE)
        await self.exec_as_root(environment, command=f"chmod -R a+rX {common.REMOTE}")
        await self.exec_as_agent(environment, command=common.install_command())

    @with_prompt_template
    async def run(self, instruction: str, environment: BaseEnvironment, context: AgentContext) -> None:
        route, spec = common.resolve(self.model_name)
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "models.json"
            config.write_text(common.models_json(spec))
            await self.exec_as_agent(environment, command=f"mkdir -p {common.CONFIG_DIR}")
            await environment.upload_file(config, f"{common.CONFIG_DIR}/models.json")
        # On Runta the egress proxy writes the real Authorization header for
        # the provider host; the variable only has to be non-empty.
        key = self._get_env(route["key_env"]) or common.SECRET_STUB
        await self.exec_as_agent(
            environment,
            command=common.run_command(instruction, spec["id"], self._max_turns, self._time_budget),
            env={route["key_env"]: key},
        )

    def populate_context_post_run(self, context: AgentContext) -> None:
        prompt, cached, _written, output = common.usage_totals(self.logs_dir / common.LOG_NAME)
        context.n_input_tokens = prompt
        context.n_cache_tokens = cached
        context.n_output_tokens = output
        context.cost_usd = None
