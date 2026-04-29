#!/usr/bin/env python

"""Интерактивное CLI-приложение для конвертации OziExplorer .map → OsmAnd sqlitedb / MBTiles.

Repository: https://github.com/georgenaz/image2sqlitedbmap

Пайплайн:
1. Парсинг .map-файла
2. Проверка изображения
3. Вычисление оптимального zoom
4. Интерактив: вывод информации → выбор формата → подтверждение
5. Трансформация GDAL (VRT+GCP → warp EPSG:3857)
6. Нарезка на тайлы (gdal2tiles) + оптимизация PNG (PIL) + упаковка (mbutil)
7. (Если sqlitedb) Конвертация MBTiles → OsmAnd sqlitedb
8. Очистка временных файлов
"""

import argparse
import logging
import os
import shutil
import sys

from database import (
    FORMAT_MBTILES,
    FORMAT_SQLITEDB,
    VALID_FORMATS,
    detect_format_by_extension,
    get_output_filename,
    mbtiles_to_osmand_sqlitedb,
)
from map_calc_tools import calculate_min_zoom, calculate_optimal_z, gcp_to_gps_corners
from map_parser import MapFileData, parse_map_file, validate_image
from tiler import process_tiles
from transformer import transform_image

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def parse_args() -> argparse.Namespace:
    """Разбор аргументов командной строки."""
    parser = argparse.ArgumentParser(
        description="Конвертация OziExplorer .map-файла в карту для OsmAnd (sqlitedb) или MBTiles.",
    )
    parser.add_argument("map_file", help="Путь к .map-файлу OziExplorer")
    parser.add_argument(
        "-o", "--output",
        help="Имя выходного файла (без пути). Расширение определяет формат, если --format не задан",
        default=None,
    )
    parser.add_argument(
        "-f", "--format",
        choices=VALID_FORMATS,
        dest="output_format",
        help="Выходной формат: sqlitedb (по умолчанию) или mbtiles",
    )
    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Тихий режим: без подтверждений, формат по умолчанию (sqlitedb)",
    )
    parser.add_argument(
        "--work-dir",
        help="Рабочая директория для временных файлов (по умолчанию — рядом с .map-файлом)",
        default=None,
    )
    parser.add_argument(
        "--keep-temp",
        action="store_true",
        help="Не удалять временные файлы (VRT, TIF, тайлы)",
    )

    return parser.parse_args()


def resolve_format(args: argparse.Namespace) -> str | None:
    """Определяет выходной формат из аргументов.

    Приоритет:
    1. Явно заданный --format
    2. Расширение из --output
    3. None (не определён — спросить у пользователя)

    Returns:
        Строка формата или None.
    """
    if args.output_format:
        return args.output_format
    if args.output:
        return detect_format_by_extension(args.output)
    return None


def interactive_format_menu() -> str:
    """Интерактивный выбор формата пользователем."""
    print()
    print("Выберите формат выходного файла:")
    print("  1 — sqlitedb  (OsmAnd)  [по умолчанию]")
    print("  2 — mbtiles")
    while True:
        answer = input("Ваш выбор [1]: ").strip()
        if answer in ("", "1"):
            return FORMAT_SQLITEDB
        if answer == "2":
            return FORMAT_MBTILES
        print("Введите 1 или 2")


def print_map_info(map_data: MapFileData, optimal_zoom: int, min_zoom: int, max_zoom_info: int,
                   gps_corners: dict, output_path: str, fmt: str) -> None:
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
    print(f"  Выходной формат:     {fmt}")
    print(f"  Выходной файл:       {output_path}")
    print("=" * 60)


def interactive_confirm(fmt: str) -> bool:
    """Запрашивает подтверждение пользователя на продолжение."""
    while True:
        answer = input(f"\nПриступить к созданию {fmt}? [y/N]: ").strip().lower()
        if answer in ("y", "yes", "д", "да"):
            return True
        if answer in ("n", "no", "н", "нет", ""):
            return False
        print("Введите 'y' или 'n'")


def interactive_output_name(default_path: str, fmt: str) -> str:
    """Позволяет пользователю изменить имя выходного файла."""
    default_name = os.path.basename(default_path)
    new_name = input(f"\nИмя выходного файла [{default_name}]: ").strip()
    if not new_name:
        return default_path
    # Подставляем расширение если не указано
    ext = f".{fmt}"
    if not new_name.lower().endswith(ext):
        new_name += ext
    return os.path.join(os.path.dirname(default_path), new_name)


