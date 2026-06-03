#!/usr/bin/env python

"""Парсер OziExplorer .map-файлов.

Извлекает: имя изображения, UTM-координаты углов (GCP), зону UTM,
GPS-координаты углов (MMPLL), размеры изображения (IWH).
"""

import logging
import os
import re
from dataclasses import dataclass, field


# Маппинг: имя datum (из .map-файла) → EPSG-код географической СК
DATUM_TO_EPSG: dict[str, str] = {
    "WGS 84": "EPSG:4326",
    "WGS84": "EPSG:4326",
    "Pulkovo 1942": "EPSG:4284",
    "Pulkovo 1942 (2)": "EPSG:4284",
    "Pulkovo 1995": "EPSG:4200",
    "Pulkovo 1995 (2)": "EPSG:4200",
}


@dataclass
class GCPPoint:
    """Ground Control Point — привязка пикселя к координатам."""

    pixel_x: int
    pixel_y: int
    utm_zone: int = 0
    easting: float = 0.0
    northing: float = 0.0
    lat: float = 0.0
    lon: float = 0.0
    is_geographic: bool = False


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
    projection: str = ""
    projection_setup: list[float] = field(default_factory=list)
    crs_type: str = "utm_grid"  # "utm_grid" | "geographic_deg"


def _parse_point_line(line: str) -> GCPPoint | None:
    """Парсит строку Point##,xy,... — поддерживает UTM grid и geographic deg форматы.

    UTM grid:  Point01,xy,0,0,in,deg,,,N,,,E,grid,37,519022.5,6193504.8,N
    Deg:       Point01,xy,10,5876,in,deg,55,39.999694,N,37,29.999973,E,grid,,,N
    """
    parts = line.split(",")
    if len(parts) < 16:
        return None

    pixel_x_str = parts[2].strip()
    pixel_y_str = parts[3].strip()

    if not pixel_x_str or not pixel_y_str:
        return None

    try:
        pixel_x = int(pixel_x_str)
        pixel_y = int(pixel_y_str)
    except ValueError:
        return None

    # Проверяем, что позиция 12 содержит "grid" (или пусто для некоторых форматов)
    grid_marker = parts[12].strip()
    if grid_marker and grid_marker != "grid":
        return None

    # Пытаемся распарсить UTM grid (zone + easting + northing заполнены)
    zone_str = parts[13].strip()
    easting_str = parts[14].strip()
    northing_str = parts[15].strip()

    if zone_str and easting_str and northing_str:
        try:
            return GCPPoint(
                pixel_x=pixel_x,
                pixel_y=pixel_y,
                utm_zone=int(zone_str),
                easting=float(easting_str),
                northing=float(northing_str),
                is_geographic=False,
            )
        except (ValueError, IndexError):
            pass

    # Пытаемся распарсить geographic deg (градусы + десятичные минуты)
    lat_deg_str = parts[6].strip()
    lat_min_str = parts[7].strip()
    lat_ns = parts[8].strip().upper()
    lon_deg_str = parts[9].strip()
    lon_min_str = parts[10].strip()
    lon_ew = parts[11].strip().upper()

    if lat_deg_str and lat_min_str and lon_deg_str and lon_min_str:
        try:
            lat = int(lat_deg_str) + float(lat_min_str) / 60.0
            if lat_ns == "S":
                lat = -lat
            lon = int(lon_deg_str) + float(lon_min_str) / 60.0
            if lon_ew == "W":
                lon = -lon
            return GCPPoint(
                pixel_x=pixel_x,
                pixel_y=pixel_y,
                lat=lat,
                lon=lon,
                is_geographic=True,
            )
        except (ValueError, IndexError):
            pass

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


def _parse_mmpxy_line(line: str) -> tuple[int, int] | None:
    """Парсит строку MMPXY,index,x,y — возвращает (x, y)."""
    parts = line.split(",")
    if len(parts) < 4:
        return None
    try:
        x = int(float(parts[2].strip()))
        y = int(float(parts[3].strip()))
        return (x, y)
    except (ValueError, IndexError):
        return None


