#!/usr/bin/env python

import io
import sqlite3
import sys

from PIL import Image

from arguments import parse_arguments

from database import get_database_filename, create_database, insert_tile
from map_calc_tools import (
    calculate_optimal_z,
    calc_tile_object,
    get_tile_4corners_gps,
    get_tile_coords_by_gps,
    get_tile_center_gps,
    find_pixel_coords,
)


def precalculate_values(zoom, coords, img_size):
    tile_top_left = calc_tile_object(coords["top_left"][0], coords["top_left"][1], zoom)
    tile_bottom_right = calc_tile_object(coords["bottom_right"][0], coords["bottom_right"][1], zoom)

    new_size = {
        "width": (tile_bottom_right["coords_tile"]["x"] - tile_top_left["coords_tile"]["x"] + 1) * 256,
        "height": (tile_bottom_right["coords_tile"]["y"] - tile_top_left["coords_tile"]["y"] + 1) * 256,
    }

    shift = {
        "top_left": find_pixel_coords(256, 256, tile_top_left["coords_gps"], coords["top_left"]),
        "bottom_right": find_pixel_coords(256, 256, tile_bottom_right["coords_gps"], coords["bottom_right"]),
    }

    return tile_top_left, tile_bottom_right, new_size, shift


def process_image(conn, zoom, tile_top_left, tile_bottom_right, new_size, shift, img_file):
    img = Image.open(img_file).convert('RGBA')

    if img.format == 'JPEG':
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        img = Image.open(buffer)

    new_width = new_size["width"] - shift["top_left"][0] - (256 - shift["bottom_right"][0])
    new_height = new_size["height"] - shift["top_left"][1] - (256 - shift["bottom_right"][1])

    if new_width <= 0 or new_height <= 0:
        print(f"Пропускаем zoom {zoom}: размеры для resample некорректны ({new_width}x{new_height})")
        return

    resized_img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

    final_img = Image.new('RGBA', (new_size["width"], new_size["height"]))

    final_img.paste(resized_img, shift["top_left"])

    img = final_img

    num_tiles_x = img.width // 256
    num_tiles_y = img.height // 256
    total_tiles = num_tiles_x * num_tiles_y

    print(f"Количество тайлов для обработки на zoom {zoom}: {total_tiles} ({num_tiles_x}x{num_tiles_y})")

    tile_count = 0
    for tile_y_offset in range(num_tiles_y):
        for tile_x_offset in range(num_tiles_x):
            x = tile_top_left["coords_tile"]["x"] + tile_x_offset
            y = tile_top_left["coords_tile"]["y"] + tile_y_offset
            z = zoom
            s = 0

            left = tile_x_offset * 256
            upper = tile_y_offset * 256
            right = left + 256
            lower = upper + 256
            cropped = img.crop((left, upper, right, lower))

            buffer = io.BytesIO()
            cropped.save(buffer, format='PNG', compress_level=9)
            image_data = buffer.getvalue()

            insert_tile(conn, x, y, z, s, image_data)

            tile_count += 1

    print(f"Обработка завершена для zoom {zoom}. Сохранено тайлов: {tile_count}")


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

    img_size = {"width": original_width, "height": original_height}

    in_coords = {
        "top_left": (args.top_left_lat, args.top_left_lon),
        "top_right": (args.top_left_lat, args.bottom_right_lon),
        "bottom_right": (args.bottom_right_lat, args.bottom_right_lon),
        "bottom_left": (args.bottom_right_lat, args.top_left_lon),
    }

    # Рассчитываем оптимальный zoom, если не указан
    if args.max_zoom is None:
        max_zoom = calculate_optimal_z(img_size["width"], img_size["height"], in_coords)
    else:
        max_zoom = args.max_zoom

    # Определяем zoom уровни от 3 до max_zoom
    # min_zoom = 3
    min_zoom = max_zoom
    zooms = list(range(min_zoom, max_zoom + 1))

    # Генерируем уникальное имя базы данных
    db_name = get_database_filename(args.image_file)

    print(f"Исходные размеры изображения: {img_size['width']}x{img_size['height']}")
    print(f"Zoom уровни: {zooms}")
    print(f"Имя базы данных: {db_name}")

    if args.analyze:
        for zoom in zooms:
            tile_top_left, tile_bottom_right, new_size, shift = precalculate_values(zoom, in_coords, img_size)
            print(f"Zoom {zoom}: Размеры изображения для карты: {new_size['width']}x{new_size['height']}")
        print("Анализ завершен.")
        return

    # Создаем базу данных
    conn = sqlite3.connect(db_name)
    create_database(db_name, max_zoom=max(zooms), min_zoom=min(zooms), conn=conn)

    for zoom in zooms:
        tile_top_left, tile_bottom_right, new_size, shift = precalculate_values(zoom, in_coords, img_size)
        process_image(conn, zoom, tile_top_left, tile_bottom_right, new_size, shift, args.image_file)

    conn.close()

    print("Обработка завершена.")





if __name__ == "__main__":
    main()
