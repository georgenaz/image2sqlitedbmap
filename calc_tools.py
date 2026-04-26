#!/usr/bin/env python

import math


def utm_to_latlon(easting, northing, zone, northern=True):
    """
    Конвертирует UTM координаты в WGS84 lat/lon.
    Приближенная формула, для точности используйте pyproj.

    Args:
        easting: Восточная координата в метрах
        northing: Северная координата в метрах
        zone: UTM зона (1-60)
        northern: True для северного полушария

    Returns:
        (lat, lon) в десятичных градусах
    """
    # Константы для WGS84
    a = 6378137.0  # большая полуось
    f = 1 / 298.257223563  # сжатие
    k0 = 0.9996  # масштабный коэффициент

    e = math.sqrt(f * (2 - f))  # эксцентриситет
    e1sq = e**2 / (1 - e**2)

    # Центральный меридиан зоны
    lon0 = (zone - 1) * 6 - 180 + 3  # +3 для центрального

    # Корректировка northing для южного полушария
    if not northern:
        northing -= 10000000

    # Мерidian arc
    m = northing / k0
    mu = m / (a * (1 - e**2/4 - 3*e**4/64 - 5*e**6/256))

    # Коэффициенты
    e1 = (1 - math.sqrt(1 - e**2)) / (1 + math.sqrt(1 - e**2))
    j1 = 3*e1/2 - 27*e1**3/32
    j2 = 21*e1**2/16 - 55*e1**4/32
    j3 = 151*e1**3/96
    j4 = 1097*e1**4/512

    fp = mu + j1*math.sin(2*mu) + j2*math.sin(4*mu) + j3*math.sin(6*mu) + j4*math.sin(8*mu)

    c1 = e1sq * math.cos(fp)**2
    t1 = math.tan(fp)**2
    r1 = a * (1 - e**2) / (1 - e**2 * math.sin(fp)**2)**(3/2)
    n1 = a / math.sqrt(1 - e**2 * math.sin(fp)**2)
    d = (easting - 500000) / (n1 * k0)

    # Широта
    lat = fp - (n1 * math.tan(fp) / r1) * (d**2/2 - (5 + 3*t1 + 10*c1 - 4*c1**2 - 9*e1sq)*d**4/24 + (61 + 90*t1 + 298*c1 + 45*t1**2 - 252*e1sq - 3*c1**2)*d**6/720)

    # Долгота
    lon = lon0 + (d - (1 + 2*t1 + c1)*d**3/6 + (5 - 2*c1 + 28*t1 - 3*c1**2 + 8*e1sq + 24*t1**2)*d**5/120) / math.cos(fp)

    return math.degrees(lat), math.degrees(lon)

# Константы
TILE_SIZE = 256
EARTH_CIRCUMFERENCE = 40075016.686  # в метрах
MAX_LATITUDE = 85.051129


def validate_gps_coords(lat: float, lon: float) -> None:
    """Проверяет корректность GPS-координат."""
    if not (-90.0 <= lat <= 90.0):
        raise ValueError(f"Широта должна быть в диапазоне [-90, 90], получено: {lat}")
    if not (-180.0 <= lon <= 180.0):
        raise ValueError(f"Долгота должна быть в диапазоне [-180, 180], получено: {lon}")
    if abs(lat) > MAX_LATITUDE:
        raise ValueError(f"Широта {lat}° выходит за пределы Web Mercator (±{MAX_LATITUDE}°)")


def gps_to_tile_coords(lat: float, lon: float, zoom: int) -> tuple[int, int]:
    """Преобразует GPS в координаты тайла (x, y)."""
    validate_gps_coords(lat, lon)

    n = 2 ** zoom
    x = math.floor(n * ((lon + 180) / 360)) % n
    y = math.floor(n * (1 - math.log(math.tan(math.radians(lat)) + 1/math.cos(math.radians(lat))) / math.pi) / 2)

    return x, y


