# image2sqlitedbmap

[![GitHub](https://img.shields.io/badge/GitHub-repository-blue)](https://github.com/georgenaz/image2sqlitedbmap)

Convert [OziExplorer](https://www.oziexplorer.com/) `.map` files into [OsmAnd](https://osmand.net/)-compatible SQLiteDB or MBTiles offline map tiles.

## What it does

Given an OziExplorer `.map` file (which references an image and UTM ground-control points), the tool:

1. Parses the `.map` file — extracts image filename, UTM coordinates, GPS corners.
2. Validates the referenced image exists and matches the declared dimensions.
3. Computes optimal Web Mercator zoom level for pixel-perfect display (no upscaling).
4. Shows a summary and asks for confirmation before proceeding.
5. Warps the image from UTM to EPSG:3857 (Web Mercator) via GDAL.
6. Tiles the result with `gdal2tiles`, optimizes PNGs (palette + compression) via Pillow, packs with `mbutil`.
7. Produces an OsmAnd-ready `.sqlitedb` or standard `.mbtiles` file.

## Requirements

- **Python 3.11**
- **GDAL** ≥ 3.8 (system library + Python bindings — versions must match)
- uv (or pip)

## Install

```bash
uv sync
```

## Usage

```bash
uv run main.py <map_file> [options]
```

**Arguments:**

| Argument | Description |
|---|---|
| `map_file` | Path to an OziExplorer `.map` file |
| `-f, --format` | Output format: `sqlitedb` (default) or `mbtiles` |
| `-o, --output` | Output file name (without path). Extension is used to detect format if `--format` is not set |
| `-q, --quiet` | Quiet mode: no prompts, uses defaults (sqlitedb, auto-generated name) |
| `--work-dir` | Directory for temporary files (default: alongside the image) |
| `--keep-temp` | Keep intermediate files (VRT, TIF, tiles) |

**Format detection rules (when `--format` is not specified):**

1. If `-o` has a `.sqlitedb` or `.mbtiles` extension → format is detected from it.
2. If `-o` is not set either → in interactive mode the user is prompted to choose; in quiet mode `sqlitedb` is used.
3. If both `--format` and `-o` are given → `--format` takes precedence (extension is ignored).

**Examples:**

```bash
# Interactive — prompts for format and filename
uv run main.py src_map_files/mmb26v.map

# Produce sqlitedb explicitly
uv run main.py src_map_files/mmb26v.map -f sqlitedb

# Produce mbtiles, auto-detected from extension
uv run main.py src_map_files/mmb26v.map -o result.mbtiles

# Quiet mode — no prompts, defaults to sqlitedb
uv run main.py src_map_files/mmb26v.map -q

# Quiet mode with specific format and output name
uv run main.py src_map_files/mmb26v.map -q -f mbtiles -o my_map.mbtiles
```

The tool prints map info, lets you change the output filename, and asks for confirmation before processing.

## Project structure

```
main.py              # CLI entry point, interactive pipeline
map_parser.py        # OziExplorer .map file parser
transformer.py       # GDAL warp: UTM → Web Mercator (EPSG:3857)
tiler.py             # gdal2tiles + PNG optimization + mbutil packing
database.py          # MBTiles → OsmAnd sqlitedb conversion, format helpers
map_calc_tools.py    # Zoom level calculations, UTM ↔ WGS84
```

## License

See [LICENSE](LICENSE) file for details.
