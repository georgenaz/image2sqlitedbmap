#!/usr/bin/env python

import sys
import sqlite3
import math
from PIL import Image

from arguments import parse_arguments
from database import get_database_filename, create_database
from calc_tools import calculate_image_transform_params, calculate_final_corner_gps


def analyze_image_and_coords(args):
    """
    Анализирует исходное изображение и координаты углов.
    Вычисляет оптимальный уровень zoom для отображения "пиксель в пиксель".
    """
    if args.img_width and args.img_height:
        img_width, img_height = args.img_width, args.img_height
        print(f"Размеры изображения: {img_width}x{img_height} пикселей (заданы параметрами)", flush=True)
    else:
        # Открываем изображение для получения размеров
        try:
            pil_img = Image.open(args.image_file)
            img_width, img_height = pil_img.size
            pil_img.close()
        except Exception as e:
            print(f"Ошибка открытия изображения: {e}")
            sys.exit(1)

        print(f"Размеры изображения: {img_width}x{img_height} пикселей", flush=True)

    # Координаты углов
    coords = {
        "top_left": (args.top_left_lat, args.top_left_lon),
        "top_right": (args.top_right_lat, args.top_right_lon),
        "bottom_right": (args.bottom_right_lat, args.bottom_right_lon),
        "bottom_left": (args.bottom_left_lat, args.bottom_left_lon),
    }

    # Коррекция смещения
    if args.offset_distance != 0.0:
        distance_m = args.offset_distance * 1609.34  # мили в метры
        direction_rad = math.radians(args.offset_direction)
        delta_north = distance_m * math.cos(direction_rad)
        delta_east = distance_m * math.sin(direction_rad)
        for corner in coords:
            lat, lon = coords[corner]
            delta_lat = delta_north / 111319.5
            delta_lon = delta_east / (111319.5 * math.cos(math.radians(lat)))
            coords[corner] = (lat - delta_lat, lon - delta_lon)

    print("Координаты углов:")
    for corner, (lat, lon) in coords.items():
        print(f"  {corner}: {lat:.6f}, {lon:.6f}")

    print("Расстояния между углами:")
    # top_left to top_right
    lat1, lon1 = coords["top_left"]
    lat2, lon2 = coords["top_right"]
    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1
    avg_lat = (lat1 + lat2) / 2
    dist_h = math.sqrt((delta_lat * 111319.5)**2 + (delta_lon * 111319.5 * math.cos(math.radians(avg_lat)))**2)
    print(f"  top_left to top_right: {dist_h:.1f} м")

    # top_left to bottom_left
    lat2, lon2 = coords["bottom_left"]
    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1
    avg_lat = (lat1 + lat2) / 2
    dist_v = math.sqrt((delta_lat * 111319.5)**2 + (delta_lon * 111319.5 * math.cos(math.radians(avg_lat)))**2)
    print(f"  top_left to bottom_left: {dist_v:.1f} м")

    # top_right to bottom_right
    lat1, lon1 = coords["top_right"]
    lat2, lon2 = coords["bottom_right"]
    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1
    avg_lat = (lat1 + lat2) / 2
    dist_vr = math.sqrt((delta_lat * 111319.5)**2 + (delta_lon * 111319.5 * math.cos(math.radians(avg_lat)))**2)
    print(f"  top_right to bottom_right: {dist_vr:.1f} м")

    # bottom_left to bottom_right
    lat1, lon1 = coords["bottom_left"]
    lat2, lon2 = coords["bottom_right"]
    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1
    avg_lat = (lat1 + lat2) / 2
    dist_b = math.sqrt((delta_lat * 111319.5)**2 + (delta_lon * 111319.5 * math.cos(math.radians(avg_lat)))**2)
    print(f"  bottom_left to bottom_right: {dist_b:.1f} м")

    # Вычисление оптимального zoom
    optimal_zoom = calculate_optimal_zoom(img_width, img_height, coords)

    print(f"Оптимальный zoom уровень: {optimal_zoom}")

    # Используем заданный zoom или оптимальный
    zoom = args.max_zoom if args.max_zoom is not None else optimal_zoom
    print(f"Используемый zoom уровень: {zoom}")

    # Вычисление параметров преобразования
    transform_params = calculate_image_transform_params(img_width, img_height, coords, zoom)

    print("Параметры преобразования:")
    print(f"  Размер канваса: {transform_params['canvas_width']}x{transform_params['canvas_height']} пикселей")
    print(f"  Целевой размер изображения: {target_width:.1f}x{target_height:.1f} пикселей")
    print(f"  Bounding box после поворота: {transform_params['rotated_bbox']['width']}x{transform_params['rotated_bbox']['height']} пикселей")
    print(f"  Угол поворота: {transform_params['rotation_angle']:.2f}°")
    if 'corner_positions' in transform_params:
        print("  Позиции углов на канвасе:")
        for corner, (x, y) in transform_params['corner_positions'].items():
            print(f"    {corner}: ({x:.1f}, {y:.1f})")

    # С перспективной трансформацией финальные координаты совпадают с входными
    print("Вычисленные GPS координаты углов после преобразования:")
    for corner in ["top_left", "top_right", "bottom_right", "bottom_left"]:
        orig_lat, orig_lon = coords[corner]
        print(f"  {corner}: вход {orig_lat:.6f} {orig_lon:.6f} -> вычислено {orig_lat:.6f} {orig_lon:.6f}")

    # Имя выходного файла
    db_name = get_database_filename(args.image_file)
    print(f"Имя выходного файла: {db_name}")