def tile_coords_to_gps(x: int, y: int, zoom: int) -> tuple[float, float]:
    """Преобразует координаты тайла в GPS центра тайла."""
    n = 2 ** zoom

    lon = (x + 0.5) / n * 360 - 180
    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * (y + 0.5) / n)))
    lat = math.degrees(lat_rad)

    return lat, lon


def pixel_in_tile_to_gps(tile_x: int, tile_y: int, zoom: int, pixel_x: int, pixel_y: int) -> tuple[float, float]:
    """Преобразует пиксельные координаты в тайле в GPS."""
    n = 2 ** zoom

    # Относительные координаты в мире [0,1]
    world_x = (tile_x + pixel_x / TILE_SIZE) / n
    world_y = (tile_y + pixel_y / TILE_SIZE) / n

    # В долготу
    lon = world_x * 360 - 180

    # В широту (обратная Меркатор)
    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * world_y)))
    lat = math.degrees(lat_rad)

    return lat, lon


def calculate_rotation_angle(coords: dict) -> float:
    """Вычисляет угол поворота по координатам верхнего края."""
    lat1, lon1 = coords["top_left"]
    lat2, lon2 = coords["top_right"]

    # Приближение через разницу координат
    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1

    # Средняя широта
    avg_lat = (lat1 + lat2) / 2
    lat_rad = math.radians(avg_lat)

    # Метры
    meters_per_deg_lat = 111319.5
    meters_per_deg_lon = 111319.5 * math.cos(lat_rad)

    delta_y = delta_lat * meters_per_deg_lat
    delta_x = delta_lon * meters_per_deg_lon

    angle = math.degrees(math.atan2(delta_y, delta_x))

    return angle


