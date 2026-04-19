#!/usr/bin/env python

import math

# Константа размера тайла в пикселях
TILE_SIZE = 256

# Максимально допустимая широта для Web Mercator (±85.051129°)
MAX_LATITUDE = 85.051129

# Полоса Земли по долготе
LON_RANGE = 360.0
LON_OFFSET = 180.0


def validate_gps_coords(lat: float, lon: float) -> None:
    """
    Проверяет корректность GPS-координат для Web Mercator.

    Args:
        lat: Широта в десятичных градусах.
        lon: Долгота в десятичных градусах.

    Raises:
        ValueError: Если координаты выходят за допустимые пределы.
    """
    if not (-90.0 <= lat <= 90.0):
        raise ValueError(f"Широта должна быть в диапазоне [-90, 90], получено: {lat}")
    if not (-180.0 <= lon <= 180.0):
        raise ValueError(f"Долгота должна быть в диапазоне [-180, 180], получено: {lon}")
    if abs(lat) > MAX_LATITUDE:
        raise ValueError(
            f"Широта {lat}° выходит за пределы Web Mercator (±{MAX_LATITUDE}°). "
            f"Проекция не определена для полярных регионов."
        )


def calculate_optimal_z(img_width_px: int, img_height_px: int, coords: dict, rotate_angle: float) -> int:
    """
    Рассчитывает оптимальный уровень масштабирования (Z-уровень) для изображения,
    чтобы оно отображалось пиксель в пиксель в проекции Web Mercator.

    Args:
        img_width_px: Исходная ширина изображения в пикселях.
        img_height_px: Исходная высота изображения в пикселях.
        coords: Словарь с GPS-координатами углов.
                Пример: {
                    'top_left': (lat_tl, lon_tl),
                    'top_right': (lat_tr, lon_tr),
                    'bottom_right': (lat_br, lon_br),
                    'bottom_left': (lat_bl, lon_bl)
                }

    Returns:
        Оптимальный уровень масштабирования Z (целое число).
    """
    # Validate all GPS coordinates
    for coord in coords.values():
        validate_gps_coords(coord[0], coord[1])

    # 1. Обработка обрезки до ближайшего значения, кратного 256
    original_width = img_width_px
    original_height = img_height_px

    img_width_px = (img_width_px // TILE_SIZE) * TILE_SIZE
    img_height_px = (img_height_px // TILE_SIZE) * TILE_SIZE

    if img_width_px != original_width or img_height_px != original_height:
        print(
            f"Изображение обрезано для кратности 256: {original_width}x{original_height}px -> {img_width_px}x{img_height_px}px"
        )

    if img_width_px == 0 or img_height_px == 0:
        raise ValueError("Размеры изображения после обрезки слишком малы для расчета Z.")

    # 1.5. Расчет размеров после поворота (математически, bounding box)
    theta_rad = math.radians(rotate_angle)
    cos_a = abs(math.cos(theta_rad))
    sin_a = abs(math.sin(theta_rad))

    rot_width = math.ceil(img_width_px * cos_a + img_height_px * sin_a)
    rot_height = math.ceil(img_height_px * cos_a + img_width_px * sin_a)

    rot_width = (rot_width // TILE_SIZE) * TILE_SIZE
    rot_height = (rot_height // TILE_SIZE) * TILE_SIZE

    print(f"Размеры изображения после поворота на {rotate_angle:.2f} градусов: {rot_width}x{rot_height}px")

    img_width_px = rot_width
    img_height_px = rot_height

    # 2. Извлечение координат для расчета охвата (используем крайние координаты из всех четырех углов)
    # Для расчета охвата по горизонтали берем мин и макс долготы
    all_lons = [coord[1] for coord in coords.values()]
    lon_left = min(all_lons)
    lon_right = max(all_lons)
    # Для расчета охвата по вертикали берем макс и мин широты
    all_lats = [coord[0] for coord in coords.values()]
    lat_top = max(all_lats)
    lat_bottom = min(all_lats)

    # 3. Расчет охвата по горизонтали (долгота в градусах)
    delta_lon = abs(lon_right - lon_left)
    # Убеждаемся, что разница не превышает 180 градусов (если карта пересекает 180 меридиан)
    if delta_lon > LON_OFFSET:
        delta_lon = LON_RANGE - delta_lon

    # 4. Расчет охвата по вертикали (Меркаторские относительные координаты 0 до 1)

    def lat_to_mercator_pos(lat_deg):
        """Преобразует широту в относительную Y-позицию (0=Север, 1=Юг)."""
        lat_rad = math.radians(lat_deg)
        # Формула: (1 - ln(tan(lat) + sec(lat)) / PI) / 2
        try:
            # Используем log вместо ln, они одинаковы в Python (math.log - натуральный логарифм)
            merc_n = math.log(math.tan(lat_rad) + (1.0 / math.cos(lat_rad)))
            pos = (1.0 - merc_n / math.pi) / 2.0
            return pos
        except ValueError as e:
            print(f"Ошибка вычисления Меркатора для широты {lat_deg}: {e}")
            return None

    m_top = lat_to_mercator_pos(lat_top)
    m_bottom = lat_to_mercator_pos(lat_bottom)

    if m_top is None or m_bottom is None:
        raise ValueError("Невозможно рассчитать Z из-за некорректных GPS-координат.")

    delta_m = abs(m_bottom - m_top)

    # 5. Расчет Z для обеих осей

    # Z_horizontal = log2( (ImageWidthPixels * 360) / (DeltaLon * 256) )
    z_horiz = math.log2((img_width_px * LON_RANGE) / (delta_lon * TILE_SIZE))

    # Z_vertical = log2( ImageHeightPixels / (DeltaM * 256) )
    z_vert = math.log2(img_height_px / (delta_m * TILE_SIZE))

    # 6. Выбор оптимального Z
    # Мы берем минимальное значение и округляем вниз (floor),
    # чтобы изображение гарантированно влезло в тайловую сетку без апскейла.
    optimal_z = math.floor(min(z_horiz, z_vert))

    print(f"Рассчитано Z_горизонтальное: {z_horiz:.2f}")
    print(f"Рассчитано Z_вертикальное: {z_vert:.2f}")
    print(f"Оптимальный Z для использования: {optimal_z}")

    return optimal_z


def get_tile_coords_by_gps(lat: float, lon: float, z: int) -> tuple[int, int]:
    """
    Преобразует GPS-координаты (широта, долгота) и уровень масштабирования Z
    в координаты тайла (X, Y) в системе Web Mercator (XYZ/OSM).

    Args:
        lat: Широта в десятичных градусах.
        lon: Долгота в десятичных градусах.
        z: Уровень масштабирования (zoom level).

    Returns:
        Кортеж (tile_x, tile_y) с целочисленными координатами тайла.
    """
    validate_gps_coords(lat, lon)

    # 1. Расчет N - общего количества тайлов на данном уровне Z
    n = 2**z

    # 2. Расчет X-координаты тайла
    # Формула: floor(N * ((lon + 180) / 360))
    x_tile = math.floor(n * ((lon + LON_OFFSET) / LON_RANGE))

    # 3. Расчет Y-координаты тайла
    # Сначала переводим широту в радианы
    lat_rad = math.radians(lat)

    # Используем формулу: floor(N * (1 - (ln(tan(lat_r) + sec(lat_r))) / PI) / 2)
    # math.log - это натуральный логарифм (ln)
    # 1/math.cos(lat_rad) - это sec(lat_rad)

    y_tile = math.floor(n * (1 - math.log(math.tan(lat_rad) + (1.0 / math.cos(lat_rad))) / math.pi) / 2.0)

    # Убедимся, что координаты находятся в пределах допустимого диапазона [0, N-1]
    x_tile = max(0, min(x_tile, n - 1))
    y_tile = max(0, min(y_tile, n - 1))

    return x_tile, y_tile


def get_tile_coords_dict(lat: float, lon: float, z: int) -> dict[str, int]:
    """
    Преобразует GPS-координаты (широта, долгота) и уровень масштабирования Z
    в словарь координат тайла {'x': tile_x, 'y': tile_y} в системе Web Mercator (XYZ/OSM).

    Args:
        lat: Широта в десятичных градусах.
        lon: Долгота в десятичных градусах.
        z: Уровень масштабирования (zoom level).

    Returns:
        Словарь с ключами 'x' и 'y' и целочисленными координатами тайла.
    """
    return dict(zip(("x", "y"), get_tile_coords_by_gps(lat, lon, z)))


def calc_tile_object(lat: float, lon: float, zoom: int) -> dict:
    """
    Создает объект тайла с координатами тайла и GPS-координатами.

    Args:
        lat: Широта в десятичных градусах.
        lon: Долгота в десятичных градусах.
        zoom: Уровень масштабирования (zoom level).

    Returns:
        Словарь с 'coords_tile' и 'coords_gps'.
    """
    coords_tile = get_tile_coords_dict(lat, lon, zoom)

    return {
        "coords_tile": coords_tile,
        "coords_gps": get_tile_4corners_gps(coords_tile["x"], coords_tile["y"], zoom),
    }


def get_tile_center_gps(x_tile: int, y_tile: int, z: int) -> tuple[float, float]:
    """
    Преобразует координаты тайла (X, Y, Z) в GPS-координаты (широта, долгота),
    соответствующие центру этого тайла в системе Web Mercator (XYZ/OSM).

    Args:
        x_tile: X-координата тайла (целое число).
        y_tile: Y-координата тайла (целое число).
        z: Уровень масштабирования (zoom level).

    Returns:
        Кортеж (latitude, longitude) с GPS-координатами центра тайла.
    """
    n = 2**z

    # x_tile + 0.5 дает нам центр тайла по X
    lon_deg = (x_tile + 0.5) / n * LON_RANGE - LON_OFFSET

    # 2. Широта (Latitude) требует обратных тригонометрических функций (обратный Меркатор):

    # y_pos_relative = (y + 0.5) / N
    # n_merc = PI * (1 - 2 * y_pos_relative)
    # lat = degrees(atan(sinh(n_merc)))

    # y_tile + 0.5 дает нам центр тайла по Y
    y_pos_relative = (y_tile + 0.5) / n

    # Промежуточное значение для обратной формулы
    merc_n = math.pi * (1.0 - 2.0 * y_pos_relative)

    # Обратное преобразование: atan(sinh(n_merc))
    lat_rad = math.atan(math.sinh(merc_n))

    # Переводим радианы обратно в градусы
    lat_deg = math.degrees(lat_rad)

    return lat_deg, lon_deg


def get_tile_lefttop_corner_gps(x_tile: int, y_tile: int, z: int) -> tuple[float, float]:
    """
    Преобразует координаты тайла (X, Y, Z) в GPS-координаты (широта, долгота),
    соответствующие левому верхнему углу этого тайла в системе Web Mercator (XYZ/OSM).

    Args:
        x_tile: X-координата тайла (целое число).
        y_tile: Y-координата тайла (целое число).
        z: Уровень масштабирования (zoom level).

    Returns:
        Кортеж (latitude, longitude) с GPS-координатами левого верхнего угла тайла
    """

    n = 2**z

    lon_deg = x_tile / n * LON_RANGE - LON_OFFSET

    y_pos_relative = y_tile / n
    merc_n = math.pi * (1.0 - 2.0 * y_pos_relative)
    lat_rad = math.atan(math.sinh(merc_n))
    lat_deg = math.degrees(lat_rad)

    return lat_deg, lon_deg


def get_tile_4corners_gps(x_tile: int, y_tile: int, z: int) -> tuple[float, float]:
    """
    Преобразует координаты тайла (X, Y, Z) в GPS-координаты (широта, долгота),
    соответствующие углам этого тайла в системе Web Mercator (XYZ/OSM).

    Args:
        x_tile: X-координата тайла (целое число).
        y_tile: Y-координата тайла (целое число).
        z: Уровень масштабирования (zoom level).

    Returns:
        Словарь кортежей (latitude, longitude) с GPS-координатами углов тайла
        Пример: {
            'top_left': (lat_tl, lon_tl),
            'top_right': (lat_tr, lon_tr),
            'bottom_right': (lat_br, lon_br),
            'bottom_left': (lat_bl, lon_bl)
        }
    """

    result = {
        "top_left": (get_tile_lefttop_corner_gps(x_tile, y_tile, z)),
        "top_right": (get_tile_lefttop_corner_gps(x_tile + 1, y_tile, z)),
        "bottom_right": (get_tile_lefttop_corner_gps(x_tile + 1, y_tile + 1, z)),
        "bottom_left": (get_tile_lefttop_corner_gps(x_tile, y_tile + 1, z)),
    }

    return result


def lat_lon_to_mercator_pos(lat_deg: float, lon_deg: float) -> tuple[float, float]:
    """
    Преобразует GPS-координаты в относительные координаты Меркатора (от 0 до 1).
    X=0 на -180 долг., X=1 на +180 долг.
    Y=0 на +85.05 шир., Y=1 на -85.05 шир.

    Args:
        lat_deg: Широта в градусах.
        lon_deg: Долгота в градусах.

    Returns:
        Кортеж (x_pos, y_pos) — относительные координаты в диапазоне [0, 1].
    """
    validate_gps_coords(lat_deg, lon_deg)

    # X-позиция
    x_pos = (lon_deg + LON_OFFSET) / LON_RANGE

    # Y-позиция
    lat_rad = math.radians(lat_deg)
    # Используем ту же формулу, что и раньше:
    merc_n = math.log(math.tan(lat_rad) + (1.0 / math.cos(lat_rad)))
    y_pos = (1.0 - merc_n / math.pi) / 2.0

    # Ограничиваем значения в пределах от 0 до 1
    x_pos = max(0.0, min(1.0, x_pos))
    y_pos = max(0.0, min(1.0, y_pos))

    return x_pos, y_pos


def solve_system(A, B):
    """
    Solves A * x = B using Gaussian elimination.
    A is list of lists, B is list, returns x list.
    """
    n = len(A)
    augmented = [A[i] + [B[i]] for i in range(n)]

    # Forward elimination
    for i in range(n):
        # Find pivot
        max_row = i
        for j in range(i + 1, n):
            if abs(augmented[j][i]) > abs(augmented[max_row][i]):
                max_row = j
        augmented[i], augmented[max_row] = augmented[max_row], augmented[i]

        # Make pivot 1
        pivot = augmented[i][i]
        if pivot == 0:
            raise ValueError("Singular matrix")
        for k in range(n + 1):
            augmented[i][k] /= pivot

        # Eliminate
        for j in range(n):
            if j != i:
                factor = augmented[j][i]
                for k in range(n + 1):
                    augmented[j][k] -= factor * augmented[i][k]

    return [row[n] for row in augmented]


def get_perspective_coeffs(src_points, dst_points):
    """
    Computes perspective transformation coefficients.
    src_points and dst_points are 4 (x,y) tuples each.
    Returns [a,b,c,d,e,f,g,h] for PIL's PERSPECTIVE.
    """
    A = []
    B = []
    for i in range(4):
        x, y = src_points[i]
        xp, yp = dst_points[i]
        A.append([x, y, 1, 0, 0, 0, -xp * x, -xp * y])
        B.append(xp)
        A.append([0, 0, 0, x, y, 1, -yp * x, -yp * y])
        B.append(yp)
    coeffs = solve_system(A, B)
    return coeffs


def find_pixel_coords(
    img_width_px: int,
    img_height_px: int,
    img_corners: dict,
    target_point: tuple[float, float],
) -> tuple[int, int] | None:
    """
    Вычисляет координаты пикселя на изображении, соответствующие заданной GPS-координате.
    Использует все 4 угла для точного определения границ.

    Args:
        img_width_px: Ширина изображения в пикселях.
        img_height_px: Высота изображения в пикселях.
        img_corners: Словарь с GPS-координатами углов изображения.
                     Пример: {
                         'top_left': (lat_tl, lon_tl),
                         'top_right': (lat_tr, lon_tr),
                         'bottom_right': (lat_br, lon_br),
                         'bottom_left': (lat_bl, lon_bl)
                     }
        target_point: Кортеж (target_lat, target_lon) искомой GPS-точки.

    Returns:
        Кортеж (pixel_x, pixel_y) или None, если точка выходит за границы изображения.
    """
    # 1. Извлекаем все 4 угла
    lat_tl, lon_tl = img_corners["top_left"]
    lat_tr, lon_tr = img_corners["top_right"]
    lat_br, lon_br = img_corners["bottom_right"]
    lat_bl, lon_bl = img_corners["bottom_left"]

    target_lat, target_lon = target_point

    # 2. Определяем границы по всем 4 углам
    # Для longitude: берём минимум и максимум из всех углов
    all_lons = [lon_tl, lon_tr, lon_br, lon_bl]
    lon_min = min(all_lons)
    lon_max = max(all_lons)

    # Для latitude: учитываем, что в Меркаторе Y инвертирован (север = 0, юг = 1)
    all_lats = [lat_tl, lat_tr, lat_br, lat_bl]
    lat_north = max(all_lats)  # северная границa
    lat_south = min(all_lats)  # южная границa

    # 3. Преобразуем в координаты Меркатора
    merc_left, merc_top = lat_lon_to_mercator_pos(lat_north, lon_min)
    merc_right, merc_bottom = lat_lon_to_mercator_pos(lat_south, lon_max)
    merc_x_target, merc_y_target = lat_lon_to_mercator_pos(target_lat, target_lon)

    # 4. Проверяем, находится ли точка в пределах границ изображения
    merc_x_min = min(merc_left, merc_right)
    merc_x_max = max(merc_left, merc_right)
    merc_y_min = min(merc_top, merc_bottom)
    merc_y_max = max(merc_top, merc_bottom)

    if not (merc_x_min <= merc_x_target <= merc_x_max and merc_y_min <= merc_y_target <= merc_y_max):
        print("Внимание: Целевая точка находится за пределами GPS-границ изображения.")

    # 5. Рассчитываем относительное положение (0.0–1.0)
    span_x = merc_x_max - merc_x_min
    span_y = merc_y_max - merc_y_min

    if span_x == 0 or span_y == 0:
        print("Ошибка: нулевой диапазон GPS-координат изображения.")
        return None

    pos_x_relative = (merc_x_target - merc_x_min) / span_x
    pos_y_relative = (merc_y_target - merc_y_min) / span_y

    # 6. Масштабируем в пиксельные координаты
    pixel_x = int(round(pos_x_relative * img_width_px))
    pixel_y = int(round(pos_y_relative * img_height_px))

    # Ограничиваем пределами изображения
    pixel_x = max(0, min(pixel_x, img_width_px - 1))
    pixel_y = max(0, min(pixel_y, img_height_px - 1))

    return pixel_x, pixel_y