def cleanup_temp_files(work_dir: str, final_mbtiles_path: str | None = None) -> None:
    """Удаляет временные файлы.

    Args:
        work_dir: Рабочая директория.
        final_mbtiles_path: Путь к финальному mbtiles-файлу (не удалять).
    """
    temp_items = ["temp.vrt", "master_mercator.tif", "output_tiles_folder"]
    for item in temp_items:
        path = os.path.join(work_dir, item)
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
        elif os.path.isfile(path):
            os.remove(path)

    # Удаляем промежуточный .mbtiles, если он не является финальным выходным файлом
    for f in os.listdir(work_dir):
        if f.endswith(".mbtiles"):
            full_path = os.path.join(work_dir, f)
            if final_mbtiles_path and os.path.abspath(full_path) == os.path.abspath(final_mbtiles_path):
                continue
            os.remove(full_path)


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
    max_zoom_info = optimal_zoom + 1

    # === Шаг 4: Определение формата и имени файла ===
    work_dir = args.work_dir or os.path.dirname(os.path.abspath(map_data.image_filepath))
    fmt = resolve_format(args)

    if args.quiet:
        # Тихий режим: формат по умолчанию, без интерактива
        if fmt is None:
            fmt = FORMAT_SQLITEDB
        output_path = get_output_filename(map_data.image_filepath, fmt, work_dir)
        if args.output:
            output_dir = os.path.dirname(output_path)
            output_name = args.output
            if not output_name.lower().endswith(f".{fmt}"):
                output_name += f".{fmt}"
            output_path = os.path.join(output_dir, output_name)
    else:
        # Интерактивный режим
        if fmt is None:
            fmt = interactive_format_menu()

        output_path = get_output_filename(map_data.image_filepath, fmt, work_dir)

        # Если пользователь указал имя — используем его
        if args.output:
            output_dir = os.path.dirname(output_path)
            output_name = args.output
            if not output_name.lower().endswith(f".{fmt}"):
                output_name += f".{fmt}"
            output_path = os.path.join(output_dir, output_name)

        print_map_info(map_data, optimal_zoom, min_zoom, max_zoom_info, gps_corners, output_path, fmt)

        # Позволяем изменить имя файла
        output_path = interactive_output_name(output_path, fmt)

        if not interactive_confirm(fmt):
            print("Отменено пользователем.")
            sys.exit(0)

    # === Шаг 5: Трансформация ===
    print("\nШаг 1/3: Трансформация изображения (UTM → Web Mercator)...")
    try:
        tif_path = transform_image(map_data, work_dir)
    except RuntimeError as e:
        print(f"ОШИБКА трансформации: {e}", file=sys.stderr)
        sys.exit(1)

    # === Шаг 6: Нарезка + оптимизация + упаковка в MBTiles ===
    print("\nШаг 2/3: Нарезка на тайлы и оптимизация PNG...")
    try:
        mbtiles_path = process_tiles(tif_path, work_dir, min_zoom, optimal_zoom)
    except RuntimeError as e:
        print(f"ОШИБКА нарезки тайлов: {e}", file=sys.stderr)
        sys.exit(1)

    # === Шаг 7: Финальный выходной файл ===
    if fmt == FORMAT_SQLITEDB:
        print("\nШаг 3/3: Формирование OsmAnd sqlitedb...")
        try:
            result_path = mbtiles_to_osmand_sqlitedb(mbtiles_path, output_path, max_zoom_info, min_zoom)
        except Exception as e:
            print(f"ОШИБКА формирования sqlitedb: {e}", file=sys.stderr)
            sys.exit(1)
        final_mbtiles = None  # промежуточный mbtiles можно удалить
    else:
        # MBTiles — просто перемещаем в финальный путь
        if os.path.abspath(mbtiles_path) != os.path.abspath(output_path):
            shutil.move(mbtiles_path, output_path)
        result_path = output_path
        final_mbtiles = output_path  # не удалять — это финальный файл
        print(f"\nMBTiles создан: {result_path}")

    # === Шаг 8: Очистка ===
    if not args.keep_temp:
        print("\nОчистка временных файлов...")
        cleanup_temp_files(work_dir, final_mbtiles)

    file_size_mb = os.path.getsize(result_path) / (1024 * 1024)
    print(f"\nГотово! Файл создан: {result_path} ({file_size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