def calculate_image_transform_params(img_width: int, img_height: int, coords: dict, zoom: int) -> dict:
    """
    Вычисляет параметры преобразования изображения для наложения на карту.
    Использует оригинальный подход с corner_positions.
    """
    # Вычисляем тайлы для углов
    tile_objects = {}
    for corner, (lat, lon) in coords.items():
        tile_objects[corner] = calc_tile_object(lat, lon, zoom)

    # Находим bounding box тайлов
    tile_xs = [to["coords_tile"]["x"] for to in tile_objects.values()]
    tile_ys = [to["coords_tile"]["y"] for to in tile_objects.values()]

    min_tile_x = min(tile_xs)
    max_tile_x = max(tile_xs)
    min_tile_y = min(tile_ys)
    max_tile_y = max(tile_ys)

    # Расширяем bounding box на 1 тайл во все стороны для запаса
    min_tile_x -= 1
    max_tile_x += 1
    min_tile_y -= 1
    max_tile_y += 1

    canvas_width = (max_tile_x - min_tile_x + 1) * TILE_SIZE
    canvas_height = (max_tile_y - min_tile_y + 1) * TILE_SIZE

    # Вычисляем пиксельные позиции углов на канвасе
    corner_positions = {}
    for corner, tile_obj in tile_objects.items():
        tile_x = tile_obj["coords_tile"]["x"]
        tile_y = tile_obj["coords_tile"]["y"]

        # Позиция тайла на канвасе
        tile_offset_x = (tile_x - min_tile_x) * TILE_SIZE
        tile_offset_y = (tile_y - min_tile_y) * TILE_SIZE

        # Пиксель в тайле
        pixel_in_tile = find_pixel_coords_in_tile(tile_x, tile_y, zoom, coords[corner])

        canvas_x = tile_offset_x + pixel_in_tile[0]
        canvas_y = tile_offset_y + pixel_in_tile[1]

        corner_positions[corner] = (canvas_x, canvas_y)

    # Вычисляем размеры изображения на основе GPS расстояний
    # Расстояние по горизонтали (top_left to top_right)
    lat1, lon1 = coords["top_left"]
    lat2, lon2 = coords["top_right"]
    delta_lat_h = lat2 - lat1
    delta_lon_h = lon2 - lon1
    avg_lat_h = (lat1 + lat2) / 2
    dist_h_m = math.sqrt(
        (delta_lat_h * 111319.5) ** 2 +
        (delta_lon_h * 111319.5 * math.cos(math.radians(avg_lat_h))) ** 2
    )

    # Расстояние по вертикали (top_left to bottom_left)
    lat3, lon3 = coords["bottom_left"]
    delta_lat_v = lat3 - lat1
    delta_lon_v = lon3 - lon1
    avg_lat_v = (lat1 + lat3) / 2
    dist_v_m = math.sqrt(
        (delta_lat_v * 111319.5) ** 2 +
        (delta_lon_v * 111319.5 * math.cos(math.radians(avg_lat_v))) ** 2
    )

    # Разрешение на данном zoom (метров на пиксель)
    meters_per_pixel = EARTH_CIRCUMFERENCE / (TILE_SIZE * (2 ** zoom))

    # Целевой размер в пикселях
    target_width = dist_h_m / meters_per_pixel
    target_height = dist_v_m / meters_per_pixel

    # Угол поворота
    rotation_angle = calculate_rotation_angle(coords)

    # Вычисляем bounding box после поворота
    rotated_bbox = calculate_rotated_bounding_box(target_width, target_height, rotation_angle)

    # Позиция вставки: центр повернутого изображения совпадает с центром corner_positions
    target_center_x = sum(pos[0] for pos in corner_positions.values()) / 4
    target_center_y = sum(pos[1] for pos in corner_positions.values()) / 4

    paste_x = target_center_x - rotated_bbox["width"] / 2
    paste_y = target_center_y - rotated_bbox["height"] / 2

    # Корректировка позиционирования для точного совпадения углов
    # Вычисляем, где окажется top_left после трансформаций
    center_x = target_width / 2
    center_y = target_height / 2

    angle_rad = math.radians(rotation_angle)
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)

    # top_left оригинального изображения
    dx = 0 - center_x
    dy = 0 - center_y

    # Поворот
    rot_x = dx * cos_a - dy * sin_a
    rot_y = dx * sin_a + dy * cos_a

    # Финальная позиция на канвасе
    final_x = rot_x + center_x + paste_x
    final_y = rot_y + center_y + paste_y

    # Целевая позиция для top_left
    target_x = corner_positions["top_left"][0]
    target_y = corner_positions["top_left"][1]

    # Корректировка
    correction_x = target_x - final_x
    correction_y = target_y - final_y

    paste_x += correction_x
    paste_y += correction_y

    return {
        "canvas_width": canvas_width,
        "canvas_height": canvas_height,
        "target_width": target_width,
        "target_height": target_height,
        "rotation_angle": rotation_angle,
        "rotated_bbox": rotated_bbox,
        "paste_x": paste_x,
        "paste_y": paste_y,
        "min_tile_x": min_tile_x,
        "min_tile_y": min_tile_y,
        "corner_positions": corner_positions,
    }


def calculate_distance(point1, point2):
    """Вычисляет евклидово расстояние между двумя точками."""
    x1, y1 = point1
    x2, y2 = point2
    return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)


def calc_tile_object(lat: float, lon: float, zoom: int) -> dict:
    """Создает объект тайла с координатами тайла и GPS."""
    coords_tile = gps_to_tile_coords(lat, lon, zoom)
    coords_gps = get_tile_4corners_gps(coords_tile[0], coords_tile[1], zoom)
    return {
        "coords_tile": {"x": coords_tile[0], "y": coords_tile[1]},
        "coords_gps": coords_gps,
    }


