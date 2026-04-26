#!/usr/bin/env python

"""Модуль работы с SQLite для формирования OsmAnd sqlitedb из MBTiles.

Конвертирует MBTiles (стандарт TMS) в формат OsmAnd sqlitedb:
- Переименовывает таблицы MBTiles в структуру OsmAnd
- Заполняет таблицу info (maxzoom, minzoom, tilenumbering)
- Очищает служебные таблицы MBTiles
- Выполняет VACUUM для оптимизации размера
"""

import logging
import os
import sqlite3


def get_database_filename(image_file: str, output_dir: str | None = None) -> str:
    """Генерирует уникальное имя файла базы данных на основе имени файла изображения.

    Args:
        image_file: Имя или путь к файлу изображения.
        output_dir: Директория для файла (по умолчанию — текущая).

    Returns:
        Полный путь к файлу базы данных.
    """
    base_name = os.path.splitext(os.path.basename(image_file))[0]
    if output_dir is None:
        output_dir = os.path.dirname(os.path.abspath(image_file))

    db_name = f"{base_name}.sqlitedb"
    db_path = os.path.join(output_dir, db_name)
    version = 1
    while os.path.exists(db_path):
        db_name = f"{base_name}-v{version}.sqlitedb"
        db_path = os.path.join(output_dir, db_name)
        version += 1
    return db_path


def mbtiles_to_osmand_sqlitedb(mbtiles_path: str, output_path: str, max_zoom: int, min_zoom: int) -> str:
    """Конвертирует MBTiles в OsmAnd sqlitedb формат.

    Выполняет:
    1. Копирование MBTiles файла
    2. Переименование таблицы tiles → tiles_src
    3. Создание таблиц info и tiles в формате OsmAnd
    4. Перенос данных из tiles_src в tiles
    5. Удаление служебных таблиц MBTiles
    6. VACUUM для оптимизации

    Args:
        mbtiles_path: Путь к MBTiles-файлу.
        output_path: Путь к выходному sqlitedb-файлу.
        max_zoom: Максимальный уровень масштабирования (на 1 больше оптимального).
        min_zoom: Минимальный уровень масштабирования.

    Returns:
        Путь к созданному sqlitedb-файлу.
    """
    # Копируем MBTiles в выходной файл
    if os.path.abspath(mbtiles_path) != os.path.abspath(output_path):
        import shutil
        shutil.copy2(mbtiles_path, output_path)

    conn = sqlite3.connect(output_path)
    cursor = conn.cursor()

    try:
        # 1. Переименовываем исходную таблицу MBTiles
        cursor.execute("ALTER TABLE tiles RENAME TO tiles_src")

        # 2. Создаём структуру OsmAnd
        cursor.execute("""
            CREATE TABLE info (
                maxzoom INTEGER,
                minzoom INTEGER,
                tilenumbering TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE tiles (
                x INTEGER,
                y INTEGER,
                z INTEGER,
                s INTEGER,
                image BLOB,
                PRIMARY KEY (x, y, z, s)
            )
        """)

        # 3. Заполняем метаданные
        # tilenumbering='0' — Google/OSM нумерация (Y от верха)
        cursor.execute(
            "INSERT INTO info (maxzoom, minzoom, tilenumbering) VALUES (?, ?, '0')",
            (max_zoom, min_zoom),
        )

        # 4. Переносим данные из MBTiles
        # MBTiles использует TMS нумерацию (Y от низа),
        # но в данном случае gdal2tiles генерирует XYZ (Google) нумерацию
        # и mbutil упаковывает как есть, поэтому инверсия Y не нужна
        cursor.execute("""
            INSERT INTO tiles (z, x, y, s, image)
            SELECT zoom_level, tile_column, tile_row, 0, tile_data
            FROM tiles_src
        """)

        # 5. Очистка служебных таблиц MBTiles
        cursor.execute("DROP TABLE tiles_src")
        cursor.execute("DROP TABLE IF EXISTS metadata")
        cursor.execute("DROP TABLE IF EXISTS grids")
        cursor.execute("DROP TABLE IF EXISTS grid_data")
        cursor.execute("DROP TABLE IF EXISTS sqlite_stat1")

        conn.commit()

        # Статистика
        cursor.execute("SELECT z, COUNT(*) FROM tiles GROUP BY z ORDER BY z")
        tile_stats = cursor.fetchall()
        total_tiles = sum(count for _, count in tile_stats)

        logging.info(f"OsmAnd sqlitedb создан: {output_path}")
        logging.info(f"  max_zoom={max_zoom}, min_zoom={min_zoom}")
        logging.info(f"  Всего тайлов: {total_tiles}")
        for z, count in tile_stats:
            logging.info(f"  z={z}: {count} тайлов")

        conn.close()

        # VACUUM в отдельном соединении (не внутри транзакции)
        conn2 = sqlite3.connect(output_path)
        conn2.execute("VACUUM")
        conn2.close()

    except Exception:
        conn.close()
        raise

    file_size_mb = os.path.getsize(output_path) / (1024 * 1024)
    logging.info(f"  Размер файла: {file_size_mb:.1f} MB")

    return output_path
