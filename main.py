#!/usr/bin/env python

import sys

from PIL import Image

from arguments import parse_arguments

from database import get_database_filename, create_database
from map_calc_tools import (
    calculate_optimal_z,
    calc_tile_object,
    get_tile_4corners_gps,
    get_tile_coords_by_gps,
    get_tile_center_gps,
    find_pixel_coords,
)


def main():
    args = parse_arguments()

    # Открываем изображение, чтобы получить размеры
    try:
        pil_img = Image.open(args.image_file)
        original_width, original_height = pil_img.size
        pil_img.close()
    except Exception as e:
        print(f"Ошибка открытия изображения: {e}")
        sys.exit(1)

    img = {"size": {"current": {"width": original_width, "height": original_height}}}

    in_coords = {
        "top_left": (args.top_left_lat, args.top_left_lon),
        "top_right": (args.top_left_lat, args.bottom_right_lon),
        "bottom_right": (args.bottom_right_lat, args.bottom_right_lon),
        "bottom_left": (args.bottom_right_lat, args.top_left_lon),
    }

    # Рассчитываем оптимальный zoom, если не указан
    if args.max_zoom is None:
        max_zoom = calculate_optimal_z(img["size"]["current"]["width"], img["size"]["current"]["height"], in_coords)
    else:
        max_zoom = args.max_zoom

    # Рассчитываем целевой размер изображения для размещения на карте в тайлах
    tile_top_left = calc_tile_object(in_coords["top_left"][0], in_coords["top_left"][1], max_zoom)
    tile_bottom_right = calc_tile_object(in_coords["bottom_right"][0], in_coords["bottom_right"][1], max_zoom)

    img["size"]["new"] = {
        "width": (tile_bottom_right["coords_tile"]["x"] - tile_top_left["coords_tile"]["x"] + 1) * 256,
        "height": (tile_bottom_right["coords_tile"]["y"] - tile_top_left["coords_tile"]["y"] + 1) * 256,
    }

    # Генерируем уникальное имя базы данных
    db_name = get_database_filename(args.image_file)

    img["shift"] = {
        "top_left": find_pixel_coords(256, 256, tile_top_left["coords_gps"], in_coords["top_left"]),
        "bottom_right": find_pixel_coords(256, 256, tile_bottom_right["coords_gps"], in_coords["bottom_right"]),
    }
    print(img["shift"])

    # Создаем базу данных
    # create_database(db_name, max_zoom=int(max_zoom), min_zoom=0)

    print(f"Исходные размеры изображения: {img['size']['current']['width']}x{img['size']['current']['height']}")
    print(f"Максимальный zoom: {max_zoom}")
    print(f"Имя базы данных: {db_name}")

    print("Верхний тайл: ", tile_top_left["coords_tile"])
    print("Нижний тайл: ", tile_bottom_right["coords_tile"])
    print(f"Размеры изображения для карты: {img['size']['new']['width']}x{img['size']['new']['height']}")

    # === Main processing ===



if __name__ == "__main__":
    main()