def calculate_target_image_size(coords: dict, zoom: int) -> tuple[float, float]:
    """
    Вычисляет целевой размер изображения на основе расстояний между углами в пикселях.
    """
    # Вычисляем расстояния между углами в метрах
    lat1, lon1 = coords["top_left"]
    lat2, lon2 = coords["top_right"]
    lat3, lon3 = coords["bottom_left"]

    # Расстояние по горизонтали (top_left to top_right)
    delta_lat_h = lat2 - lat1
    delta_lon_h = lon2 - lon1
    avg_lat_h = (lat1 + lat2) / 2
    dist_h_m = math.sqrt(
        (delta_lat_h * 111319.5) ** 2 +
        (delta_lon_h * 111319.5 * math.cos(math.radians(avg_lat_h))) ** 2
    )

    # Расстояние по вертикали (top_left to bottom_left)
    delta_lat_v = lat3 - lat1
    delta_lon_v = lon3 - lon1
    avg_lat_v = (lat1 + lat3) / 2
    dist_v_m = math.sqrt(
        (delta_lat_v * 111319.5) ** 2 +
        (delta_lon_v * 111319.5 * math.cos(math.radians(avg_lat_v))) ** 2
    )

    # Разрешение на данном zoom (метров на пиксель)
    meters_per_pixel = EARTH_CIRCUMFERENCE / (TILE_SIZE * (2 ** zoom))

    # Целевой размер в пикселях
    target_width = dist_h_m / meters_per_pixel
    target_height = dist_v_m / meters_per_pixel

    return target_width, target_height


def calculate_rotated_bounding_box(width: float, height: float, angle_deg: float) -> dict:
    """
    Вычисляет bounding box повернутого прямоугольника.
    """
    angle_rad = math.radians(angle_deg)
    cos_a = abs(math.cos(angle_rad))
    sin_a = abs(math.sin(angle_rad))

    # Размеры bounding box
    bbox_width = width * cos_a + height * sin_a
    bbox_height = height * cos_a + width * sin_a

    # Округляем до ближайшего большего TILE_SIZE
    bbox_width = math.ceil(bbox_width / TILE_SIZE) * TILE_SIZE
    bbox_height = math.ceil(bbox_height / TILE_SIZE) * TILE_SIZE

    return {
        "width": bbox_width,
        "height": bbox_height,
    }


def find_pixel_coords_in_tile(tile_x: int, tile_y: int, zoom: int, target_gps: tuple[float, float]) -> tuple[float, float]:
    """
    Вычисляет субпиксельные координаты GPS-точки внутри тайла.
    """
    target_lat, target_lon = target_gps

    n = 2 ** zoom

    # Для долготы - линейная интерполяция
    lon_left = tile_x / n * 360 - 180
    lon_right = (tile_x + 1) / n * 360 - 180
    rel_x = (target_lon - lon_left) / (lon_right - lon_left)
    pixel_x = rel_x * TILE_SIZE

    # Для широты - правильная Меркатор проекция
    lat_rad = math.radians(target_lat)
    merc_y = (1 - math.log(math.tan(lat_rad) + 1/math.cos(lat_rad)) / math.pi) / 2

    merc_y_top = tile_y / n
    rel_y = (merc_y - merc_y_top) * n
    pixel_y = rel_y * TILE_SIZE

    return pixel_x, pixel_y


def get_tile_4corners_gps(x_tile: int, y_tile: int, z: int) -> dict:
    """
    Возвращает GPS координаты четырех углов тайла.
    """
    corners = {}
    corners["top_left"] = get_tile_lefttop_corner_gps(x_tile, y_tile, z)
    corners["top_right"] = get_tile_lefttop_corner_gps(x_tile + 1, y_tile, z)
    corners["bottom_right"] = get_tile_lefttop_corner_gps(x_tile + 1, y_tile + 1, z)
    corners["bottom_left"] = get_tile_lefttop_corner_gps(x_tile, y_tile + 1, z)
    return corners


def get_tile_lefttop_corner_gps(x_tile: int, y_tile: int, z: int) -> tuple[float, float]:
    """
    GPS координаты левого верхнего угла тайла.
    """
    n = 2 ** z

    lon_deg = x_tile / n * 360 - 180

    y_pos_relative = y_tile / n
    merc_n = math.pi * (1.0 - 2.0 * y_pos_relative)
    lat_rad = math.atan(math.sinh(merc_n))
    lat_deg = math.degrees(lat_rad)

    return lat_deg, lon_deg


