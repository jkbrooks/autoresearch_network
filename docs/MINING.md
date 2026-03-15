# MINING.md

This guide takes a new miner from zero to a running AutoResearch miner on testnet.

## Requirements

- Ubuntu 22.04+ recommended
- NVIDIA GPU with at least 8GB VRAM
- Python 3.10+
- `uv`
- roughly 10GB free disk
- stable internet connection

## Install

```bash
git clone https://github.com/jkbrooks/autoresearch_network.git
cd autoresearch_network
python -m pip install -e .
uv sync --python 3.11
```

- `git clone` downloads the repository.
- `python -m pip install -e .` installs the package in editable mode.
- `uv sync` installs the locked Python dependencies.

## One-Time Data Setup

```bash
uv run prepare.py
```

This downloads the training data, trains the tokenizer, and caches assets in `~/.cache/autoresearch/`. It is only needed once per machine.

## Create Wallet

```bash
btcli wallet new_coldkey --wallet.name my-miner
btcli wallet new_hotkey --wallet.name my-miner --wallet.hotkey default
```

- The coldkey is your long-lived identity and should be backed up immediately.
- The hotkey is the operational key the miner process uses.
- Wallet files are stored under `~/.bittensor/wallets/`.

## Get Test TAO

- Join the Bittensor Discord: https://discord.gg/bittensor
- Ask in the faucet channel for test TAO
- Budget about 100 test TAO for registration and experimentation

## Register on Testnet

```bash
btcli subnet register --netuid 193 --network test \
  --wallet.name my-miner --wallet.hotkey default
```

## Configure LLM Mutations (Optional)

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

or

```bash
export OPENAI_API_KEY="sk-..."
```

Without an API key the miner uses the built-in structured mutation strategy.

### API cost budgeting

| Provider | Cost per experiment | Cost per hour | Cost per day |
| --- | --- | --- | --- |
| Anthropic Claude Opus | ~$0.06 | ~$0.72 | ~$17 |
| OpenAI GPT-4o | ~$0.02 | ~$0.24 | ~$6 |
| Local / compatible endpoint | $0 | $0 | $0 |

You can use a compatible local endpoint with:

```bash
python neurons/miner.py \
  --mutation-provider openai-compatible \
  --mutation-base-url http://localhost:8000
```

## Run the Miner

With structured mutations:

```bash
python neurons/miner.py \
  --netuid 193 \
  --network test \
  --wallet.name my-miner \
  --wallet.hotkey default \
  --logging.debug
```

With an LLM provider:

```bash
python neurons/miner.py \
  --netuid 193 \
  --network test \
  --wallet.name my-miner \
  --wallet.hotkey default \
  --mutation-provider anthropic \
  --logging.debug
```

Run under `tmux` or `screen` for persistence.

## Verify You Are Earning

```bash
btcli wallet overview --wallet.name my-miner --network test
```

Look for:
- a non-zero `EMISSION`
- non-zero `INCENTIVE`
- a populated `RANK`

## Troubleshooting

| Problem | Solution |
| --- | --- |
| No CUDA GPU detected | Install NVIDIA drivers and verify with `nvidia-smi`. |
| `uv` not found | Install with `curl -LsSf https://astral.sh/uv/install.sh \| sh`. |
| Data cache missing | Run `uv run autoresearch/data/prepare.py`. |
| OOM during training | Lower-memory mutation variants should cycle automatically; verify the GPU meets the minimum requirement. |
| Zero emissions after a long wait | Check miner logs, wallet registration, and validator availability on the subnet. |

## Modal Hybrid Path

Pure Modal ingress is not a reliable long-lived Bittensor axon strategy. Modal can expose the
miner process over raw TCP, but Bittensor validators still dial the numeric `external_ip` and
`external_port` advertised on-chain. The documented Modal tunnel endpoint is a relay host and
random port, not a stable public IPv4 reserved for the miner.

If you still want Modal for GPU execution, put a small stable-IP VM in front of it.

### Preferred Modal hybrid

Deploy the miner as a persistent Modal HTTP endpoint:

```bash
AUTORESEARCH_PUBLIC_IP=<VM_PUBLIC_IPV4> \
AUTORESEARCH_PUBLIC_PORT=8091 \
modal deploy scripts/modal_miner_193_http.py
```

The deploy output will include the stable `modal.run` URL for the endpoint. Reverse-proxy the VM's
public `8091` to that Modal URL. A minimal nginx shape is:

```nginx
server {
    listen 8091;
    server_name _;

    location / {
        proxy_pass https://YOUR_WORKSPACE--autoresearch-miner-193.modal.run;
        proxy_http_version 1.1;
        proxy_ssl_server_name on;
        proxy_set_header Host YOUR_WORKSPACE--autoresearch-miner-193.modal.run;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto http;
        proxy_request_buffering off;
        proxy_buffering off;
        proxy_read_timeout 15s;
        proxy_send_timeout 15s;
    }
}
```

Then advertise only the VM endpoint:

```bash
btcli axon set --netuid 193 --ip <VM_PUBLIC_IPV4> --port 8091 --ip-type 4 --network test
```

### Current sandbox bridge

The repository still includes the older raw-tunnel bridge for short-lived debugging. Use it only if
you specifically want the existing sandbox flow:

1. Launch the Modal miner with the VM's public IPv4:

```bash
python scripts/modal_miner_193.py launch \
  --public-ip <VM_PUBLIC_IPV4> \
  --public-port 8091
```

2. On the VM, forward the stable public port to the Modal tunnel target printed by the launcher:

```bash
socat TCP-LISTEN:8091,reuseaddr,fork TCP:<MODAL_TUNNEL_HOST>:<MODAL_TUNNEL_PORT>
```

3. Advertise only the stable VM endpoint to Bittensor:

```bash
btcli axon set --netuid 193 --ip <VM_PUBLIC_IPV4> --port 8091 --ip-type 4 --network test
```

This is still a workaround. For long-lived operation, the preferred production shape is a normal
GPU VM with a stable public IPv4, or a stable-IP front end that owns the public axon surface and
uses Modal only for backend compute.

## Validation Status

This walkthrough was smoke-tested on 2026-03-14 against testnet subnet `193` using a Modal L4 GPU
sandbox. The miner process booted and served locally inside Modal, but the fully public
validator-to-miner response path did not complete through Modal's direct external routing. For
long-lived operation, prefer a dedicated GPU host or the stable-IP front-end pattern above.
