# Evaluation: Current-Workspace Ticket Audit, Hardcoded/Demo Sweep, and Karpathy/Bittensor Parity

Date: 2026-03-15 16:35:00 PDT  
Repository: `jkbrooks/autoresearch_network`  
Workspace: `/Users/m/Desktop/autoresearchnetwork`  
Branch: `mcp97/live-proof-ux`  
Ticket source of truth: GitHub repo issues [#1](https://github.com/jkbrooks/autoresearch_network/issues/1) through [#27](https://github.com/jkbrooks/autoresearch_network/issues/27)

GitHub Project board columns were not used in this audit because the active `gh` token does not have `read:project` scope. Ticket status and acceptance criteria were derived from issue bodies instead.

## Executive Summary

- Ticket results:
  - `19` tickets are `Met`
  - `8` tickets are `Partially Met`
  - `0` tickets are `Not Met`
  - `0` tickets are `Unverifiable (external)`
- The repo is no longer just a protocol-only stub. It contains real miner and validator scaffolding, a live signed relay probe, a runnable experiment harness, guard logic, state persistence, and ticket-shaped docs and tests.
- Under the strict “Bittensor distributed AutoResearch by Andrej Karpathy” bar, the workspace is **not implemented** as a full Karpathy-distributed system. The best classification is **Partially implemented / scaffolded**:
  - the repo vendors the real `prepare.py` and `program.md` flow,
  - the miner can execute arbitrary `train.py` source through the experiment runner,
  - but the bundled default `train.py` and the live relay probe baseline are simplified surrogates rather than the real Karpathy training program.
- The highest-signal repo-local problems are tooling and operator-shape mismatches:
  - `ruff check .` currently fails because the persisted runtime artifact [`best_train.py`](/Users/m/Desktop/autoresearchnetwork/.validator-state-live/best_train.py:1) lives under a repo path that is linted as source.
  - `mypy autoresearch neurons` currently fails in demo/showcase surfaces, not in the core protocol or neuron logic.
  - `pytest tests/test_protocol.py -q` and `pytest tests/test_integration.py -q` both run their tests successfully but still exit `1` because the global 100% coverage gate applies to unrelated protocol/demo branches.
  - [`VALIDATING.md`](/Users/m/Desktop/autoresearchnetwork/docs/VALIDATING.md:58) instructs operators to keep the validator online continuously, but [`neurons/validator.py`](/Users/m/Desktop/autoresearchnetwork/neurons/validator.py:264) does not implement an explicit steady-state tempo loop in user code; only `--run-once` invokes `forward()`.
- Live-network evidence is stronger than the older March 14 docs alone:
  - `python -m autoresearch network-check --json --timeout 30` succeeded with `axon_status=200`, `dendrite_status=200`, `target_uid=0`, `val_bpb=0.9979`, and `hardware_tier=large`.
  - That proves a live relay-backed miner can currently answer a signed Bittensor probe from this environment.
  - It does **not** prove real Karpathy experiment parity, because the probe injects a hardcoded synthetic baseline in [`live_relay_proof.py`](/Users/m/Desktop/autoresearchnetwork/autoresearch/live_relay_proof.py:29).

## Hardcoded / Demo-Only Findings

### Runtime-Blocking

1. **The default validator baseline is a toy `train.py`, not the Karpathy workload.**
   - The bundled training program is a 7-line math toy in [`autoresearch/data/train.py`](/Users/m/Desktop/autoresearchnetwork/autoresearch/data/train.py:1).
   - The validator’s global-best tracker loads that file as the default baseline in [`autoresearch/validator/best_tracker.py`](/Users/m/Desktop/autoresearchnetwork/autoresearch/validator/best_tracker.py:15) and seeds `self.train_py` from it in [`autoresearch/validator/best_tracker.py`](/Users/m/Desktop/autoresearchnetwork/autoresearch/validator/best_tracker.py:34).
   - The experiment runner faithfully executes whatever `train.py` it is given in [`autoresearch/experiment_runner.py`](/Users/m/Desktop/autoresearchnetwork/autoresearch/experiment_runner.py:210), so the default distributed path is only as real as the baseline source it propagates.
   - Impact: strict Karpathy parity fails even though the miner/validator plumbing exists.

2. **Repo tooling is polluted by persisted runtime state.**
   - `ruff check .` currently fails on [`/Users/m/Desktop/autoresearchnetwork/.validator-state-live/best_train.py`](/Users/m/Desktop/autoresearchnetwork/.validator-state-live/best_train.py:1), which is a saved runtime artifact rather than maintained source code.
   - The validator docs explicitly persist `best_train.py` under the configured state directory in [`docs/VALIDATING.md`](/Users/m/Desktop/autoresearchnetwork/docs/VALIDATING.md:105).
   - Impact: a successful live run can make repo quality checks fail without any source change.

3. **Demo/showcase code currently breaks main quality gates.**
   - `mypy autoresearch neurons` reports errors in [`autoresearch/demo_format.py`](/Users/m/Desktop/autoresearchnetwork/autoresearch/demo_format.py:69), [`autoresearch/validator_round_showcase.py`](/Users/m/Desktop/autoresearchnetwork/autoresearch/validator_round_showcase.py:158), and [`autoresearch/live_relay_proof.py`](/Users/m/Desktop/autoresearchnetwork/autoresearch/live_relay_proof.py:120).
   - `pytest -q` fails only on coverage because [`autoresearch.protocol`](/Users/m/Desktop/autoresearchnetwork/autoresearch/protocol.py:341) now includes an uncovered `validator-showcase` CLI branch at [`autoresearch/protocol.py:347`](/Users/m/Desktop/autoresearchnetwork/autoresearch/protocol.py:347).
   - Impact: demo surfaces, not core miner/validator code, are currently what keep the repo from a green typed-and-gated state.

4. **Validator operator expectations and actual lifecycle are mismatched.**
   - [`docs/VALIDATING.md`](/Users/m/Desktop/autoresearchnetwork/docs/VALIDATING.md:84) tells operators to keep the validator running under `tmux` or `systemd`.
   - In the entrypoint, only `--run-once` actually invokes `validator.forward()` in [`neurons/validator.py`](/Users/m/Desktop/autoresearchnetwork/neurons/validator.py:333); otherwise the script initializes, saves state, and returns in [`neurons/validator.py`](/Users/m/Desktop/autoresearchnetwork/neurons/validator.py:358).
   - Impact: Epic 4 operator claims are ahead of the steady-state runtime lifecycle implemented in user code.

### Misleading-but-Nonblocking

1. **The README still describes the repo as protocol-foundation scaffolding.**
   - [`README.md`](/Users/m/Desktop/autoresearchnetwork/README.md:3) still says the project ships “minimal neuron scaffolding.”
   - [`README.md`](/Users/m/Desktop/autoresearchnetwork/README.md:5) still says the pass “intentionally stops at the protocol foundation.”
   - Impact: the docs understate the actual miner/validator and live-probe functionality now present in the repo.

2. **The live relay proof is a connectivity probe with hardcoded defaults and a canned baseline.**
   - [`autoresearch/live_relay_proof.py`](/Users/m/Desktop/autoresearchnetwork/autoresearch/live_relay_proof.py:21) hardcodes `netuid=193`, `wallet_name=my-miner`, `wallet_hotkey=default`, and `target_hotkey=default`.
   - The probe injects a synthetic `PLAUSIBLE_BASELINE` in [`autoresearch/live_relay_proof.py`](/Users/m/Desktop/autoresearchnetwork/autoresearch/live_relay_proof.py:29) instead of the repo’s tracked baseline or Karpathy’s real `train.py`.
   - Impact: a successful live probe proves signed Bittensor reachability, not real distributed AutoResearch parity.

3. **The protocol demo and mock factory are intentionally synthetic.**
   - The mock baseline and modified source are generated in [`autoresearch/mock.py`](/Users/m/Desktop/autoresearchnetwork/autoresearch/mock.py:16) through [`autoresearch/mock.py`](/Users/m/Desktop/autoresearchnetwork/autoresearch/mock.py:124).
   - The protocol module exposes a preview-only score formula in [`autoresearch/protocol.py`](/Users/m/Desktop/autoresearchnetwork/autoresearch/protocol.py:141) and a self-contained demo entrypoint in [`autoresearch/protocol.py`](/Users/m/Desktop/autoresearchnetwork/autoresearch/protocol.py:202).
   - Impact: these are good demo/test tools, but they should not be mistaken for proof of real distributed training parity.

4. **Modal launchers still expose debug-only bypasses for smoke testing.**
   - [`scripts/modal_miner_193.py`](/Users/m/Desktop/autoresearchnetwork/scripts/modal_miner_193.py:138) includes `--debug-skip-health-check`, `--debug-allow-non-validator-queries`, and `--debug-min-validator-stake`.
   - The generated miner command maps those to `--skip-health-check` and blacklist bypass flags in [`scripts/modal_miner_193.py`](/Users/m/Desktop/autoresearchnetwork/scripts/modal_miner_193.py:381).
   - Impact: these flags are clearly debug-shaped, but they are still close enough to operator flows that they can confuse production readiness discussions.

### Expected Demo/Test Scaffolding

1. **Mock runtimes are intentionally built into the base neuron layers.**
   - The miner base uses `_MockAxon` in [`autoresearch/base/miner.py`](/Users/m/Desktop/autoresearchnetwork/autoresearch/base/miner.py:15).
   - The shared neuron base uses `_MockSubtensor` and a mock wallet path in [`autoresearch/base/neuron.py`](/Users/m/Desktop/autoresearchnetwork/autoresearch/base/neuron.py:17).
   - The validator base provides placeholder wallet/subtensor/metagraph/dendrite surfaces in [`autoresearch/base/validator.py`](/Users/m/Desktop/autoresearchnetwork/autoresearch/base/validator.py:17).

2. **The validator showcase is explicitly presentation-only.**
   - [`autoresearch/validator_round_showcase.py`](/Users/m/Desktop/autoresearchnetwork/autoresearch/validator_round_showcase.py:42) defines `ShowcaseMetagraph`, `ShowcaseSubtensor`, and `ShowcaseDendrite`.
   - Its response payload is a hand-built synthetic submission in [`autoresearch/validator_round_showcase.py`](/Users/m/Desktop/autoresearchnetwork/autoresearch/validator_round_showcase.py:92).

3. **The validator docs explicitly describe a local mock path for regression testing.**
   - [`docs/VALIDATING.md`](/Users/m/Desktop/autoresearchnetwork/docs/VALIDATING.md:152) documents `--subtensor._mock`, `--skip-health-check`, and `--run-once` as a deterministic local path.

## Ticket Audit Matrix

| Issue | Verdict | Blocker | Acceptance Summary | Evidence |
| --- | --- | --- | --- | --- |
| [#1](https://github.com/jkbrooks/autoresearch_network/issues/1) Epic 1: Repository & Project Setup | Partially Met | GitHub/main | Editable install and local pytest work, but hosted CI on `main` is currently red. | [ci.yml:24](/Users/m/Desktop/autoresearchnetwork/.github/workflows/ci.yml:24)<br>`python -m pip install -e .` passed on 2026-03-15<br>`gh run list -R jkbrooks/autoresearch_network -L 10` showed the last 10 `main` push runs failed, latest [23121136189](https://github.com/jkbrooks/autoresearch_network/actions/runs/23121136189) |
| [#2](https://github.com/jkbrooks/autoresearch_network/issues/2) Epic 2: Protocol Definition | Partially Met | tooling | The no-GPU demo path is clean and fast, but the exact `pytest tests/test_protocol.py` command exits `1` because the global 100% coverage gate now misses the `validator-showcase` branch. | [protocol.py:341](/Users/m/Desktop/autoresearchnetwork/autoresearch/protocol.py:341)<br>`python -m autoresearch.protocol demo` exited `0` in `0.976s`<br>`UV_CACHE_DIR=.uv-cache uv run pytest tests/test_protocol.py -q` -> `48 passed`, exit `1`, coverage `99.02%` |
| [#3](https://github.com/jkbrooks/autoresearch_network/issues/3) E2-1: Define `ExperimentSubmission` synapse class | Met | — | Synapse contract, optional miner fields, and `deserialize()` are implemented and tested. | [protocol.py:63](/Users/m/Desktop/autoresearchnetwork/autoresearch/protocol.py:63)<br>[tests/test_protocol.py:65](/Users/m/Desktop/autoresearchnetwork/tests/test_protocol.py:65) |
| [#4](https://github.com/jkbrooks/autoresearch_network/issues/4) E2-2: Define `HardwareTier` enum and scoring constants | Met | — | Hardware tiers, plausibility ranges, and scoring constants are centralized and exercised by tests. | [constants.py:9](/Users/m/Desktop/autoresearchnetwork/autoresearch/constants.py:9)<br>[tests/test_constants.py:18](/Users/m/Desktop/autoresearchnetwork/tests/test_constants.py:18) |
| [#5](https://github.com/jkbrooks/autoresearch_network/issues/5) E2-3: Implement protocol-level input validation | Met | — | `validate()` exists, enforces the ordered rule set, and is well covered. | [protocol.py:89](/Users/m/Desktop/autoresearchnetwork/autoresearch/protocol.py:89)<br>[tests/test_protocol.py:111](/Users/m/Desktop/autoresearchnetwork/tests/test_protocol.py:111) |
| [#6](https://github.com/jkbrooks/autoresearch_network/issues/6) E2-4: Build mock submission factory for testing | Met | — | The deterministic mock factory generates valid and invalid ticket-shaped submissions with no external dependencies. | [mock.py:57](/Users/m/Desktop/autoresearchnetwork/autoresearch/mock.py:57)<br>[tests/test_protocol.py:252](/Users/m/Desktop/autoresearchnetwork/tests/test_protocol.py:252) |
| [#7](https://github.com/jkbrooks/autoresearch_network/issues/7) E2-5: Build CLI demo command | Met | — | The demo command works, runs under 5 seconds, and uses only local synthetic data. | [protocol.py:202](/Users/m/Desktop/autoresearchnetwork/autoresearch/protocol.py:202)<br>[__main__.py:30](/Users/m/Desktop/autoresearchnetwork/autoresearch/__main__.py:30)<br>`python -m autoresearch.protocol demo` exited `0` in `0.976s` |
| [#8](https://github.com/jkbrooks/autoresearch_network/issues/8) Epic 3: Miner Implementation | Partially Met | live-network | Core miner code exists and a live signed probe succeeds, but the “zero to earning in 30 minutes” operator claim is not fully demonstrated by the current guide. | [neurons/miner.py:21](/Users/m/Desktop/autoresearchnetwork/neurons/miner.py:21)<br>[docs/MINING.md:89](/Users/m/Desktop/autoresearchnetwork/docs/MINING.md:89)<br>[docs/MINING.md:214](/Users/m/Desktop/autoresearchnetwork/docs/MINING.md:214)<br>`network-check --json` -> `axon_status=200`, `dendrite_status=200` |
| [#9](https://github.com/jkbrooks/autoresearch_network/issues/9) E3-1: Scaffold miner neuron and Bittensor connection layer | Met | — | The miner serves an axon, logs startup identity, returns synapses, and is visible to the current live probe target metagraph. | [base/miner.py:40](/Users/m/Desktop/autoresearchnetwork/autoresearch/base/miner.py:40)<br>[neurons/miner.py:46](/Users/m/Desktop/autoresearchnetwork/neurons/miner.py:46)<br>`network-check --json` -> `target_uid=0`, `target_endpoint=44.209.235.221:8091` |
| [#10](https://github.com/jkbrooks/autoresearch_network/issues/10) E3-2: Implement experiment execution environment | Met | — | The experiment runner handles setup, success, crash, timeout, cleanup, and metric parsing. | [experiment_runner.py:172](/Users/m/Desktop/autoresearchnetwork/autoresearch/experiment_runner.py:172)<br>[tests/test_experiment_runner.py:131](/Users/m/Desktop/autoresearchnetwork/tests/test_experiment_runner.py:131) |
| [#11](https://github.com/jkbrooks/autoresearch_network/issues/11) E3-3: Implement hardware tier detection | Met | — | VRAM boundaries, override precedence, throughput consistency, and CPU fallback are implemented and tested. | [hardware.py:32](/Users/m/Desktop/autoresearchnetwork/autoresearch/hardware.py:32)<br>[tests/test_hardware.py:26](/Users/m/Desktop/autoresearchnetwork/tests/test_hardware.py:26) |
| [#12](https://github.com/jkbrooks/autoresearch_network/issues/12) E3-4: Implement structured mutation strategy | Met | — | Deterministic structured mutations, exhaustion behavior, and AST validity checks exist. | [mutations.py:71](/Users/m/Desktop/autoresearchnetwork/autoresearch/mutations.py:71)<br>[tests/test_mutations.py:1](/Users/m/Desktop/autoresearchnetwork/tests/test_mutations.py:1) |
| [#13](https://github.com/jkbrooks/autoresearch_network/issues/13) E3-5: Implement `forward()` full experiment cycle | Met | — | Miner `forward()` covers lock handling, baseline resets, experiment execution, and synapse field mapping. | [neurons/miner.py:77](/Users/m/Desktop/autoresearchnetwork/neurons/miner.py:77)<br>[tests/test_miner.py:41](/Users/m/Desktop/autoresearchnetwork/tests/test_miner.py:41) |
| [#14](https://github.com/jkbrooks/autoresearch_network/issues/14) E3-6: Implement LLM-driven mutation via AutoResearch agent protocol | Met | — | LLM mutation is env-driven, provider-selectable, and falls back safely on API or parse failure. | [mutations.py:257](/Users/m/Desktop/autoresearchnetwork/autoresearch/mutations.py:257)<br>[neurons/miner.py:50](/Users/m/Desktop/autoresearchnetwork/neurons/miner.py:50) |
| [#15](https://github.com/jkbrooks/autoresearch_network/issues/15) E3-7: Implement request blacklisting and stake-weighted priority | Met | — | Blacklist and priority paths handle hotkey registration, validator permit, stake floors, and dev bypasses. | [neurons/miner.py:127](/Users/m/Desktop/autoresearchnetwork/neurons/miner.py:127)<br>[tests/test_miner.py:152](/Users/m/Desktop/autoresearchnetwork/tests/test_miner.py:152) |
| [#16](https://github.com/jkbrooks/autoresearch_network/issues/16) E3-8: Miner startup health check | Met | — | GPU, `uv`, cache, wallet, and Bittensor checks are implemented and covered by targeted tests. | [health.py:49](/Users/m/Desktop/autoresearchnetwork/autoresearch/health.py:49)<br>[tests/test_health.py:9](/Users/m/Desktop/autoresearchnetwork/tests/test_health.py:9) |
| [#17](https://github.com/jkbrooks/autoresearch_network/issues/17) E3-9: Write `MINING.md` onboarding guide | Partially Met | live-network | The guide is detailed and rendered, but the repo’s own validation notes still stop short of proving a frictionless “zero to earning” path. | [docs/MINING.md:14](/Users/m/Desktop/autoresearchnetwork/docs/MINING.md:14)<br>[docs/MINING.md:214](/Users/m/Desktop/autoresearchnetwork/docs/MINING.md:214) |
| [#18](https://github.com/jkbrooks/autoresearch_network/issues/18) E3-10: Full validator-side replay verification | Partially Met | repo-local | Replay sampling, comparison, and stats exist, but only in shadow telemetry mode; score multipliers and elevated sampling are not wired into rewards. | [validator/replay.py:44](/Users/m/Desktop/autoresearchnetwork/autoresearch/validator/replay.py:44)<br>[validator/forward.py:91](/Users/m/Desktop/autoresearchnetwork/autoresearch/validator/forward.py:91)<br>[tests/test_validator_replay.py:16](/Users/m/Desktop/autoresearchnetwork/tests/test_validator_replay.py:16) |
| [#19](https://github.com/jkbrooks/autoresearch_network/issues/19) Epic 4: Validator & Scoring Engine | Partially Met | repo-local, tooling | The scoring engine, tracker, guards, state, and live probe surfaces exist, but the plain validator entrypoint has no explicit steady-state tempo loop and the exact integration-test command exits `1` under the global coverage gate. | [neurons/validator.py:257](/Users/m/Desktop/autoresearchnetwork/neurons/validator.py:257)<br>[tests/test_integration.py:28](/Users/m/Desktop/autoresearchnetwork/tests/test_integration.py:28)<br>`UV_CACHE_DIR=.uv-cache uv run pytest tests/test_integration.py -q` -> `5 passed`, exit `1` |
| [#20](https://github.com/jkbrooks/autoresearch_network/issues/20) E4-1: Scaffold validator neuron and Bittensor connection layer | Partially Met | repo-local | Runtime objects, score state, and CLI flags exist, but the user-code entrypoint still lacks an explicit long-running validator lifecycle and only `--run-once` invokes `forward()`. | [base/validator.py:163](/Users/m/Desktop/autoresearchnetwork/autoresearch/base/validator.py:163)<br>[neurons/validator.py:264](/Users/m/Desktop/autoresearchnetwork/neurons/validator.py:264)<br>[tests/test_validator_scaffold.py:96](/Users/m/Desktop/autoresearchnetwork/tests/test_validator_scaffold.py:96) |
| [#21](https://github.com/jkbrooks/autoresearch_network/issues/21) E4-2: Implement global best tracker | Met | — | The tracker defaults to bundled baseline source, validates updates, and persists metadata plus `best_train.py`. | [best_tracker.py:23](/Users/m/Desktop/autoresearchnetwork/autoresearch/validator/best_tracker.py:23)<br>[tests/test_validator_best_tracker.py:1](/Users/m/Desktop/autoresearchnetwork/tests/test_validator_best_tracker.py:1) |
| [#22](https://github.com/jkbrooks/autoresearch_network/issues/22) E4-3: Implement Stage 1 scoring | Met | — | Stage 1 scoring zeros invalids, gives participation credit for non-improvements, and caps improvement reward. | [reward.py:12](/Users/m/Desktop/autoresearchnetwork/autoresearch/validator/reward.py:12)<br>[tests/test_validator_reward.py:1](/Users/m/Desktop/autoresearchnetwork/tests/test_validator_reward.py:1) |
| [#23](https://github.com/jkbrooks/autoresearch_network/issues/23) E4-4: Implement `forward()` full validation cycle | Met | — | `forward()` builds challenges, queries active miners, applies Stage 1 plus guards, updates tracker/EMA/stats, and sets weights. | [validator/forward.py:39](/Users/m/Desktop/autoresearchnetwork/autoresearch/validator/forward.py:39)<br>[tests/test_validator_forward.py:1](/Users/m/Desktop/autoresearchnetwork/tests/test_validator_forward.py:1) |
| [#24](https://github.com/jkbrooks/autoresearch_network/issues/24) E4-5: Implement anti-duplication and anti-gaming guards | Met | — | Exact duplicate, near-duplicate, throughput, and combined guard multipliers are implemented and tested. | [guards.py:26](/Users/m/Desktop/autoresearchnetwork/autoresearch/validator/guards.py:26)<br>[tests/test_validator_guards.py:1](/Users/m/Desktop/autoresearchnetwork/tests/test_validator_guards.py:1) |
| [#25](https://github.com/jkbrooks/autoresearch_network/issues/25) E4-6: Implement per-miner EMA score tracking and leaderboard stats | Met | — | EMA score persistence, hotkey resync behavior, miner stats, and leaderboard formatting are present. | [stats.py:10](/Users/m/Desktop/autoresearchnetwork/autoresearch/validator/stats.py:10)<br>[tests/test_validator_scaffold.py:48](/Users/m/Desktop/autoresearchnetwork/tests/test_validator_scaffold.py:48)<br>[tests/test_validator_stats.py:1](/Users/m/Desktop/autoresearchnetwork/tests/test_validator_stats.py:1) |
| [#26](https://github.com/jkbrooks/autoresearch_network/issues/26) E4-7: Implement validator state persistence and startup health check | Met | — | Validator state files, replay stats, health checks, and periodic save behavior are implemented and tested. | [neurons/validator.py:118](/Users/m/Desktop/autoresearchnetwork/neurons/validator.py:118)<br>[tests/test_validator_state.py:23](/Users/m/Desktop/autoresearchnetwork/tests/test_validator_state.py:23) |
| [#27](https://github.com/jkbrooks/autoresearch_network/issues/27) E4-8: Write `VALIDATING.md` guide and end-to-end integration test | Partially Met | tooling, live-network | The guide and integration tests exist, but the doc still records one unresolved live checklist item and the exact `pytest tests/test_integration.py` command currently exits `1` because of the global coverage gate. | [docs/VALIDATING.md:198](/Users/m/Desktop/autoresearchnetwork/docs/VALIDATING.md:198)<br>[tests/test_integration.py:28](/Users/m/Desktop/autoresearchnetwork/tests/test_integration.py:28)<br>`UV_CACHE_DIR=.uv-cache uv run pytest tests/test_integration.py -q` -> `5 passed`, exit `1` |

## Karpathy/Bittensor Parity Verdict

**Verdict: `Partially implemented / scaffolded`**

### Experiment Parity

- **Not met.**
- The default validator baseline comes from the repo’s toy [`autoresearch/data/train.py`](/Users/m/Desktop/autoresearchnetwork/autoresearch/data/train.py:1), not the real Karpathy `train.py`.
- The live relay probe also injects a hardcoded synthetic training script in [`autoresearch/live_relay_proof.py`](/Users/m/Desktop/autoresearchnetwork/autoresearch/live_relay_proof.py:29).
- The miner mutation engine is structurally capable of mutating arbitrary `train.py` source in [`neurons/miner.py`](/Users/m/Desktop/autoresearchnetwork/neurons/miner.py:87) and [`autoresearch/mutations.py`](/Users/m/Desktop/autoresearchnetwork/autoresearch/mutations.py:71), but the default shipped challenge path is still surrogate.

### Data / Evaluation Parity

- **Partially met.**
- The repo vendors the real fixed-data/fixed-eval scaffolding in [`autoresearch/data/prepare.py`](/Users/m/Desktop/autoresearchnetwork/autoresearch/data/prepare.py:1) and the Karpathy-style operator prompt in [`autoresearch/data/program.md`](/Users/m/Desktop/autoresearchnetwork/autoresearch/data/program.md:1).
- The experiment runner uses those vendored assets when it creates isolated workdirs in [`autoresearch/experiment_runner.py`](/Users/m/Desktop/autoresearchnetwork/autoresearch/experiment_runner.py:182) through [`autoresearch/experiment_runner.py`](/Users/m/Desktop/autoresearchnetwork/autoresearch/experiment_runner.py:219).
- The missing piece is the bundled baseline `train.py`, which is not the real training program that those assets are meant to support.

### Distributed Protocol Parity

- **Partially met.**
- The core Bittensor request/response contract is real in [`autoresearch/protocol.py`](/Users/m/Desktop/autoresearchnetwork/autoresearch/protocol.py:63).
- The miner and validator both have real optional Bittensor runtime paths in [`autoresearch/base/neuron.py`](/Users/m/Desktop/autoresearchnetwork/autoresearch/base/neuron.py:51) and [`autoresearch/base/validator.py`](/Users/m/Desktop/autoresearchnetwork/autoresearch/base/validator.py:179).
- A live signed probe succeeded from this workspace:

```json
{
  "dendrite_status": 200,
  "axon_status": 200,
  "target_uid": 0,
  "target_endpoint": "44.209.235.221:8091",
  "val_bpb": 0.9979,
  "hardware_tier": "large"
}
```

- That confirms live relay-backed reachability, but because the probe challenge is synthetic, it is still not proof of true Karpathy-style distributed autoresearch.

### Operator Parity

- **Not met.**
- The miner guide is detailed, but its own validation note still stops short of a clean zero-to-earning proof in [`docs/MINING.md`](/Users/m/Desktop/autoresearchnetwork/docs/MINING.md:214).
- The validator guide claims persistent operation, but the current user-code entrypoint does not implement an explicit steady-state tempo loop in [`neurons/validator.py`](/Users/m/Desktop/autoresearchnetwork/neurons/validator.py:264).

## Verification Results

### Local Commands

```text
python -m pip install -e .
-> passed

python -m autoresearch.protocol demo
-> exit 0
-> elapsed 0.976s

UV_CACHE_DIR=.uv-cache uv run pytest -q --no-cov
-> 227 passed in 8.10s

UV_CACHE_DIR=.uv-cache uv run pytest -q
-> 227 passed
-> exit 1 because coverage gate failed
-> total coverage 99.02%
-> missing lines: autoresearch/protocol.py:348-350

UV_CACHE_DIR=.uv-cache uv run pytest tests/test_protocol.py -q
-> 48 passed
-> exit 1 because coverage gate failed
-> total coverage 99.02%

UV_CACHE_DIR=.uv-cache uv run pytest tests/test_integration.py -q
-> 5 passed
-> exit 1 because coverage gate failed
-> total coverage 54.90%

UV_CACHE_DIR=.uv-cache uv run ruff check .
-> exit 1
-> .validator-state-live/best_train.py import order failure

UV_CACHE_DIR=.uv-cache uv run mypy autoresearch neurons
-> exit 1
-> 8 errors in autoresearch/demo_format.py, autoresearch/validator_round_showcase.py, and autoresearch/live_relay_proof.py
```

### Live-Network Probe

```text
UV_CACHE_DIR=.uv-cache uv run python -m autoresearch network-check --json --timeout 30
-> exit 0
-> dendrite_status=200
-> axon_status=200
-> target_uid=0
-> target_endpoint=44.209.235.221:8091
-> val_bpb=0.9979
-> hardware_tier=large
```

### GitHub-Hosted CI

```text
gh run list -R jkbrooks/autoresearch_network -L 10
-> last 10 push runs on main all failed
-> latest main push failures include:
   - 23121136189
   - 23121119871
   - 23118706994
   - 23117770502
```

## Open External Gaps

- GitHub Project board column state could not be audited because the active token lacks `read:project`.
- The operator docs were not re-walked by a brand-new human operator during this audit, so “can follow without questions” claims remain weaker than code/test claims.
- The live signed relay probe succeeded, but it only exercised a synthetic challenge payload, not the real Karpathy `train.py`.
- The validator’s exact steady-state live lifecycle remains operationally ambiguous from user code:
  - the entrypoint exposes `--run-once`,
  - the docs describe a persistent validator,
  - but no explicit perpetual tempo loop is implemented in the entrypoint itself.
- Main-branch CI is still externally red, which blocks a clean “fully merged and green on main” conclusion for Epic 1.