def find_perspective_coeffs(source_points, target_points):
    """
    Вычисляет коэффициенты для перспективной трансформации PIL.
    source_points: [(x,y), ...] углы исходного изображения
    target_points: [(x,y), ...] целевые позиции на канвасе
    Возвращает (a, b, c, d, e, f, g, h) для Image.PERSPECTIVE
    """
    sx = [p[0] for p in source_points]
    sy = [p[1] for p in source_points]
    tx = [p[0] for p in target_points]
    ty = [p[1] for p in target_points]

    # Строим матрицу A и вектор B для системы уравнений
    A = []
    B = []
    for i in range(4):
        # Уравнение для x
        A.append([sx[i], sy[i], 1, 0, 0, 0, -sx[i]*tx[i], -sy[i]*tx[i]])
        B.append(tx[i])
        # Уравнение для y
        A.append([0, 0, 0, sx[i], sy[i], 1, -sx[i]*ty[i], -sy[i]*ty[i]])
        B.append(ty[i])

    # Расширенная матрица
    for i in range(8):
        A[i].append(B[i])

    # Гауссово исключение
    for i in range(8):
        # Поиск опорного элемента
        max_row = i
        for k in range(i+1, 8):
            if abs(A[k][i]) > abs(A[max_row][i]):
                max_row = k
        A[i], A[max_row] = A[max_row], A[i]

        # Исключение
        for k in range(i+1, 8):
            c = -A[k][i] / A[i][i]
            for j in range(i, 9):
                A[k][j] += c * A[i][j]

    # Обратная подстановка
    coeffs = [0] * 8
    for i in range(7, -1, -1):
        coeffs[i] = A[i][8]
        for j in range(i+1, 8):
            coeffs[i] -= A[i][j] * coeffs[j]
        coeffs[i] /= A[i][i]

    return tuple(coeffs)


def calculate_final_corner_gps(transform_params: dict, coords: dict, zoom: int) -> dict:
    """
    Вычисляет GPS координаты углов после преобразования и наложения.
    """
    # Получаем параметры
    target_width = transform_params["target_width"]
    target_height = transform_params["target_height"]
    rotation_angle = transform_params["rotation_angle"]
    paste_x = transform_params["paste_x"]
    paste_y = transform_params["paste_y"]
    min_tile_x = transform_params["min_tile_x"]
    min_tile_y = transform_params["min_tile_y"]

    # Углы оригинального изображения (до преобразований)
    original_corners = {
        "top_left": (0, 0),
        "top_right": (target_width, 0),
        "bottom_right": (target_width, target_height),
        "bottom_left": (0, target_height),
    }

    # Центр масштабирования/поворота
    center_x = target_width / 2
    center_y = target_height / 2

    # Поворачиваем углы
    angle_rad = math.radians(rotation_angle)
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)

    rotated_corners = {}
    for corner, (x, y) in original_corners.items():
        # Сдвиг к центру
        dx = x - center_x
        dy = y - center_y

        # Поворот
        rot_x = dx * cos_a - dy * sin_a
        rot_y = dx * sin_a + dy * cos_a

        # Сдвиг обратно + вставка на канвас
        final_x = rot_x + center_x + paste_x
        final_y = rot_y + center_y + paste_y

        rotated_corners[corner] = (final_x, final_y)

    # Преобразуем пиксельные координаты в GPS
    final_coords = {}
    for corner, (pixel_x, pixel_y) in rotated_corners.items():
        # Определяем тайл
        tile_x_offset = int(pixel_x // TILE_SIZE)
        tile_y_offset = int(pixel_y // TILE_SIZE)

        abs_tile_x = min_tile_x + tile_x_offset
        abs_tile_y = min_tile_y + tile_y_offset

        pixel_in_tile_x = pixel_x % TILE_SIZE
        pixel_in_tile_y = pixel_y % TILE_SIZE

        # В GPS
        lat, lon = pixel_in_tile_to_gps(abs_tile_x, abs_tile_y, zoom, pixel_in_tile_x, pixel_in_tile_y)
        final_coords[corner] = (lat, lon)

    return final_coords
