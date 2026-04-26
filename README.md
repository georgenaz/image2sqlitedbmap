# image2sqlitedbmap

Convert [OziExplorer](https://www.oziexplorer.com/) `.map` files into [OsmAnd](https://osmand.net/)-compatible SQLiteDB offline map tiles.

## What it does

Given an OziExplorer `.map` file (which references an image and UTM ground-control points), the tool:

1. Parses the `.map` file — extracts image filename, UTM coordinates, GPS corners.
2. Validates the referenced image exists and matches the declared dimensions.
3. Computes optimal Web Mercator zoom level for pixel-perfect display (no upscaling).
4. Shows a summary and asks for confirmation before proceeding.
5. Warps the image from UTM to EPSG:3857 (Web Mercator) via GDAL.
6. Tiles the result with `gdal2tiles`, optimizes PNGs (palette + compression) via Pillow, packs with `mbutil`.
7. Produces an OsmAnd-ready `.sqlitedb` file with proper `tiles` and `info` tables.

## Requirements

- **Python 3.11**
- **GDAL** ≥ 3.8 (system library + Python bindings — versions must match)
- uv (or pip)

## Install

```bash
uv venv --python 3.11
uv pip install -e .
```

## Usage

```bash
uv run python main.py <map_file> [options]
```

**Arguments:**

| Argument | Description |
|---|---|
| `map_file` | Path to an OziExplorer `.map` file |
| `-o, --output` | Custom name for the output `.sqlitedb` file |
| `--work-dir` | Directory for temporary files (default: alongside the image) |
| `--keep-temp` | Keep intermediate files (VRT, TIF, tiles, MBTiles) |

**Example:**

```bash
uv run python main.py src_map_files/mmb26v.map
```

The tool prints map info, lets you change the output filename, and asks for confirmation before processing.

## Project structure

```
main.py              # CLI entry point, interactive pipeline
map_parser.py        # OziExplorer .map file parser
transformer.py       # GDAL warp: UTM → Web Mercator (EPSG:3857)
tiler.py             # gdal2tiles + PNG optimization + mbutil packing
database.py          # MBTiles → OsmAnd sqlitedb conversion
map_calc_tools.py    # Zoom level calculations, UTM ↔ WGS84
```

## License

See [LICENSE](LICENSE) file for details.
