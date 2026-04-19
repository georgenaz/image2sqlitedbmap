#!/usr/bin/env python

import io
import math
import sqlite3
import sys

from PIL import Image

from arguments import parse_arguments

from database import get_database_filename, create_database, insert_tile
from map_calc_tools import (
    calculate_optimal_z,
    calc_tile_object,
    find_pixel_coords,
)


def precalculate_values(zoom, coords, img_size, rotate_angle):
    # Compute tile coords for all four corners
    tile_objects = {}
    for corner_name in coords:
        tile_objects[corner_name] = calc_tile_object(coords[corner_name][0], coords[corner_name][1], zoom)

    # Find extreme tile coords
    tile_x_coords = [tile_objects[k]["coords_tile"]["x"] for k in tile_objects]
    tile_y_coords = [tile_objects[k]["coords_tile"]["y"] for k in tile_objects]
    min_x = min(tile_x_coords)
    max_x = max(tile_x_coords)
    min_y = min(tile_y_coords)
    max_y = max(tile_y_coords)

    new_size = {
        "width": (max_x - min_x + 1) * 256,
        "height": (max_y - min_y + 1) * 256,
    }

    # Compute canvas pixel positions for each corner
    corner_positions = {}
    for k, v in tile_objects.items():
        tile_x_offset = v["coords_tile"]["x"] - min_x
        tile_y_offset = v["coords_tile"]["y"] - min_y
        pixel_in_tile = find_pixel_coords(256, 256, v["coords_gps"], coords[k])
        if pixel_in_tile:
            canvas_x = tile_x_offset * 256 + pixel_in_tile[0]
            canvas_y = tile_y_offset * 256 + pixel_in_tile[1]
            corner_positions[k] = (canvas_x, canvas_y)
        else:
            # If not found, use approximate
            corner_positions[k] = (tile_x_offset * 256, tile_y_offset * 256)

    # Also, the top_left tile for tiling
    tile_top_left = calc_tile_object(coords["top_left"][0], coords["top_left"][1], zoom)  # original

    return tile_top_left, new_size, corner_positions, min_x, min_y


def calculate_rotated_corners(width, height, angle_degrees, corner_names=None):
    """
    Вычисляет координаты углов изображения после поворота относительно центра.

    Args:
        width: ширина изображения в пикселях
        height: высота изображения в пикселях
        angle_degrees: угол поворота в градусах (положительный - против часовой стрелки)
        corner_names: список названий углов (по умолчанию: ["top_left", "top_right",
                     "bottom_right", "bottom_left"])

    Returns:
        Словарь с координатами углов после поворота: {"угол": (x, y), ...}
    """
    if corner_names is None:
        corner_names = ["top_left", "top_right", "bottom_right", "bottom_left"]

    # Координаты центра изображения
    center_x = width / 2.0
    center_y = height / 2.0

    # Преобразуем угол в радианы
    angle_rad = math.radians(angle_degrees)
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)

    # Координаты углов относительно центра (до поворота)
    corners_relative = {
        "top_left": (-center_x, -center_y),
        "top_right": (width - center_x, -center_y),
        "bottom_right": (width - center_x, height - center_y),
        "bottom_left": (-center_x, height - center_y)
    }

    # Вычисляем координаты после поворота
    rotated_corners = {}

    for name in corner_names:
        if name not in corners_relative:
            continue

        # Координаты относительно центра до поворота
        x_rel, y_rel = corners_relative[name]

        # Применяем матрицу поворота:
        # x' = x*cos(a) - y*sin(a)
        # y' = x*sin(a) + y*cos(a)
        x_rotated = x_rel * cos_a - y_rel * sin_a
        y_rotated = x_rel * sin_a + y_rel * cos_a

        # Переводим обратно в абсолютные координаты
        x_absolute = x_rotated + center_x
        y_absolute = y_rotated + center_y

        rotated_corners[name] = (x_absolute, y_absolute)

    return rotated_corners


