#!/usr/bin/env python

import argparse
import os
import sys
from PIL import Image

from database import get_database_filename, create_database
from map_calc_tools import (
    calculate_optimal_z,
    get_tile_coords_by_gps,
    get_tile_center_gps,
    find_pixel_coords,
)


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Скрипт для обработки изображений с GPS-координатами.",
        usage="%(prog)s <image_file> <top_left_lat> <top_left_lon> <bottom_right_lat> <bottom_right_lon> [max_zoom] [output_format] [quality] [--analyze]",
    )

    parser.add_argument(
        "image_file", help="Имя файла изображения (обязательно, формат png или jpeg)"
    )
    parser.add_argument(
        "top_left_lat",
        type=float,
        help="Широта GPS-координаты левого верхнего угла изображения (десятичная дробь, например 59.987123)",
    )
    parser.add_argument(
        "top_left_lon",
        type=float,
        help="Долгота GPS-координаты левого верхнего угла изображения (десятичная дробь)",
    )
    parser.add_argument(
        "bottom_right_lat",
        type=float,
        help="Широта GPS-координаты правого нижнего угла изображения (десятичная дробь)",
    )
    parser.add_argument(
        "bottom_right_lon",
        type=float,
        help="Долгота GPS-координаты правого нижнего угла изображения (десятичная дробь)",
    )
    parser.add_argument(
        "max_zoom",
        nargs="?",
        type=int,
        help="Максимальный уровень масштабирования (целове число от 0 до 22, опционально)",
    )
    parser.add_argument(
        "output_format",
        nargs="?",
        default="png",
        help="Выходной формат изображений (png или jpeg, регистронезависимо, по умолчанию png)",
    )
    parser.add_argument(
        "quality",
        nargs="?",
        type=int,
        help="Качество для формата jpeg (целое число от 1 до 100, по умолчанию 85, используется только если формат jpeg)",
    )
    parser.add_argument(
        "--analyze",
        action="store_true",
        help="Выполнить анализ (именованный параметр без значения)",
    )

    # Если нет аргументов, показать помощь
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    args = parser.parse_args()

    # Нормализация пути для кросс-платформенности
    args.image_file = os.path.normpath(args.image_file)

    # Валидация входного файла
    if not args.image_file.lower().endswith((".png", ".jpg", ".jpeg")):
        parser.error(
            f"Файл изображения должен быть в формате png или jpeg: {args.image_file}"
        )

    # Валидация zoom
    if args.max_zoom is not None and not (0 <= args.max_zoom <= 22):
        parser.error(f"Уровень масштабирования должен быть от 0 до 22: {args.max_zoom}")

    # Нормализация формата
    args.output_format = args.output_format.lower()
    if args.output_format not in ["png", "jpeg"]:
        parser.error(f"Формат должен быть png или jpeg: {args.output_format}")

    # Валидация quality только если jpeg
    if args.output_format == "jpeg":
        if args.quality is None:
            args.quality = 85
        elif not (1 <= args.quality <= 100):
            parser.error(f"Качество должно быть от 1 до 100: {args.quality}")
    else:
        # Для png quality игнорируется
        args.quality = None

    return args


def main():
    args = parse_arguments()

    # Открываем изображение, чтобы получить размеры
    try:
        img = Image.open(args.image_file)
        img_width, img_height = img.size
        img.close()
    except Exception as e:
        print(f"Ошибка открытия изображения: {e}")
        sys.exit(1)

    # Конструируем координаты углов изображения (предполагаем прямоугольник)
    coords = {
        "top_left": (args.top_left_lat, args.top_left_lon),
        "top_right": (args.top_left_lat, args.bottom_right_lon),
        "bottom_right": (args.bottom_right_lat, args.bottom_right_lon),
        "bottom_left": (args.bottom_right_lat, args.top_left_lon),
    }

    # Рассчитываем оптимальный zoom, если не указан
    if args.max_zoom is None:
        max_zoom = calculate_optimal_z(img_width, img_height, coords)
    else:
        max_zoom = args.max_zoom

    # Генерируем уникальное имя базы данных
    db_name = get_database_filename(args.image_file)

    # Создаем базу данных
    create_database(db_name, max_zoom=int(max_zoom), min_zoom=0)

    print(f"Размеры изображения: {img_width}x{img_height}")
    print(f"Максимальный zoom: {max_zoom}")
    print(f"Имя базы данных: {db_name}")


if __name__ == "__main__":
    main()