def calculate_optimal_zoom(img_width_px, img_height_px, coords):
    """
    Вычисляет оптимальный уровень zoom для отображения изображения "пиксель в пиксель"
    на основе расстояний между углами в системе Web Mercator.
    """
    import math

    # Константы
    TILE_SIZE = 256
    EARTH_CIRCUMFERENCE = 40075016.686  # в метрах

    # Извлекаем координаты
    lat_tl, lon_tl = coords["top_left"]
    lat_tr, lon_tr = coords["top_right"]
    lat_br, lon_br = coords["bottom_right"]
    lat_bl, lon_bl = coords["bottom_left"]

    # Вычисляем охват по долготе и широте
    lon_min = min(lon_tl, lon_tr, lon_br, lon_bl)
    lon_max = max(lon_tl, lon_tr, lon_br, lon_bl)
    lat_min = min(lat_tl, lat_tr, lat_br, lat_bl)
    lat_max = max(lat_tl, lat_tr, lat_br, lat_bl)

    # Разница в градусах
    delta_lon = lon_max - lon_min
    delta_lat = lat_max - lat_min

    print(f"Охват по долготе: {delta_lon:.6f}°")
    print(f"Охват по широте: {delta_lat:.6f}°")

    # Для каждого zoom от 0 до 22 вычисляем размер в пикселях
    best_zoom = 0
    best_score = float('inf')

    for zoom in range(5, 18):
        # Количество тайлов на этом zoom
        n = 2 ** zoom

        # Размер мира в тайлах: n x n
        # Размер одного тайла в градусах: 360° / n по долготе, но по широте сложнее из-за Меркатора

        # Для простоты используем приближение: размер в метрах на пиксель
        meters_per_pixel = EARTH_CIRCUMFERENCE / (TILE_SIZE * n)

        # Средняя широта для расчета
        avg_lat = (lat_min + lat_max) / 2
        lat_rad = math.radians(avg_lat)

        # Коррекция для широты (Меркатор сжимает высокие широты)
        # Но для простоты используем приближение

        # Размер охвата в метрах
        delta_lon_m = delta_lon * 111319.5 * math.cos(lat_rad)  # метров на градус долготы
        delta_lat_m = delta_lat * 111319.5  # метров на градус широты

        # Размер охвата в пикселях на этом zoom
        width_px = delta_lon_m / meters_per_pixel
        height_px = delta_lat_m / meters_per_pixel

        print(f"Zoom {zoom}: охват {width_px:.0f}x{height_px:.0f} пикселей")

        # Сравниваем с размером изображения
        # Ищем zoom, где размер охвата closest к размеру изображения
        score = abs(width_px - img_width_px) + abs(height_px - img_height_px)

        if score < best_score:
            best_score = score
            best_zoom = zoom

    return best_zoom


