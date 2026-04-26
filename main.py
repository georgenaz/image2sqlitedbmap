#!/usr/bin/env python

"""Интерактивное CLI-приложение для конвертации OziExplorer .map → OsmAnd sqlitedb.

Пайплайн:
1. Парсинг .map-файла
2. Проверка изображения
3. Вычисление оптимального zoom
4. Интерактив: вывод информации → подтверждение пользователя
5. Трансформация GDAL (VRT+GCP → warp EPSG:3857)
6. Нарезка на тайлы (gdal2tiles) + оптимизация PNG (PIL) + упаковка (mbutil)
7. Конвертация MBTiles → OsmAnd sqlitedb
8. Очистка временных файлов
"""

import argparse
import logging
import os
import shutil
import sys
import tempfile

from database import get_database_filename, mbtiles_to_osmand_sqlitedb
from map_calc_tools import calculate_min_zoom, calculate_optimal_z, gcp_to_gps_corners
from map_parser import MapFileData, parse_map_file, validate_image
from tiler import process_tiles
from transformer import transform_image

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def parse_args() -> argparse.Namespace:
    """Разбор аргументов командной строки."""
    parser = argparse.ArgumentParser(
        description="Конвертация OziExplorer .map-файла в sqlitedb-карту для OsmAnd.",
    )
    parser.add_argument("map_file", help="Путь к .map-файлу OziExplorer")
    parser.add_argument(
        "-o", "--output",
        help="Имя выходного sqlitedb-файла (без пути; по умолчанию — на основе имени изображения)",
        default=None,
    )
    parser.add_argument(
        "--work-dir",
        help="Рабочая директория для временных файлов (по умолчанию — рядом с .map-файлом)",
        default=None,
    )
    parser.add_argument(
        "--keep-temp",
        action="store_true",
        help="Не удалять временные файлы (VRT, TIF, тайлы, MBTiles)",
    )

    return parser.parse_args()


def print_map_info(map_data: MapFileData, optimal_zoom: int, min_zoom: int, max_zoom_info: int,
                   gps_corners: dict, db_path: str) -> None:
    """Выводит пользователю всю полезную информацию о карте."""
    print()
    print("=" * 60)
    print("  ИНФОРМАЦИЯ О КАРТЕ")
    print("=" * 60)
    print(f"  Файл карты:         {map_data.image_filename}")
    print(f"  Изображение:        {map_data.image_filepath}")
    print(f"  Размер изображения: {map_data.image_width} x {map_data.image_height} px")
    print(f"  UTM зона:           {map_data.utm_zone} ({map_data.epsg_code})")
    print()
    print("  GPS-координаты углов (из UTM GCP):")
    for label, key in [("Левый верхний", "top_left"), ("Правый верхний", "top_right"),
                       ("Правый нижний", "bottom_right"), ("Левый нижний", "bottom_left")]:
        lat, lon = gps_corners[key]
        print(f"    {label:18s}: {lat:.6f}, {lon:.6f}")

    if map_data.gps_corners:
        print()
        print("  GPS-координаты углов (MMPLL из .map-файла):")
        labels = ["Левый верхний", "Правый верхний", "Правый нижний", "Левый нижний"]
        for i, (lat, lon) in enumerate(map_data.gps_corners):
            if i < len(labels):
                print(f"    {labels[i]:18s}: {lat:.6f}, {lon:.6f}")

    print()
    print("  Уровни масштабирования:")
    print(f"    Оптимальный zoom:    {optimal_zoom}")
    print(f"    Минимальный zoom:    {min_zoom}")
    print(f"    max_zoom (в info):   {max_zoom_info}")
    print(f"    Диапазон нарезки:    {min_zoom} – {optimal_zoom}")
    print()
    print(f"  Выходной файл:       {db_path}")
    print("=" * 60)


def interactive_confirm() -> bool:
    """Запрашивает подтверждение пользователя на продолжение."""
    while True:
        answer = input("\nПриступить к созданию sqlitedb? [y/N]: ").strip().lower()
        if answer in ("y", "yes", "д", "да"):
            return True
        if answer in ("n", "no", "н", "нет", ""):
            return False
        print("Введите 'y' или 'n'")