def calculate_corner_shifts(width, height, angle_degrees):
    """
    Вычисляет сдвиги углов изображения при повороте относительно центра.

    Args:
        width: ширина изображения в пикселях
        height: высота изображения в пикселях
        angle_degrees: угол поворота в градусах (положительный - против часовой стрелки)

    Returns:
        Словарь со сдвигами для каждого угла: {"угол": (shift_x, shift_y), ...}
        где shift_x = x_rotated - x_original, shift_y = y_rotated - y_original
    """
    # Координаты углов до поворота
    original_corners = {
        "top_left": (0, 0),
        "top_right": (width, 0),
        "bottom_right": (width, height),
        "bottom_left": (0, height)
    }

    # Координаты после поворота
    rotated_corners = calculate_rotated_corners(width, height, angle_degrees)

    # Вычисляем сдвиги
    shifts = {}

    for name in original_corners:
        if name in rotated_corners:
            x_orig, y_orig = original_corners[name]
            x_rot, y_rot = rotated_corners[name]

            shift_x = x_rot - x_orig
            shift_y = y_rot - y_orig

            shifts[name] = (shift_x, shift_y)

    return shifts


def calculate_distance(point1, point2):
    """
    Вычисляет евклидово расстояние между двумя точками в двумерном пространстве.

    Args:
        point1: кортеж (x1, y1) - координаты первой точки
        point2: кортеж (x2, y2) - координаты второй точки

    Returns:
        float: расстояние между точками
    """
    # Распаковываем координаты
    x1, y1 = point1
    x2, y2 = point2

    dx = x2 - x1  # горизонтальный катет
    dy = y2 - y1  # вертикальный катет

    # по теореме Пифагора
    distance = math.sqrt(dx**2 + dy**2)

    return distance