def process_image(conn, zoom, img_file, transform_params, output_format, quality):
    """
    Обрабатывает изображение: масштабирует, поворачивает, вставляет на канвас,
    режет на тайлы.
    """
    from PIL import Image
    import io

    # Открываем изображение
    img = Image.open(img_file).convert("RGBA")

    # Конвертируем JPEG в PNG для лучшего качества
    if img.format == "JPEG":
        buffer = io.BytesIO()
        img.save(buffer, format="PNG", compress_level=9, optimize=True)
        buffer.seek(0)
        img = Image.open(buffer)

    # Получаем параметры
    target_width = max(1, int(transform_params["target_width"]))
    target_height = max(1, int(transform_params["target_height"]))
    rotation_angle = transform_params["rotation_angle"]
    canvas_width = transform_params["canvas_width"]
    canvas_height = transform_params["canvas_height"]
    paste_x = int(transform_params["paste_x"])
    paste_y = int(transform_params["paste_y"])

    print(f"Масштабирование изображения до {target_width}x{target_height} пикселей")
    # Масштабируем
    resized_img = img.resize((target_width, target_height), Image.Resampling.LANCZOS)

    print(f"Поворот изображения на {rotation_angle:.2f}°")
    # Поворачиваем
    rotated_img = resized_img.rotate(rotation_angle, expand=True, resample=Image.BICUBIC)

    print(f"Создание канваса {canvas_width}x{canvas_height} пикселей")
    # Создаем канвас
    canvas = Image.new("RGBA", (canvas_width, canvas_height))

    print(f"Вставка изображения в позицию ({paste_x}, {paste_y})")
    # Вставляем на канвас
    canvas.paste(rotated_img, (paste_x, paste_y))

    # Конвертируем в P для сжатия
    canvas = canvas.convert("P", palette=Image.ADAPTIVE, colors=256)

    # Временно сохраняем подготовленное изображение
    debug_filename = f"debug_prepared_{zoom}.png"
    print(f"Сохранение подготовленного изображения: {debug_filename}")
    canvas.save(debug_filename, compress_level=9, optimize=True)

    # Режем на тайлы
    min_tile_x = transform_params["min_tile_x"]
    min_tile_y = transform_params["min_tile_y"]
    generate_tiles_from_canvas(canvas, zoom, conn, output_format, quality, min_tile_x, min_tile_y)