def interactive_db_name(default_path: str) -> str:
    """Позволяет пользователю изменить имя выходного файла."""
    default_name = os.path.basename(default_path)
    new_name = input(f"\nИмя выходного файла [{default_name}]: ").strip()
    if not new_name:
        return default_path
    # Подставляем расширение если нужно
    if not new_name.endswith(".sqlitedb"):
        new_name += ".sqlitedb"
    return os.path.join(os.path.dirname(default_path), new_name)


def cleanup_temp_files(work_dir: str) -> None:
    """Удаляет временные файлы."""
    temp_items = ["temp.vrt", "master_mercator.tif", "output_tiles_folder"]
    for item in temp_items:
        path = os.path.join(work_dir, item)
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
        elif os.path.isfile(path):
            os.remove(path)

    # Удаляем .mbtiles если есть
    for f in os.listdir(work_dir):
        if f.endswith(".mbtiles"):
            os.remove(os.path.join(work_dir, f))


def main() -> None:
    args = parse_args()

    # === Шаг 1: Парсинг .map-файла ===
    print("Чтение .map-файла...")
    try:
        map_data = parse_map_file(args.map_file)
    except (FileNotFoundError, ValueError) as e:
        print(f"ОШИБКА: {e}", file=sys.stderr)
        sys.exit(1)

    # === Шаг 2: Проверка изображения ===
    print("Проверка изображения...")
    try:
        validate_image(map_data)
    except (FileNotFoundError, ValueError) as e:
        print(f"ОШИБКА: {e}", file=sys.stderr)
        sys.exit(1)

    # === Шаг 3: Вычисление zoom ===
    gps_corners = gcp_to_gps_corners(map_data.gcp_points)

    from PIL import Image
    with Image.open(map_data.image_filepath) as img:
        img_w, img_h = img.size

    optimal_zoom = calculate_optimal_z(img_w, img_h, gps_corners)
    min_zoom = calculate_min_zoom(optimal_zoom, gps_corners)
    # max_zoom в info — на 1 больше оптимального (требование OsmAnd)
    max_zoom_info = optimal_zoom + 1

    # === Шаг 4: Интерактив ===
    work_dir = args.work_dir or os.path.dirname(os.path.abspath(map_data.image_filepath))
    default_db_path = get_database_filename(map_data.image_filepath, work_dir)

    # Если пользователь указал имя — используем его
    if args.output:
        output_dir = os.path.dirname(default_db_path)
        output_name = args.output
        if not output_name.endswith(".sqlitedb"):
            output_name += ".sqlitedb"
        db_path = os.path.join(output_dir, output_name)
    else:
        db_path = default_db_path

    print_map_info(map_data, optimal_zoom, min_zoom, max_zoom_info, gps_corners, db_path)

    # Позволяем изменить имя файла
    db_path = interactive_db_name(db_path)

    if not interactive_confirm():
        print("Отменено пользователем.")
        sys.exit(0)

    # === Шаг 5: Трансформация ===
    print("\nШаг 1/3: Трансформация изображения (UTM → Web Mercator)...")
    try:
        tif_path = transform_image(map_data, work_dir)
    except RuntimeError as e:
        print(f"ОШИБКА трансформации: {e}", file=sys.stderr)
        sys.exit(1)

    # === Шаг 6: Нарезка + оптимизация + упаковка ===
    print("\nШаг 2/3: Нарезка на тайлы и оптимизация PNG...")
    try:
        mbtiles_path = process_tiles(tif_path, work_dir, min_zoom, optimal_zoom)
    except RuntimeError as e:
        print(f"ОШИБКА нарезки тайлов: {e}", file=sys.stderr)
        sys.exit(1)

    # === Шаг 7: Конвертация в OsmAnd sqlitedb ===
    print("\nШаг 3/3: Формирование OsmAnd sqlitedb...")
    try:
        result_path = mbtiles_to_osmand_sqlitedb(mbtiles_path, db_path, max_zoom_info, min_zoom)
    except Exception as e:
        print(f"ОШИБКА формирования sqlitedb: {e}", file=sys.stderr)
        sys.exit(1)

    # === Шаг 8: Очистка ===
    if not args.keep_temp:
        print("\nОчистка временных файлов...")
        cleanup_temp_files(work_dir)

    file_size_mb = os.path.getsize(result_path) / (1024 * 1024)
    print(f"\nГотово! Файл создан: {result_path} ({file_size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
