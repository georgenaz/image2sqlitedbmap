import argparse
import os
import sys


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Скрипт для упаковки изображений в sqlitedb-файл карты с использованием указанных GPS-координат (по Web-Mercator в десятичных градусах (WGS84)).",
        usage="%(prog)s <image_file> <top_left_lat> <top_left_lon> <bottom_right_lat> <bottom_right_lon> [max_zoom] [output_format] [quality] [--analyze]",
    )

    parser.add_argument(
        "image_file", help="Имя файла изображения (формат png или jpeg)"
    )
    parser.add_argument(
        "top_left_lat",
        type=float,
        help="Широта GPS-координаты левого верхнего угла изображения",
    )
    parser.add_argument(
        "top_left_lon",
        type=float,
        help="Долгота GPS-координаты левого верхнего угла изображения",
    )
    parser.add_argument(
        "bottom_right_lat",
        type=float,
        help="Широта GPS-координаты правого нижнего угла изображения",
    )
    parser.add_argument(
        "bottom_right_lon",
        type=float,
        help="Долгота GPS-координаты правого нижнего угла изображения",
    )
    parser.add_argument(
        "max_zoom",
        nargs="?",
        type=int,
        help="Максимальный уровень масштабирования (от 0 до 22, опционально)",
    )
    parser.add_argument(
        "output_format",
        nargs="?",
        default="png",
        help="Выходной формат изображений (png или jpeg, по умолчанию png)",
    )
    parser.add_argument(
        "quality",
        nargs="?",
        type=int,
        help="Качество для формата jpeg (от 1 до 100, по умолчанию 85, используется только если формат jpeg)",
    )
    parser.add_argument(
        "--analyze",
        action="store_true",
        help="Выполнить анализ указанного изображения",
    )

    # Если нет аргументов, показать помощь
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    args = parser.parse_args()

    # Нормализация пути для кросс-платформенности
    args.image_file = os.path.normpath(args.image_file)

    # Валидация расширения входного файла
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
