#!/usr/bin/env python

"""Парсер OziExplorer .map-файлов.

Извлекает: имя изображения, UTM-координаты углов (GCP), зону UTM,
GPS-координаты углов (MMPLL), размеры изображения (IWH).
"""

import logging
import os
import re
from dataclasses import dataclass, field


@dataclass
class GCPPoint:
    """Ground Control Point — привязка пикселя к UTM-координатам."""

    pixel_x: int
    pixel_y: int
    utm_zone: int
    easting: float
    northing: float


@dataclass
class MapFileData:
    """Результат парсинга .map-файла."""

    image_filename: str = ""
    image_filepath: str = ""
    utm_zone: int = 0
    epsg_code: str = ""
    gcp_points: list[GCPPoint] = field(default_factory=list)
    gps_corners: list[tuple[float, float]] = field(default_factory=list)
    image_width: int = 0
    image_height: int = 0
    datum: str = ""


def _parse_point_line(line: str) -> GCPPoint | None:
    """Парсит строку Point01,xy,0,0,...,grid,37,519022.5,6193504.8,N."""
    # Формат: Point##,xy,px,py,in,deg,...,grid,zone,easting,northing,N
    parts = line.split(",")
    if len(parts) < 16:
        return None

    pixel_x_str = parts[2].strip()
    pixel_y_str = parts[3].strip()
    grid_marker = parts[12].strip()
    zone_str = parts[13].strip()
    easting_str = parts[14].strip()
    northing_str = parts[15].strip()

    if grid_marker != "grid" or not pixel_x_str or not pixel_y_str:
        return None

    try:
        return GCPPoint(
            pixel_x=int(pixel_x_str),
            pixel_y=int(pixel_y_str),
            utm_zone=int(zone_str),
            easting=float(easting_str),
            northing=float(northing_str),
        )
    except (ValueError, IndexError):
        return None


def _parse_mmpll_line(line: str) -> tuple[float, float] | None:
    """Парсит строку MMPLL,1,39.304121,55.886642."""
    parts = line.split(",")
    if len(parts) < 4:
        return None
    try:
        # MMPLL,index,lon,lat  — внимание: в .map-файле сначала lon, потом lat
        lon = float(parts[2].strip())
        lat = float(parts[3].strip())
        return (lat, lon)
    except (ValueError, IndexError):
        return None


def _parse_iwh_line(line: str) -> tuple[int, int] | None:
    """Парсит строку IWH,Map Image Width/Height,8583,8583."""
    parts = line.split(",")
    if len(parts) < 4:
        return None
    try:
        width = int(parts[2].strip())
        height = int(parts[3].strip())
        return (width, height)
    except (ValueError, IndexError):
        return None


def parse_map_file(map_filepath: str) -> MapFileData:
    """Парсит OziExplorer .map-файл и возвращает структурированные данные.

    Args:
        map_filepath: Путь к .map-файлу.

    Returns:
        Объект MapFileData с извлечёнными данными.

    Raises:
        FileNotFoundError: Если .map-файл не найден.
        ValueError: Если файл имеет некорректный формат или缺少 обязательные данные.
    """
    if not os.path.isfile(map_filepath):
        raise FileNotFoundError(f"Файл карты не найден: {map_filepath}")

    map_dir = os.path.dirname(os.path.abspath(map_filepath))
    data = MapFileData()

    with open(map_filepath, encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    if not lines:
        raise ValueError("Пустой .map-файл")

    # Строка 1: заголовок OziExplorer
    header = lines[0].strip()
    if "OziExplorer Map Data File" not in header:
        raise ValueError(f"Некорректный формат .map-файла: {header}")

    # Строка 2: имя файла изображения
    data.image_filename = lines[1].strip() if len(lines) > 1 else ""
    data.image_filepath = os.path.join(map_dir, data.image_filename)

    # Строка 4: Datum (WGS 84)
    if len(lines) > 3:
        datum_line = lines[3].strip()
        if datum_line.startswith("WGS"):
            data.datum = "WGS 84"

    for line in lines:
        line_stripped = line.strip()

        # Point## — GCP точки
        if re.match(r"^Point\d+,xy,", line_stripped):
            gcp = _parse_point_line(line_stripped)
            if gcp is not None:
                data.gcp_points.append(gcp)

        # MMPLL — GPS-координаты углов
        elif line_stripped.startswith("MMPLL,"):
            corner = _parse_mmpll_line(line_stripped)
            if corner is not None:
                data.gps_corners.append(corner)

        # IWH — размеры изображения
        elif line_stripped.startswith("IWH,"):
            dims = _parse_iwh_line(line_stripped)
            if dims is not None:
                data.image_width, data.image_height = dims

    # Определяем UTM-зону и EPSG из первой GCP-точки
    if data.gcp_points:
        data.utm_zone = data.gcp_points[0].utm_zone
        # Определяем полушарие по northing
        if data.gcp_points[0].northing >= 0:
            data.epsg_code = f"EPSG:326{data.utm_zone:02d}"
        else:
            data.epsg_code = f"EPSG:327{data.utm_zone:02d}"

    # Валидация
    if not data.image_filename:
        raise ValueError("Не удалось определить имя файла изображения в .map-файле")
    if len(data.gcp_points) < 3:
        raise ValueError(f"Нужно минимум 3 GCP-точки, найдено: {len(data.gcp_points)}")
    if not data.gps_corners:
        raise ValueError("Не найдены GPS-координаты углов (MMPLL)")
    if data.image_width == 0 or data.image_height == 0:
        raise ValueError("Не удалось определить размер изображения (IWH)")

    logging.info(
        f"Map-файл: изображение={data.image_filename}, "
        f"размер={data.image_width}x{data.image_height}, "
        f"EPSG={data.epsg_code}, "
        f"GCP-точек={len(data.gcp_points)}, "
        f"GPS-углов={len(data.gps_corners)}"
    )

    return data


def validate_image(map_data: MapFileData) -> None:
    """Проверяет, что файл изображения существует и его размер совпадает с .map-файлом.

    Args:
        map_data: Данные из .map-файла.

    Raises:
        FileNotFoundError: Если файл изображения не найден.
        ValueError: Если размер изображения не совпадает.
    """
    from PIL import Image

    if not os.path.isfile(map_data.image_filepath):
        raise FileNotFoundError(f"Файл изображения не найден: {map_data.image_filepath}")

    with Image.open(map_data.image_filepath) as img:
        real_w, real_h = img.size

    # IWH может отличаться на 1 пиксель (8583 в .map vs 8582 реальный размер PNG)
    diff_w = abs(real_w - map_data.image_width)
    diff_h = abs(real_h - map_data.image_height)

    if diff_w > 1 or diff_h > 1:
        raise ValueError(
            f"Размер изображения ({real_w}x{real_h}) не совпадает "
            f"с указанным в .map-файле ({map_data.image_width}x{map_data.image_height})"
        )

    logging.info(f"Изображение проверено: {real_w}x{real_h}")
