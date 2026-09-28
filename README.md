# xeno FrontierHarness adapter

Harbor (Terminal-Bench) and Pier (DeepSWE) adapters for [`@visual-z/xeno`](https://www.npmjs.com/package/@visual-z/xeno).

- `install-xeno.sh` — run by `provision-golden-checkpoint.sh --install-script`; stages Bun and xeno on the host.
- Harbor: `PYTHONPATH=/work/harness harbor run ... -a xeno_fh.harbor_agent:Xeno -m kimi-coding/kimi-k3`
- Pier: `PYTHONPATH=/work/harness pier run ... --agent-import-path xeno_fh.pier_agent:Xeno --model kimi-coding/kimi-k3`

xeno state goes to `/logs/agent/xeno-state` and its event stream to `/logs/agent/xeno.jsonl`; nothing is written into the task workspace.
