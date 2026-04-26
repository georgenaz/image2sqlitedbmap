#!/usr/bin/env python

"""Модуль нарезки тайлов и оптимизации PNG.

Использует:
- gdal2tiles для нарезки Mercator TIF на тайлы
- mbutil для упаковки тайлов в MBTiles
- PIL для оптимизации PNG (palette + compression)
"""

import logging
import os
import shutil
import subprocess
import sys

from PIL import Image

# Порог размера файла для оптимизации (байты)
OPTIMIZE_SIZE_THRESHOLD = 768


def generate_tiles(tif_path: str, output_dir: str, min_zoom: int, max_zoom: int) -> str:
    """Нарезает Mercator TIF на тайлы с помощью gdal2tiles.

    Args:
        tif_path: Путь к Mercator TIF-файлу.
        output_dir: Директория для тайлов.
        min_zoom: Минимальный уровень масштабирования.
        max_zoom: Максимальный уровень масштабирования.

    Returns:
        Путь к директории с тайлами.
    """
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)

    cmd = [
        sys.executable, "-m", "osgeo_utils.gdal2tiles",
        "-z", f"{min_zoom}-{max_zoom}",
        tif_path,
        output_dir,
    ]

    logging.info(f"Запуск gdal2tiles: {' '.join(cmd)}")

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        # Пробуем альтернативный способ вызова
        cmd_alt = ["gdal2tiles.py", "-z", f"{min_zoom}-{max_zoom}", tif_path, output_dir]
        logging.info(f"Пробуем альтернативный вызов: {' '.join(cmd_alt)}")
        result = subprocess.run(cmd_alt, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"gdal2tiles завершился с ошибкой (код {result.returncode}):\n"
                f"stdout: {result.stdout}\nstderr: {result.stderr}"
            )

    logging.info(f"Тайлы созданы: {output_dir}")
    return output_dir


def optimize_png_tiles(tiles_dir: str) -> int:
    """Оптимизирует PNG-тайлы: конвертирует в palette (256 цветов) + max compression.

    Пропускает файлы меньше OPTIMIZE_SIZE_THRESHOLD байт.

    Args:
        tiles_dir: Директория с тайлами.

    Returns:
        Количество оптимизированных файлов.
    """
    optimized_count = 0

    for root, _dirs, files in os.walk(tiles_dir):
        for name in files:
            if not name.lower().endswith(".png"):
                continue

            path = os.path.join(root, name)
            file_size = os.path.getsize(path)

            # Пропускаем мелкие файлы (обычно пустые/прозрачные)
            if file_size < OPTIMIZE_SIZE_THRESHOLD:
                continue

            try:
                with Image.open(path) as img:
                    # Конвертируем в палитру с адаптивными цветами
                    if img.mode == "RGBA":
                        # Для RGBA используем P с палитрой, сохраняя прозрачность
                        optimized = img.convert("P", palette=Image.ADAPTIVE, colors=256)
                    elif img.mode == "RGB":
                        optimized = img.convert("P", palette=Image.ADAPTIVE, colors=256)
                    else:
                        optimized = img

                    optimized.save(path, optimize=True, compress_level=9)
                    optimized_count += 1
            except Exception as e:
                logging.warning(f"Ошибка оптимизации {path}: {e}")

    logging.info(f"Оптимизировано PNG: {optimized_count} файлов")
    return optimized_count


def tiles_to_mbtiles(tiles_dir: str, mbtiles_path: str) -> str:
    """Упаковывает директорию с тайлами в MBTiles с помощью mbutil.

    Args:
        tiles_dir: Директория с тайлами (структура TMS).
        mbtiles_path: Путь к выходному MBTiles-файлу.

    Returns:
        Путь к MBTiles-файлу.
    """
    try:
        from mbutil import disk_to_mbtiles
        disk_to_mbtiles(tiles_dir, mbtiles_path, quiet=True)
    except ImportError:
        # Запасной вариант — через subprocess
        cmd = ["mb-util", "--silent", tiles_dir, mbtiles_path]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"mb-util завершился с ошибкой: {result.stderr}")

    logging.info(f"MBTiles создан: {mbtiles_path}")
    return mbtiles_path


def process_tiles(tif_path: str, work_dir: str, min_zoom: int, max_zoom: int) -> str:
    """Полный пайплайн нарезки и упаковки тайлов.

    Args:
        tif_path: Путь к Mercator TIF.
        work_dir: Рабочая директория.
        min_zoom: Минимальный zoom.
        max_zoom: Максимальный zoom.

    Returns:
        Путь к MBTiles-файлу.
    """
    tiles_dir = os.path.join(work_dir, "output_tiles_folder")
    base_name = os.path.splitext(os.path.basename(tif_path))[0].replace("master_mercator", "output")
    mbtiles_path = os.path.join(work_dir, f"{base_name}.mbtiles")

    # Удаляем старый mbtiles если есть
    if os.path.exists(mbtiles_path):
        os.remove(mbtiles_path)

    generate_tiles(tif_path, tiles_dir, min_zoom, max_zoom)
    optimize_png_tiles(tiles_dir)
    tiles_to_mbtiles(tiles_dir, mbtiles_path)

    return mbtiles_path
