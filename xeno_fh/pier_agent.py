"""Pier (DeepSWE) adapter: `--agent-import-path xeno_fh.pier_agent:Xeno`."""
from __future__ import annotations

import tempfile
from pathlib import Path

from pier.agents.installed.base import BaseInstalledAgent, with_prompt_template
from pier.environments.base import BaseEnvironment
from pier.models.agent.context import AgentContext
from pier.models.agent.install import AgentInstallSpec, InstallStep
from pier.models.agent.network import NetworkAllowlist

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

    def install_spec(self) -> AgentInstallSpec:
        # Pier's docker environment bakes these steps into the task image at
        # build time -- before any upload exists -- and then treats the agent
        # as preinstalled, skipping install(). So the build step only creates
        # the directory; the staged files are uploaded in setup() instead.
        return AgentInstallSpec(agent_name=self.name(), version=self._version,
                                steps=[InstallStep(user="root", run=f"mkdir -p {common.REMOTE}")])

    async def install(self, environment: BaseEnvironment) -> None:
        await self.exec_as_root(environment, command=f"mkdir -p {common.REMOTE} && chmod 755 /installed-agent {common.REMOTE}")
        await environment.upload_dir(common.STAGE, common.REMOTE)
        await self.exec_as_root(environment, command=f"chmod -R a+rX {common.REMOTE}")
        await self.exec_as_agent(environment, command=common.install_command())
        self._uploaded = True

    async def setup(self, environment: BaseEnvironment) -> None:
        self._uploaded = False
        await super().setup(environment)
        # Runs whether or not Pier considered the agent preinstalled.
        if not self._uploaded:
            await self.install(environment)

    def network_allowlist(self) -> NetworkAllowlist:
        route, _ = common.resolve(self.model_name)
        return NetworkAllowlist(domains=[route["host"]])

    @with_prompt_template
    async def run(self, instruction: str, environment: BaseEnvironment, context: AgentContext) -> None:
        route, spec = common.resolve(self.model_name)
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "models.json"
            config.write_text(common.models_json(spec))
            await self.exec_as_agent(environment, command=f"mkdir -p {common.CONFIG_DIR}")
            await environment.upload_file(config, f"{common.CONFIG_DIR}/models.json")
        await common.upload_ca(environment)
        # On Runta the egress proxy writes the real Authorization header for
        # the provider host; the variable only has to be non-empty.
        key = self._get_env(route["key_env"]) or common.SECRET_STUB
        env = self.build_process_env()
        env[route["key_env"]] = key
        await self.exec_as_agent(
            environment,
            command=common.run_command(instruction, spec["id"], self._max_turns, self._time_budget),
            env=env,
        )

    def populate_context_post_run(self, context: AgentContext) -> None:
        prompt, cached, _written, output = common.usage_totals(self.logs_dir / common.LOG_NAME)
        context.n_input_tokens = prompt
        context.n_cache_tokens = cached
        context.n_output_tokens = output
        context.cost_usd = None
