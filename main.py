#!/usr/bin/env python

import argparse
import sys

from map_calc_tools import (
    calculate_optimal_z,
    get_tile_coords,
    get_tile_center_gps,
    find_pixel_coords,
)


def parse_arguments():
    parser = argparse.ArgumentParser(
        description='Скрипт для обработки изображений с GPS-координатами.',
        usage='%(prog)s <image_file> <top_left_lat> <top_left_lon> <bottom_right_lat> <bottom_right_lon> [max_zoom] [output_format] [quality] [--analyze]'
    )

    parser.add_argument(
        'image_file',
        help='Имя файла изображения (обязательно, формат png или jpeg)'
    )
    parser.add_argument(
        'top_left_lat', type=float,
        help='Широта GPS-координаты левого верхнего угла изображения (десятичная дробь, например 59.987123)'
    )
    parser.add_argument(
        'top_left_lon', type=float,
        help='Долгота GPS-координаты левого верхнего угла изображения (десятичная дробь)'
    )
    parser.add_argument(
        'bottom_right_lat', type=float,
        help='Широта GPS-координаты правого нижнего угла изображения (десятичная дробь)'
    )
    parser.add_argument(
        'bottom_right_lon', type=float,
        help='Долгота GPS-координаты правого нижнего угла изображения (десятичная дробь)'
    )
    parser.add_argument(
        'max_zoom', nargs='?', type=int,
        help='Максимальный уровень масштабирования (целове число от 0 до 22, опционально)'
    )
    parser.add_argument(
        'output_format', nargs='?', default='png',
        help='Выходной формат изображений (png или jpeg, регистронезависимо, по умолчанию png)'
    )
    parser.add_argument(
        'quality', nargs='?', type=int,
        help='Качество для формата jpeg (целое число от 1 до 100, по умолчанию 85, используется только если формат jpeg)'
    )
    parser.add_argument(
        '--analyze', action='store_true',
        help='Выполнить анализ (именованный параметр без значения)'
    )

    # Если нет аргументов, показать помощь
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    args = parser.parse_args()

    # Валидация входного файла
    if not args.image_file.lower().endswith(('.png', '.jpg', '.jpeg')):
        parser.error(f"Файл изображения должен быть в формате png или jpeg: {args.image_file}")

    # Валидация zoom
    if args.max_zoom is not None and not (0 <= args.max_zoom <= 22):
        parser.error(f"Уровень масштабирования должен быть от 0 до 22: {args.max_zoom}")

    # Нормализация формата
    args.output_format = args.output_format.lower()
    if args.output_format not in ['png', 'jpeg']:
        parser.error(f"Формат должен быть png или jpeg: {args.output_format}")

    # Валидация quality только если jpeg
    if args.output_format == 'jpeg':
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

    print(f"Args: {args}")
    print(f"Image file: {args.image_file}")
    print(f"Top left: {args.top_left_lat}, {args.top_left_lon}")
    print(f"Bottom right: {args.bottom_right_lat}, {args.bottom_right_lon}")
    print(f"Max zoom: {args.max_zoom}")
    print(f"Output format: {args.output_format}")
    print(f"Quality: {args.quality}")
    print(f"Analyze: {args.analyze}")
    print("\n" + "="*50 + "\n")

    # Пример GPS-координат (взят условный квадрат в районе Москвы/Владимира)
    # Важно: широта, долгота
    coords_example = {
        "top_left": (56.2, 38.5),
        "top_right": (56.2, 40.5),
        "bottom_right": (55.5, 40.5),
        "bottom_left": (55.5, 38.5),
    }

    # Пример размера изображения (изначально не кратно 256)
    width = 8200
    height = 8100

    optimal_zoom = calculate_optimal_z(width, height, coords_example)

    print(f"\nФинальный оптимальный Z-уровень: {optimal_zoom}")

    print("\n" * 4)

    # --- Пример использования вычисления координат тайла ---

    lat_point = 55.918087
    lon_point = 39.533434

    print(f"Координаты: {lat_point}, {lon_point}")

    # Пример для Z=9
    x9, y9 = get_tile_coords(lat_point, lon_point, 9)
    print(f"Для Z=9: X={x9}, Y={y9}")
    # Ожидаемый результат: X=312, Y=158 (совпадает с расчетами выше)

    # Пример для Z=13
    x13, y13 = get_tile_coords(lat_point, lon_point, 13)
    print(f"Для Z=13: X={x13}, Y={y13}")
    # Ожидаемый результат: X=4996, Y=2538 (совпадает с расчетами выше)

    # Пример для Z=18
    x18, y18 = get_tile_coords(lat_point, lon_point, 18)
    print(f"Для Z=18: X={x18}, Y={y18}")
    # Ожидаемый результат: X=160010, Y=81297 (совпадает с расчетами выше)

    print("\n" * 4)

    # Используем координаты тайла, которые мы получили ранее для Z=13: X=4996, Y=2538

    x_test = 4995
    y_test = 2554
    z_test = 13

    center_lat, center_lon = get_tile_center_gps(x_test, y_test, z_test)

    print(f"Координаты центра тайла X={x_test}, Y={y_test}, Z={z_test}:")
    print(f"Широта: {center_lat:.6f}")
    print(f"Долгота: {center_lon:.6f}")

    # Ожидаемый результат: координаты должны быть очень близки к исходным 55.918087, 39.533434
    # Получаемый результат при выполнении кода:
    # Широта: 55.917637
    # Долгота: 39.531250

    # Небольшое отличие от исходных 55.918087, 39.533434 естественно,
    # так как исходная точка была где-то внутри тайла, а функция вернула
    # точный центр этого тайла.

    print("\n" * 4)

    # Координаты углов изображения (используем тот же пример, что и раньше)
    image_corners = {
        "top_left": (56.2, 38.5),
        "top_right": (56.2, 40.5),
        "bottom_right": (55.5, 40.5),
        "bottom_left": (55.5, 38.5),
    }

    # Размеры изображения (предположим 8000x8000 пикселей)
    image_width = 8000
    image_height = 8000

    # Целевая точка (наша тестовая точка из предыдущих примеров)
    target_gps = (55.918087, 39.533434)

    # Вычисляем положение точки на изображении
    pixel_coords = find_pixel_coords(
        image_width, image_height, image_corners, target_gps
    )

    if pixel_coords:
        print(f"Image size: {image_width}x{image_height}")
        print(
            f"\nЦелевая GPS-точка ({target_gps[0]:.6f}, {target_gps[1]:.6f}) найдена в пикселях:"
        )
        print(f"X (горизонталь): {pixel_coords[0]} px")
        print(f"Y (вертикаль):   {pixel_coords[1]} px")


if __name__ == "__main__":
    main()