def _read_image_dimensions(image_path: str) -> tuple[int, int] | None:
    """Читает размеры изображения через PIL."""
    try:
        from PIL import Image
        with Image.open(image_path) as img:
            return img.size
    except Exception:
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

    # Строка 2 (index 1): имя файла изображения
    data.image_filename = lines[1].strip() if len(lines) > 1 else ""
    data.image_filepath = os.path.join(map_dir, data.image_filename)

    mmpxy_coords: list[tuple[int, int]] = []

    for line in lines:
        line_stripped = line.strip()

        # Point## — GCP точки
        if re.match(r"^Point\d+,xy,", line_stripped):
            gcp = _parse_point_line(line_stripped)
            if gcp is not None:
                data.gcp_points.append(gcp)

        # Projection Setup — параметры проекции
        elif line_stripped.startswith("Projection Setup,"):
            setup_parts = line_stripped.split(",")
            try:
                data.projection_setup = [float(p.strip()) for p in setup_parts[1:] if p.strip()]
            except ValueError:
                pass

        # Map Projection — имя проекции
        elif line_stripped.startswith("Map Projection,"):
            proj_parts = line_stripped.split(",")
            if len(proj_parts) > 1:
                data.projection = proj_parts[1].strip()

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

        # MMPXY — координаты углов карты в пикселях
        elif line_stripped.startswith("MMPXY,"):
            mpx = _parse_mmpxy_line(line_stripped)
            if mpx is not None:
                mmpxy_coords.append(mpx)

    # Если IWH отсутствует — извлекаем размеры из MMPXY (max X/Y)
    if (data.image_width == 0 or data.image_height == 0) and mmpxy_coords:
        max_x = max(x for x, y in mmpxy_coords)
        max_y = max(y for x, y in mmpxy_coords)
        if max_x > 0 and max_y > 0:
            data.image_width = max_x
            data.image_height = max_y
            logging.info(f"Размеры изображения из MMPXY: {max_x}x{max_y}")

    # Если всё ещё нет — читаем из самого файла изображения
    if (data.image_width == 0 or data.image_height == 0) and data.image_filepath:
        img_dims = _read_image_dimensions(data.image_filepath)
        if img_dims is not None:
            data.image_width, data.image_height = img_dims
            logging.info(f"Размеры изображения из файла: {img_dims[0]}x{img_dims[1]}")

    # Datum: строка 5 (index 4), формат "Datum Name,..."
    # Примеры: "WGS 84,,0,0,WGS 84" или "Pulkovo 1942 (2),WGS 84,0,0,WGS 84"
    if len(lines) > 4:
        datum_parts = lines[4].strip().split(",")
        if datum_parts:
            datum_name = datum_parts[0].strip()
            # Проверяем, что строка действительно содержит datum (не "Reserved" и не пустое)
            if datum_name and not datum_name.startswith("Reserved"):
                data.datum = datum_name

    # Определяем тип CRS и EPSG
    if data.gcp_points:
        first_gcp = data.gcp_points[0]
        if first_gcp.is_geographic:
            data.crs_type = "geographic_deg"
            # EPSG из datum
            data.epsg_code = DATUM_TO_EPSG.get(data.datum, "")
        else:
            data.crs_type = "utm_grid"
            data.utm_zone = first_gcp.utm_zone
            if first_gcp.northing >= 0:
                data.epsg_code = f"EPSG:326{data.utm_zone:02d}"
            else:
                data.epsg_code = f"EPSG:327{data.utm_zone:02d}"

    # Проверяем, что все GCP используют один формат
    if data.gcp_points:
        first_geo = data.gcp_points[0].is_geographic
        if not all(gcp.is_geographic == first_geo for gcp in data.gcp_points):
            raise ValueError("Смешанные форматы GCP (UTM grid + geographic deg) в одном файле")

    # Валидация
    if not data.image_filename:
        raise ValueError("Не удалось определить имя файла изображения в .map-файле")
    if len(data.gcp_points) < 3:
        raise ValueError(f"Нужно минимум 3 GCP-точки, найдено: {len(data.gcp_points)}")
    if not data.gps_corners:
        logging.warning("Не найдены GPS-координаты углов (MMPLL) — будет использован расчёт из GCP")
    if data.image_width == 0 or data.image_height == 0:
        raise ValueError("Не удалось определить размер изображения (IWH/MMPXY/PIL)")
    if not data.epsg_code:
        raise ValueError(f"Не удалось определить EPSG для datum '{data.datum}'. "
                         f"Поддерживаемые: {', '.join(DATUM_TO_EPSG.keys())}")

    logging.info(
        f"Map-файл: изображение={data.image_filename}, "
        f"размер={data.image_width}x{data.image_height}, "
        f"datum={data.datum}, projection={data.projection}, "
        f"CRS type={data.crs_type}, EPSG={data.epsg_code}, "
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
