# image2sqlitedbmap

Convert georeferenced images into SQLite database tiles compatible with navigation software such as [OsmAnd](https://osmand.net/).

## Overview

This tool takes an image and GPS coordinates for its four corners, then generates map tiles in the Web Mercator projection (XYZ tile format) stored in a SQLite database. The resulting `.sqlitedb` file can be used with offline navigation applications.

## Features

- Automatic calculation of optimal zoom level based on image resolution and GPS coverage
- Image rotation and perspective transformation to align with map projection
- Multi-zoom level tile generation
- SQLite database output compatible with OsmAnd and similar software

## Requirements

- Python 3.11+
- [Pillow](https://pillow.readthedocs.io/) for image processing

## Installation

```bash
pip install pillow
```

## Usage

```bash
python main.py <image_file> <top_left_lat> <top_left_lon> <top_right_lat> <top_right_lon> <bottom_right_lat> <bottom_right_lon> <bottom_left_lat> <bottom_left_lon> [max_zoom] [output_format] [quality] [--analyze]
```

### Arguments

| Argument | Description |
|----------|-------------|
| `image_file` | Image file (png, jpg, jpeg) |
| `top_left_lat` | Latitude of top-left corner (decimal degrees) |
| `top_left_lon` | Longitude of top-left corner (decimal degrees) |
| `top_right_lat` | Latitude of top-right corner (decimal degrees) |
| `top_right_lon` | Longitude of top-right corner (decimal degrees) |
| `bottom_right_lat` | Latitude of bottom-right corner (decimal degrees) |
| `bottom_right_lon` | Longitude of bottom-right corner (decimal degrees) |
| `bottom_left_lat` | Latitude of bottom-left corner (decimal degrees) |
| `bottom_left_lon` | Longitude of bottom-left corner (decimal degrees) |
| `max_zoom` | Maximum zoom level (0-22, optional - auto-calculated if omitted) |
| `output_format` | Output format: png or jpeg (default: png) |
| `quality` | JPEG quality 1-100 (default: 85, only for jpeg) |
| `--analyze` | Analyze image without generating tiles |

### Example

```bash
python main.py map.png 55.751244 37.618423 55.751244 37.628423 55.741244 37.628423 55.741244 37.618423
```

## How It Works

1. **Input**: Image + GPS coordinates for all 4 corners
2. **Calculate optimal zoom**: Determines best zoom level to match image resolution to tile grid
3. **Compute rotation angle**: Accounts for map tilt from corner coordinates
4. **Transform image**: Resize → rotate → paste into canvas with perspective correction
5. **Generate tiles**: Slice into 256×256 tiles and store in SQLite DB

## Database Schema

The output `.sqlitedb` file contains two tables:

```sql
CREATE TABLE tiles (
    x INTEGER, y INTEGER, z INTEGER, s INTEGER,
    image BLOB,
    PRIMARY KEY (x, y, z, s)
);

CREATE TABLE info (
    maxzoom INTEGER, minzoom INTEGER, tilenumbering TEXT
);
```

## Project Structure

```
image2sqlitedbmap/
├── main.py              # Main entry point
├── arguments.py         # CLI argument parsing
├── database.py          # SQLite database operations
├── map_calc_tools.py    # Web Mercator math utilities
└── tests/               # Test suite
```

## Development

### Running tests

```bash
pytest
```

### Code linting

```bash
ruff check .
```

## License

See [LICENSE](LICENSE) file for details.
