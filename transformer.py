#!/usr/bin/env python

"""Модуль трансформации изображения из UTM в Web Mercator (EPSG:3857).

Использует GDAL (python bindings) для:
1. Создания VRT-файла с GCP-точками
2. Warping (перепроецирование) в EPSG:3857
"""

import logging
import os
import tempfile

from osgeo import gdal, osr

from map_parser import MapFileData

gdal.UseExceptions()


def create_vrt_with_gcp(map_data: MapFileData, vrt_path: str) -> str:
    """Создаёт VRT-файл с GCP-точками из данных .map-файла.

    Args:
        map_data: Данные из .map-файла.
        vrt_path: Путь для создания VRT-файла.

    Returns:
        Путь к созданному VRT-файлу.
    """
    image_path = map_data.image_filepath

    # Получаем WKT для пространственной системы привязки
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(int(map_data.epsg_code.split(":")[1]))
    srs_wkt = srs.ExportToWkt()

    # Формируем список GCP-точек
    gcps = []
    for gcp in map_data.gcp_points:
        g = gdal.GCP(
            gcp.easting,      # X (easting)
            gcp.northing,     # Y (northing)
            0.0,              # Z
            gcp.pixel_x,     # pixel
            gcp.pixel_y,     # line
        )
        gcps.append(g)

    # Создаём VRT с expand rgba
    vrt_options = gdal.TranslateOptions(
        format="VRT",
        rgbExpand="rgba",
    )
    vrt_ds = gdal.Translate(vrt_path, image_path, options=vrt_options)

    if vrt_ds is None:
        raise RuntimeError(f"Не удалось создать VRT: {vrt_path}")

    # Устанавливаем GCP с WKT пространственной привязкой
    vrt_ds.SetGCPs(gcps, srs_wkt)
    vrt_ds.FlushCache()
    vrt_ds = None

    logging.info(f"VRT создан: {vrt_path} с {len(gcps)} GCP-точками")
    return vrt_path


def warp_to_mercator(vrt_path: str, output_tif: str) -> str:
    """Выполняет warp (перепроецирование) из исходной СК в Web Mercator.

    Args:
        vrt_path: Путь к VRT-файлу с GCP.
        output_tif: Путь к выходному TIF-файлу.

    Returns:
        Путь к созданному TIF-файлу.
    """
    warp_options = gdal.WarpOptions(
        format="GTiff",
        dstSRS="EPSG:3857",
        resampleAlg="bilinear",
        dstAlpha=True,
        creationOptions=["COMPRESS=LZW", "TILED=YES", "BIGTIFF=IF_NEEDED"],
    )

    warped_ds = gdal.Warp(output_tif, vrt_path, options=warp_options)

    if warped_ds is None:
        raise RuntimeError(f"gdalwarp не удался: {vrt_path} -> {output_tif}")

    warped_ds.FlushCache()
    warped_ds = None

    logging.info(f"Warp завершён: {output_tif}")
    return output_tif


def transform_image(map_data: MapFileData, work_dir: str | None = None) -> str:
    """Полная трансформация: .map → VRT → Mercator TIF.

    Args:
        map_data: Данные из .map-файла.
        work_dir: Директория для временных файлов (по умолчанию — рядом с изображением).

    Returns:
        Путь к Mercator TIF-файлу.
    """
    if work_dir is None:
        work_dir = os.path.dirname(map_data.image_filepath)

    os.makedirs(work_dir, exist_ok=True)

    vrt_path = os.path.join(work_dir, "temp.vrt")
    tif_path = os.path.join(work_dir, "master_mercator.tif")

    # Удаляем старые файлы если есть
    for f in (vrt_path, tif_path):
        if os.path.exists(f):
            os.remove(f)

    create_vrt_with_gcp(map_data, vrt_path)
    warp_to_mercator(vrt_path, tif_path)

    return tif_path
