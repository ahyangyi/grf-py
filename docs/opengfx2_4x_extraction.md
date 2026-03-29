# Extracting OpenGFX2 4x sprites

This repository ships a helper script that downloads the latest OpenGFX2 release and extracts every 4x zoom sprite using grf-py.

## Prerequisites

- Python 3.12
- Network access to download the OpenGFX2 release from GitHub

Install grf-py and its dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e .
```

## Run the extraction

```bash
python scripts/extract_opengfx2_4x.py --output downloads/opengfx2-4x
```

The script will:

1. Query the GitHub API for the latest OpenGFX2 release.
2. Download the `.grf` (or release archive) into `downloads/opengfx2`.
3. Extract every sprite with `zoom=ZOOM_4X` into `downloads/opengfx2-4x`.
4. Write a `manifest.csv` in the output directory describing each extracted sprite and its source metadata.

### Using a pre-downloaded GRF

If you already have the OpenGFX2 `.grf` file, pass it directly to skip the download step:

```bash
python scripts/extract_opengfx2_4x.py --grf /path/to/opengfx2.grf --output downloads/opengfx2-4x
```

### Palette selection

For paletted sprites, choose the palette to use:

```bash
python scripts/extract_opengfx2_4x.py --palette win --output downloads/opengfx2-4x
```
