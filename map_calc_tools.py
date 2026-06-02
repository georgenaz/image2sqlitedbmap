#!/usr/bin/env python

"""Инструменты для вычисления zoom-уровней и работы с тайловой системой.

Вычисляет оптимальный zoom по GPS или UTM-координатам углов изображения,
а также min_zoom — минимальный уровень, на котором карта ещё занимает хотя бы 1 тайл.
"""

import logging
import math
from typing import Any

from pyproj import Transformer

TILE_SIZE = 256


def _lat_to_mercator_y(lat_deg: float) -> float:
    """Широта (градусы) → относительная Y-позиция в Web Mercator (0=Север, 1=Юг)."""
    lat_rad = math.radians(lat_deg)
    merc_n = math.log(math.tan(lat_rad) + (1.0 / math.cos(lat_rad)))
    return (1.0 - merc_n / math.pi) / 2.0


def calculate_optimal_z(img_width_px: int, img_height_px: int, coords: dict) -> int:
    """Рассчитывает оптимальный zoom для отображения пиксель-в-пиксель в Web Mercator.

    Принимает GPS-координаты (WGS84) углов изображения.
    Возвращает floor(min(z_horiz, z_vert)) — без растягивания.

    Args:
        img_width_px: Ширина изображения в пикселях.
        img_height_px: Высота изображения в пикселях.
        coords: GPS-координаты углов: {
            'top_left': (lat, lon), 'top_right': (lat, lon),
            'bottom_right': (lat, lon), 'bottom_left': (lat, lon)
        }

    Returns:
        Оптимальный zoom (целое число).
    """
    # Обрезаем до кратности TILE_SIZE
    w = (img_width_px // TILE_SIZE) * TILE_SIZE
    h = (img_height_px // TILE_SIZE) * TILE_SIZE
    if w == 0 or h == 0:
        raise ValueError("Размеры изображения слишком малы")

    delta_lon = abs(coords["top_right"][1] - coords["top_left"][1])
    if delta_lon > 180:
        delta_lon = 360 - delta_lon

    lat_top = coords["top_left"][0]
    lat_bottom = coords["bottom_left"][0]
    m_top = _lat_to_mercator_y(lat_top)
    m_bottom = _lat_to_mercator_y(lat_bottom)
    delta_m = abs(m_bottom - m_top)

    z_horiz = math.log2((w * 360) / (delta_lon * TILE_SIZE))
    z_vert = math.log2(h / (delta_m * TILE_SIZE))

    optimal_z = math.floor(min(z_horiz, z_vert))

    logging.info(f"Z_горизонтальный: {z_horiz:.2f}, Z_вертикальный: {z_vert:.2f}")
    logging.info(f"Оптимальный zoom (floor): {optimal_z}")

    return optimal_z


def calculate_min_zoom(optimal_zoom: int, coords: dict) -> int:
    """Вычисляет минимальный zoom для отображения карты.

    Использует эвристику: 9-10 уровней ниже оптимального, но не меньше 1.
    Это обеспечивает достаточный диапазон overview-тайлов для плавного масштабирования.

    Args:
        optimal_zoom: Оптимальный (максимальный) уровень масштабирования.
        coords: GPS-координаты углов (для совместимости).

    Returns:
        Минимальный zoom (целое число, >= 1).
    """
    return max(1, optimal_zoom - 9)


def _utm_corners_to_wgs84(corners: list[tuple[float, float]], utm_zone: int) -> list[tuple[float, float]]:
    """Конвертирует UTM координаты (easting, northing) в WGS84 (lat, lon).

    Args:
        corners: Список (easting, northing) координат.
        utm_zone: Номер UTM-зоны.

    Returns:
        Список (lat, lon) координат.
    """
    epsg_utm = f"EPSG:326{utm_zone:02d}"
    transformer = Transformer.from_crs(epsg_utm, "EPSG:4326", always_xy=True)

    result = []
    for easting, northing in corners:
        lon, lat = transformer.transform(easting, northing)
        result.append((lat, lon))

    return result


def _classify_gcp_corners(gcp_points: list, width: int, height: int) -> dict:
    """Классифицирует GCP-точки по углам изображения на основе пиксельных координат.

    Args:
        gcp_points: Список GCPPoint (не менее 4).
        width: Ширина изображения.
        height: Высота изображения.

    Returns:
        Словарь {top_left, top_right, bottom_right, bottom_left} → GCPPoint.
    """
    cx, cy = width / 2, height / 2
    corners: dict[str, Any] = {}
    for gcp in gcp_points:
        if gcp.pixel_x <= cx and gcp.pixel_y <= cy:
            corners["top_left"] = gcp
        elif gcp.pixel_x > cx and gcp.pixel_y <= cy:
            corners["top_right"] = gcp
        elif gcp.pixel_x > cx and gcp.pixel_y > cy:
            corners["bottom_right"] = gcp
        else:
            corners["bottom_left"] = gcp
    return corners


def gcp_to_gps_corners(map_data) -> dict:
    """Преобразует GCP-точки из .map-файла в GPS-координаты углов (WGS84).

    Поддерживает два формата GCP:
    - UTM grid: конвертирует easting/northing → WGS84 через pyproj
    - Geographic deg: конвертирует lat/lon из source datum → WGS84 через pyproj

    Args:
        map_data: Объект MapFileData из map_parser.

    Returns:
        Словарь с GPS-координатами углов (WGS84).
    """
    gcp_points = map_data.gcp_points
    if not gcp_points:
        raise ValueError("Нет GCP-точек")

    first = gcp_points[0]
    width = map_data.image_width
    height = map_data.image_height

    if first.is_geographic:
        # Geographic GCP: lat/lon в исходном datum → конвертация в WGS84
        source_crs = map_data.epsg_code
        transformer = Transformer.from_crs(source_crs, "EPSG:4326", always_xy=True)

        classified = _classify_gcp_corners(gcp_points, width, height)
        if len(classified) < 4:
            raise ValueError(f"Не удалось классифицировать углы: найдено {len(classified)}/4")

        result = {}
        for key, gcp in classified.items():
            lon, lat = transformer.transform(gcp.lon, gcp.lat)
            result[key] = (lat, lon)
        return result
    else:
        # UTM grid GCP: easting/northing → WGS84
        utm_zone = first.utm_zone
        utm_corners = [(gcp.easting, gcp.northing) for gcp in gcp_points]
        gps_corners = _utm_corners_to_wgs84(utm_corners, utm_zone)

        # Классификация по пиксельным координатам для надёжности
        classified = _classify_gcp_corners(gcp_points, width, height)
        if len(classified) < 4:
            # Fallback на фиксированный порядок TL, TR, BR, BL
            if len(gps_corners) >= 4:
                return {
                    "top_left": gps_corners[0],
                    "top_right": gps_corners[1],
                    "bottom_right": gps_corners[2],
                    "bottom_left": gps_corners[3],
                }
            raise ValueError("Недостаточно GCP-точек для расчёта углов")

        # Маппим: pixel corner → gps coordinate по индексу GCP
        gcp_idx_map = {id(gcp): i for i, gcp in enumerate(gcp_points)}
        result = {}
        for key, gcp in classified.items():
            idx = gcp_idx_map[id(gcp)]
            result[key] = gps_corners[idx]
        return result