def generate_tiles_from_canvas(canvas, zoom, conn, output_format, quality, min_tile_x, min_tile_y, min_x=0, min_y=0):
    """
    Режет канвас на тайлы 256x256 и сохраняет в базу данных.
    min_x, min_y - смещение канваса в пикселях относительно оригинального.
    """
    from database import insert_tile
    import io

    tile_size = 256
    num_tiles_x = (canvas.width + tile_size - 1) // tile_size
    num_tiles_y = (canvas.height + tile_size - 1) // tile_size

    total_tiles = num_tiles_x * num_tiles_y
    print(f"Генерация тайлов: {num_tiles_x}x{num_tiles_y} = {total_tiles} тайлов")

    tile_count = 0
    for tile_y_offset in range(num_tiles_y):
        for tile_x_offset in range(num_tiles_x):
            left = tile_x_offset * tile_size
            upper = tile_y_offset * tile_size
            right = min(left + tile_size, canvas.width)
            lower = min(upper + tile_size, canvas.height)

            # Вырезаем тайл
            tile_img = canvas.crop((left, upper, right, lower))

            # Проверяем, есть ли содержимое
            if tile_img.getbbox() is not None:
                # Сохраняем в нужном формате
                buffer = io.BytesIO()
                if output_format == "png":
                    tile_img.save(buffer, format="PNG", compress_level=9)
                else:  # jpeg
                    # Конвертируем в RGB для JPEG
                    tile_img = tile_img.convert("RGB")
                    tile_img.save(buffer, format="JPEG", quality=quality)

                image_data = buffer.getvalue()

                # Вычисляем координаты тайла с учетом смещения
                abs_x = left + min_x
                abs_y = upper + min_y
                x = min_tile_x + (abs_x // tile_size)
                y = min_tile_y + (abs_y // tile_size)
                z = zoom
                s = 0

                insert_tile(conn, x, y, z, s, image_data)
                tile_count += 1

    print(f"Сохранено тайлов: {tile_count}")


def main():
    args = parse_arguments()

    if args.analyze:
        analyze_image_and_coords(args)
        return

    # Основной режим
    print("Запуск основного режима генерации тайлов")

    # Получаем размеры изображения
    try:
        pil_img = Image.open(args.image_file)
        img_width, img_height = pil_img.size
        pil_img.close()
    except Exception as e:
        print(f"Ошибка открытия изображения: {e}")
        sys.exit(1)

    print(f"Размеры изображения: {img_width}x{img_height} пикселей")

    # Координаты углов
    coords = {
        "top_left": (args.top_left_lat, args.top_left_lon),
        "top_right": (args.top_right_lat, args.top_right_lon),
        "bottom_right": (args.bottom_right_lat, args.bottom_right_lon),
        "bottom_left": (args.bottom_left_lat, args.bottom_left_lon),
    }

    # Коррекция смещения
    if args.offset_distance != 0.0:
        distance_m = args.offset_distance * 1609.34  # мили в метры
        direction_rad = math.radians(args.offset_direction)
        delta_north = distance_m * math.cos(direction_rad)
        delta_east = distance_m * math.sin(direction_rad)
        for corner in coords:
            lat, lon = coords[corner]
            delta_lat = delta_north / 111319.5
            delta_lon = delta_east / (111319.5 * math.cos(math.radians(lat)))
            coords[corner] = (lat - delta_lat, lon - delta_lon)

    # Вычисление оптимального zoom
    optimal_zoom = calculate_optimal_zoom(img_width, img_height, coords)
    max_zoom = args.max_zoom if args.max_zoom is not None else optimal_zoom
    min_zoom = 5

    print(f"Оптимальный zoom уровень: {optimal_zoom}")
    print(f"Максимальный zoom уровень: {max_zoom}")
    print(f"Минимальный zoom уровень: {min_zoom}")

    # Создание базы данных
    db_name = get_database_filename(args.image_file)
    print(f"Создание базы данных: {db_name}")

    conn = sqlite3.connect(db_name)
    create_database(db_name, max_zoom=max_zoom, min_zoom=min_zoom, conn=conn)

    # Обработка для каждого zoom уровня от max_zoom до min_zoom
    for zoom in range(max_zoom, min_zoom - 1, -1):
        print(f"\n--- Обработка zoom уровня {zoom} ---")

        # Вычисление параметров преобразования для этого zoom
        transform_params = calculate_image_transform_params(img_width, img_height, coords, zoom)

        target_width = transform_params["target_width"]
        target_height = transform_params["target_height"]

        print("Параметры преобразования:")
        print(f"  Размер канваса: {transform_params['canvas_width']}x{transform_params['canvas_height']} пикселей")
        print(f"  Целевой размер изображения: {target_width:.1f}x{target_height:.1f} пикселей")
        print(f"  Bounding box после поворота: {transform_params['rotated_bbox']['width']}x{transform_params['rotated_bbox']['height']} пикселей")
        print(f"  Угол поворота: {transform_params['rotation_angle']:.2f}°")

        # Для низких zoom изображение может быть очень маленьким, но все равно генерируем

        # Обработка изображения для этого zoom
        process_image(conn, zoom, args.image_file, transform_params, args.output_format, args.quality)

    conn.close()
    print("\nГенерация тайлов завершена")


if __name__ == "__main__":
    main()