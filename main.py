#!/usr/bin/env python

from PIL import Image

from arguments import parse_arguments

from database import get_database_filename, create_database
from map_calc_tools import (
    calculate_optimal_z,
    get_tile_coords_by_gps,
    get_tile_center_gps,
    find_pixel_coords,
)


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