def process_image(conn, zoom, img_file, new_size, corner_positions, rotate_angle, min_x, min_y, in_coords):
    img = Image.open(img_file).convert("RGBA")

    if img.format == "JPEG":
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        img = Image.open(buffer)

    # Compute original resize size without extreme corners
    tile_top_left = calc_tile_object(in_coords["top_left"][0], in_coords["top_left"][1], zoom)
    tile_bottom_right = calc_tile_object(in_coords["bottom_right"][0], in_coords["bottom_right"][1], zoom)
    tile_bottom_left = calc_tile_object(in_coords["bottom_left"][0], in_coords["bottom_left"][1], zoom)
    orig_shift = {
        "top_left": find_pixel_coords(256, 256, tile_top_left["coords_gps"], in_coords["top_left"]),
        "bottom_right": find_pixel_coords(256, 256, tile_bottom_right["coords_gps"], in_coords["bottom_right"]),
        "bottom_left": find_pixel_coords(256, 256, tile_bottom_left["coords_gps"], in_coords["bottom_left"]),
    }

    new_width = int(calculate_distance(corner_positions["top_left"], corner_positions["top_right"]))
    new_height = int(calculate_distance(corner_positions["top_right"], corner_positions["bottom_right"]))

    if new_width <= 0 or new_height <= 0:
        print(f"Пропускаем zoom {zoom}: размеры для resample некорректны ({new_width}x{new_height})")
        return

    resized_img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

    # Rotate without expand and paste at calculated offset
    w = resized_img.width
    h = resized_img.height
    center_x = w / 2
    center_y = h / 2
    angle_rad = math.radians(rotate_angle)
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)

    # Compute rotated positions for all corners
    corner_names = ["top_left", "top_right", "bottom_right", "bottom_left"]
    rotated_positions = {}
    for i, k in enumerate(corner_names):
        x = (i % 2) * w
        y = (i // 2) * h
        dx = x - center_x
        dy = y - center_y
        rot_x = center_x + dx * cos_a - dy * sin_a
        rot_y = center_y + dx * sin_a + dy * cos_a
        rotated_positions[k] = (rot_x, rot_y)

    rotated_img = resized_img.rotate(rotate_angle, expand=True, resample=Image.BICUBIC)

    final_img = Image.new("RGBA", (new_size["width"], new_size["height"]))
    final_img.paste(rotated_img, (orig_shift['bottom_left'][0], orig_shift['top_left'][1]))

    # Save for debugging
    # final_img.save("test_image.png")

    num_tiles_x = new_size["width"] // 256
    num_tiles_y = new_size["height"] // 256
    total_tiles = num_tiles_x * num_tiles_y

    print(f"Количество тайлов для обработки на zoom {zoom}: {total_tiles} ({num_tiles_x}x{num_tiles_y})")

    tile_count = 0
    for tile_y_offset in range(num_tiles_y):
        for tile_x_offset in range(num_tiles_x):
            x = min_x + tile_x_offset
            y = min_y + tile_y_offset
            z = zoom
            s = 0

            left = tile_x_offset * 256
            upper = tile_y_offset * 256
            right = left + 256
            lower = upper + 256
            cropped = final_img.crop((left, upper, right, lower))

            # Only save if not empty (has content)
            if cropped.getbbox() is not None:
                buffer = io.BytesIO()
                cropped.save(buffer, format="PNG", compress_level=9)
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
        "top_right": (args.top_right_lat, args.top_right_lon),
        "bottom_right": (args.bottom_right_lat, args.bottom_right_lon),
        "bottom_left": (args.bottom_left_lat, args.bottom_left_lon),
    }

    # Рассчитываем угол поворота в метрах для проекции (UTM approx)
    delta_lat = in_coords["top_right"][0] - in_coords["top_left"][0]
    delta_lon = in_coords["top_right"][1] - in_coords["top_left"][1]
    lat_radians = math.radians((in_coords["top_left"][0] + in_coords["top_right"][0]) / 2)
    meters_per_degree_lat = 111319.5
    meters_per_degree_lon = 111319.5 * math.cos(lat_radians)
    delta_y_meters = delta_lat * meters_per_degree_lat
    delta_x_meters = delta_lon * meters_per_degree_lon
    rotate_angle = math.degrees(math.atan2(delta_y_meters, delta_x_meters))

    # Рассчитываем оптимальный zoom, если не указан
    if args.max_zoom is None:
        max_zoom = calculate_optimal_z(img_size["width"], img_size["height"], in_coords, rotate_angle)
    else:
        max_zoom = args.max_zoom

    # Определяем zoom уровни от 3 до max_zoom
    min_zoom = 3
    # min_zoom = max_zoom
    zooms = list(range(min_zoom, max_zoom + 1))

    # Генерируем уникальное имя базы данных
    db_name = get_database_filename(args.image_file)

    print(f"Исходные размеры изображения: {img_size['width']}x{img_size['height']}")
    print(f"Zoom уровни: {zooms}")
    print(f"Имя базы данных: {db_name}")
    print(f"Угол поворота: {rotate_angle:.2f} градусов")

    if args.analyze:
        for zoom in zooms:
            tile_top_left, new_size, corner_positions, min_x, min_y = precalculate_values(zoom, in_coords, img_size, rotate_angle)
            print(f"Zoom {zoom}: Размеры изображения для карты: {new_size['width']}x{new_size['height']}")
        print("Анализ завершен.")
        return

    # Создаем базу данных
    conn = sqlite3.connect(db_name)
    # create_database(db_name, max_zoom=max(zooms), min_zoom=min(zooms), conn=conn)
    create_database(db_name, max_zoom=max(zooms), min_zoom=3, conn=conn)

    for zoom in zooms:
        tile_top_left, new_size, corner_positions, min_x, min_y = precalculate_values(zoom, in_coords, img_size, rotate_angle)
        process_image(conn, zoom, args.image_file, new_size, corner_positions, rotate_angle, min_x, min_y, in_coords)

    conn.close()

    print("Обработка завершена.")


if __name__ == "__main__":
    main()
