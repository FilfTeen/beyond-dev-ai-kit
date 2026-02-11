# R17 Install Notes

## Install (Editable)

```bash
cd /Users/dwight/Downloads/【洪智科技】本地存档/beyond-dev-ai-kit
python3 -m pip install --upgrade pip setuptools wheel
python3 -m pip install -e .
```

## Smoke

```bash
mkdir -p /tmp/hz_proj
HONGZHI_PLUGIN_ENABLE=1 python3 -m hongzhi_ai_kit status --repo-root /tmp/hz_proj
HONGZHI_PLUGIN_ENABLE=1 hongzhi-ai-kit status --repo-root /tmp/hz_proj
```

## Expected

- No `No module named hongzhi_ai_kit` error.
- Module entry and console entry both work.
- Discover command emits:
  - `HONGZHI_CAPS <abs_path>`
  - `hongzhi_ai_kit_summary ...` (v3 compatibility)
