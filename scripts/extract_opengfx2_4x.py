#!/usr/bin/env python

import argparse
import csv
import json
import shutil
import tarfile
import zipfile
from pathlib import Path
import urllib.request

from PIL import Image

from grf.colour import (
    PIL_PALETTE,
    PIL_PALETTE_WIN,
    PIL_PALETTE_DOS_TOYLAND,
    PIL_PALETTE_WIN_TOYLAND,
    PIL_PALETTE_TTO,
    PIL_PALETTE_TTO_MARS,
)
from grf.common import ZOOM_4X
from grf.decompile import ParsingContext, RealGraphicsSprite, decode_sprite, read


LATEST_RELEASE_URL = "https://api.github.com/repos/OpenTTD/OpenGFX2/releases/latest"


def fetch_latest_release(url=LATEST_RELEASE_URL):
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "grf-py-opengfx2-downloader",
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def choose_asset(assets):
    if not assets:
        raise RuntimeError("No release assets found for OpenGFX2.")
    asset_by_name = {asset.get("name", "").lower(): asset for asset in assets}
    for suffix in (".grf", ".tar.xz", ".tar.gz", ".zip"):
        for name, asset in asset_by_name.items():
            if name.endswith(suffix):
                return asset
    raise RuntimeError("No downloadable OpenGFX2 GRF or archive asset found in the latest release.")


def download_asset(asset, download_dir):
    download_dir.mkdir(parents=True, exist_ok=True)
    asset_name = asset.get("name")
    if not asset_name:
        raise RuntimeError("Release asset missing a name.")
    url = asset.get("browser_download_url")
    if not url:
        raise RuntimeError(f"Release asset {asset_name} missing download URL.")
    target = download_dir / asset_name
    if target.exists():
        return target
    with urllib.request.urlopen(url, timeout=120) as response, open(target, "wb") as handle:
        shutil.copyfileobj(response, handle)
    return target


def extract_grf(asset_path, work_dir):
    work_dir.mkdir(parents=True, exist_ok=True)
    lower_name = asset_path.name.lower()
    if lower_name.endswith(".grf"):
        return asset_path
    if lower_name.endswith((".tar.xz", ".tar.gz", ".tar")):
        with tarfile.open(asset_path) as archive:
            for member in archive.getmembers():
                if member.name.lower().endswith(".grf"):
                    target = work_dir / Path(member.name).name
                    with archive.extractfile(member) as src, open(target, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    return target
    if lower_name.endswith(".zip"):
        with zipfile.ZipFile(asset_path) as archive:
            for name in archive.namelist():
                if name.lower().endswith(".grf"):
                    target = work_dir / Path(name).name
                    with archive.open(name) as src, open(target, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    return target
    raise RuntimeError(f"No .grf file found in {asset_path}.")


def select_palette(name):
    return {
        "dos": PIL_PALETTE,
        "win": PIL_PALETTE_WIN,
        "dos-toyland": PIL_PALETTE_DOS_TOYLAND,
        "win-toyland": PIL_PALETTE_WIN_TOYLAND,
        "tto": PIL_PALETTE_TTO,
        "tto-mars": PIL_PALETTE_TTO_MARS,
    }[name]


def save_sprite_images(sprite, data, palette, output_dir, index):
    bpp = sprite.bpp
    mask = None
    if sprite.type & 0x04:
        mask = data[:, :, -1]
        bpp -= 1
    if bpp == 4:
        color_img = Image.fromarray(data[:, :, :bpp], mode="RGBA")
    elif bpp == 3:
        color_img = Image.fromarray(data[:, :, :bpp], mode="RGB")
    elif bpp == 2:
        color_img = Image.fromarray(data[:, :, :bpp], mode="LA")
    elif bpp == 1:
        color_img = Image.fromarray(data[:, :, 0], mode="P")
        color_img.putpalette(palette)
    else:
        raise RuntimeError(
            f"Unsupported sprite bpp {bpp} for sprite index {index} (id {sprite.id})."
        )

    image_name = f"sprite_{index:05d}_id{sprite.id}.png"
    image_path = output_dir / image_name
    color_img.save(image_path, "PNG")

    mask_path = None
    if mask is not None:
        mask_img = Image.fromarray(mask, mode="P")
        mask_img.putpalette(palette)
        mask_name = f"sprite_{index:05d}_id{sprite.id}_mask.png"
        mask_path = output_dir / mask_name
        mask_img.save(mask_path, "PNG")

    return image_path, mask_path


def extract_4x_sprites(grf_path, output_dir, palette):
    if output_dir.exists():
        raise RuntimeError(
            f"Output directory already exists: {output_dir}. Remove it or choose a different --output path."
        )
    output_dir.mkdir(parents=True)
    manifest_path = output_dir / "manifest.csv"
    count = 0
    with open(grf_path, "rb") as handle, open(manifest_path, "w", newline="") as manifest:
        writer = csv.writer(manifest)
        writer.writerow(
            [
                "index",
                "sprite_id",
                "offset",
                "width",
                "height",
                "zoom",
                "type",
                "xofs",
                "yofs",
                "image",
                "mask",
            ]
        )
        context = ParsingContext()
        _, container, real_sprites, _ = read(handle, context)
        for sprite_list in real_sprites.values():
            for sprite in sprite_list:
                if not isinstance(sprite, RealGraphicsSprite):
                    continue
                if sprite.zoom != ZOOM_4X:
                    continue
                handle.seek(sprite.offset)
                data, _ = decode_sprite(handle, sprite, container)
                image_path, mask_path = save_sprite_images(sprite, data, palette, output_dir, count)
                writer.writerow(
                    [
                        count,
                        sprite.id,
                        sprite.offset,
                        sprite.width,
                        sprite.height,
                        sprite.zoom,
                        sprite.type,
                        sprite.xofs,
                        sprite.yofs,
                        image_path.name,
                        mask_path.name if mask_path else "",
                    ]
                )
                count += 1
    return count


def resolve_grf(args):
    if args.grf:
        return args.grf
    release = fetch_latest_release(args.release_url)
    asset = choose_asset(release.get("assets", []))
    downloaded = download_asset(asset, args.work_dir)
    return extract_grf(downloaded, args.work_dir)


def main():
    parser = argparse.ArgumentParser(
        description="Download the latest OpenGFX2 release and extract all 4x sprites with grf-py."
    )
    parser.add_argument(
        "--grf",
        type=Path,
        help="Path to an existing OpenGFX2 .grf file (skips download).",
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=Path("downloads/opengfx2"),
        help="Directory used to store the downloaded release assets.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("downloads/opengfx2-4x"),
        help="Output directory for extracted 4x sprites.",
    )
    parser.add_argument(
        "--palette",
        choices=("dos", "win", "dos-toyland", "win-toyland", "tto", "tto-mars"),
        default="dos",
        help="Palette for paletted sprites.",
    )
    parser.add_argument(
        "--release-url",
        default=LATEST_RELEASE_URL,
        help="Override the GitHub API URL used to fetch the latest OpenGFX2 release.",
    )
    args = parser.parse_args()
    palette = select_palette(args.palette)

    grf_path = resolve_grf(args)
    if not grf_path.exists():
        raise RuntimeError(f"OpenGFX2 GRF not found at {grf_path}")

    extracted = extract_4x_sprites(grf_path, args.output, palette)
    print(f"Extracted {extracted} 4x sprites to {args.output}.")


if __name__ == "__main__":
    main()
