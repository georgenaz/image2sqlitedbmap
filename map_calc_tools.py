#!/usr/bin/env python

import math
import logging

# Константа размера тайла в пикселях
TILE_SIZE = 256

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def calculate_optimal_z(img_width_px: int, img_height_px: int, coords: dict) -> int:
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
    
    # 1. Обработка обрезки до ближайшего значения, кратного 256
    original_width = img_width_px
    original_height = img_height_px
    
    img_width_px = (img_width_px // TILE_SIZE) * TILE_SIZE
    img_height_px = (img_height_px // TILE_SIZE) * TILE_SIZE
    
    if img_width_px != original_width or img_height_px != original_height:
        logging.info(f"Изображение обрезано для кратности 256: {original_width}x{original_height}px -> {img_width_px}x{img_height_px}px")

    if img_width_px == 0 or img_height_px == 0:
        raise ValueError("Размеры изображения после обрезки слишком малы для расчета Z.")

    # 2. Извлечение координат для расчета охвата
    # Для расчета охвата по горизонтали берем долготу левого и правого края
    lon_left = coords['top_left'][1]
    lon_right = coords['top_right'][1]
    # Для расчета охвата по вертикали берем широту верхнего и нижнего края
    lat_top = coords['top_left'][0]
    lat_bottom = coords['bottom_left'][0]

    # 3. Расчет охвата по горизонтали (долгота в градусах)
    delta_lon = abs(lon_right - lon_left)
    # Убеждаемся, что разница не превышает 360 градусов (если карта пересекает 180 меридиан)
    if delta_lon > 180:
        delta_lon = 360 - delta_lon

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
            logging.error(f"Ошибка вычисления Меркатора для широты {lat_deg}: {e}")
            return None
            
    m_top = lat_to_mercator_pos(lat_top)
    m_bottom = lat_to_mercator_pos(lat_bottom)
    
    if m_top is None or m_bottom is None:
        raise ValueError("Невозможно рассчитать Z из-за некорректных GPS-координат.")

    delta_m = abs(m_bottom - m_top)

    # 5. Расчет Z для обеих осей
    
    # Z_horizontal = log2( (ImageWidthPixels * 360) / (DeltaLon * 256) )
    z_horiz = math.log2((img_width_px * 360) / (delta_lon * TILE_SIZE))
    
    # Z_vertical = log2( ImageHeightPixels / (DeltaM * 256) )
    z_vert = math.log2(img_height_px / (delta_m * TILE_SIZE))

    # 6. Выбор оптимального Z
    # Мы берем минимальное значение и округляем вниз (floor), 
    # чтобы изображение гарантированно влезло в тайловую сетку без апскейла.
    optimal_z = math.floor(min(z_horiz, z_vert))
    
    logging.info(f"Рассчитано Z_горизонтальное: {z_horiz:.2f}")
    logging.info(f"Рассчитано Z_вертикальное: {z_vert:.2f}")
    logging.info(f"Оптимальный Z для использования: {optimal_z}")

    return optimal_z



def get_tile_coords(lat: float, lon: float, z: int) -> tuple[int, int]:
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
    
    # 1. Расчет N - общего количества тайлов на данном уровне Z
    n = 2 ** z
    
    # 2. Расчет X-координаты тайла
    # Формула: floor(N * ((lon + 180) / 360))
    x_tile = math.floor(n * ((lon + 180.0) / 360.0))
    
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
    
    # 1. Сначала найдем границы верхнего левого угла (0,0) тайла в относительных координатах.
    # Чтобы найти центр, мы используем координаты верхнего левого угла тайла + 0.5 (полтайла)
    
    # Долгота (Longitude) рассчитывается проще:
    # x_pos_relative = (x + 0.5) / N
    # lon = x_pos_relative * 360 - 180
    
    n = 2 ** z
    
    # x_tile + 0.5 дает нам центр тайла по X
    lon_deg = (x_tile + 0.5) / n * 360.0 - 180.0
    
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


def lat_lon_to_mercator_pos(lat_deg, lon_deg):
    """
    Преобразует GPS-координаты в относительные координаты Меркатора (от 0 до 1).
    X=0 на -180 долг., X=1 на +180 долг.
    Y=0 на +85.05 шир., Y=1 на -85.05 шир.
    """
    # X-позиция
    x_pos = (lon_deg + 180.0) / 360.0
    
    # Y-позиция
    lat_rad = math.radians(lat_deg)
    # Используем ту же формулу, что и раньше:
    merc_n = math.log(math.tan(lat_rad) + (1.0 / math.cos(lat_rad)))
    y_pos = (1.0 - merc_n / math.pi) / 2.0
    
    # Ограничиваем значения в пределах от 0 до 1
    x_pos = max(0.0, min(1.0, x_pos))
    y_pos = max(0.0, min(1.0, y_pos))
    
    return x_pos, y_pos


def lat_lon_to_mercator_pos(lat_deg, lon_deg):
    """
    Преобразует GPS-координаты в относительные координаты Меркатора (от 0 до 1).
    X=0 на -180 долг., X=1 на +180 долг.
    Y=0 на +85.05 шир., Y=1 на -85.05 шир.
    """
    # X-позиция
    x_pos = (lon_deg + 180.0) / 360.0
    
    # Y-позиция
    lat_rad = math.radians(lat_deg)
    # Используем ту же формулу, что и раньше:
    merc_n = math.log(math.tan(lat_rad) + (1.0 / math.cos(lat_rad)))
    y_pos = (1.0 - merc_n / math.pi) / 2.0
    
    # Ограничиваем значения в пределах от 0 до 1
    x_pos = max(0.0, min(1.0, x_pos))
    y_pos = max(0.0, min(1.0, y_pos))
    
    return x_pos, y_pos

def find_pixel_coords(img_width_px: int, img_height_px: int, img_corners: dict, target_point: tuple[float, float]) -> tuple[int, int] | None:
    """
    Вычисляет координаты пикселя на изображении, соответствующие заданной GPS-координате.

    Args:
        img_width_px: Ширина изображения в пикселях.
        img_height_px: Высота изображения в пикселях.
        img_corners: Словарь с GPS-координатами углов изображения.
                     Пример: {
                         'top_left': (lat_tl, lon_tl), 
                         'bottom_right': (lat_br, lon_br), 
                         ...}
        target_point: Кортеж (target_lat, target_lon) искомой GPS-точки.

    Returns:
        Кортеж (pixel_x, pixel_y) или None, если точка выходит за границы изображения.
    """
    
    # 1. Получаем GPS-координаты границ из словаря углов (предполагаем прямоугольность)
    lat_top = img_corners['top_left'][0]
    lon_left = img_corners['top_left'][1]
    lat_bottom = img_corners['bottom_right'][0]
    lon_right = img_corners['bottom_right'][1]
    
    target_lat, target_lon = target_point

    # 2. Преобразуем границы изображения в относительные координаты Меркатора (0 до 1)
    merc_x_left, merc_y_top = lat_lon_to_mercator_pos(lat_top, lon_left)
    merc_x_right, merc_y_bottom = lat_lon_to_mercator_pos(lat_bottom, lon_right)
    
    # 3. Преобразуем целевую точку в относительные координаты Меркатора
    merc_x_target, merc_y_target = lat_lon_to_mercator_pos(target_lat, target_lon)
    
    # 4. Проверяем, находится ли точка в пределах границ изображения по Меркатору
    if not (merc_x_left <= merc_x_target <= merc_x_right and 
            merc_y_top <= merc_y_target <= merc_y_bottom):
        print("Внимание: Целевая точка находится за пределами GPS-границ изображения.")
        # Можно вернуть None или координаты ближайшего края
        # return None

    # 5. Рассчитываем пропорциональное положение точки внутри изображения
    
    # Относительное положение по X внутри изображения (от 0.0 до 1.0)
    # Используем min/max на случай, если пользователь ввел некорректные углы (например, поменял left/right)
    span_x = abs(merc_x_right - merc_x_left)
    pos_x_relative_to_image = (merc_x_target - min(merc_x_left, merc_x_right)) / span_x
    
    # Относительное положение по Y внутри изображения (от 0.0 до 1.0)
    span_y = abs(merc_y_bottom - merc_y_top)
    pos_y_relative_to_image = (merc_y_target - min(merc_y_top, merc_y_bottom)) / span_y

    # 6. Масштабируем относительные позиции в пиксельные координаты
    # Округляем до целых пикселей
    pixel_x = int(round(pos_x_relative_to_image * img_width_px))
    pixel_y = int(round(pos_y_relative_to_image * img_height_px))
    
    # Убеждаемся, что пиксели находятся внутри изображения
    pixel_x = max(0, min(pixel_x, img_width_px - 1))
    pixel_y = max(0, min(pixel_y, img_height_px - 1))

    return pixel_x, pixel_y

