#!/usr/bin/env python

import os
import sqlite3


def get_database_filename(image_file):
    """
    Генерирует уникальное имя файла базы данных на основе имени файла изображения,
    добавляя версию если файл уже существует.
    """
    base_name = os.path.splitext(os.path.basename(image_file))[0]
    db_name = base_name + ".sqlitedb"
    version = 1
    while os.path.exists(db_name):
        db_name = f"{base_name}-v{version}.sqlitedb"
        version += 1
    return db_name


def create_database(db_name, max_zoom=None, min_zoom=0):
    """
    Создает новый файл базы данных SQLite и инициализирует таблицы tiles и info.

    Args:
        db_name: Имя файла базы данных
        max_zoom: Максимальный уровень масштабирования
        min_zoom: Минимальный уровень масштабирования (по умолчанию 0)
    """
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()

    # Создание таблицы tiles
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

    # Создание таблицы info
    cursor.execute("""
        CREATE TABLE info (
            maxzoom INTEGER,
            minzoom INTEGER,
            tilenumbering TEXT
        )
    """)

    # Вставка начальных значений в info
    cursor.execute(
        "INSERT INTO info (maxzoom, minzoom) VALUES (?, ?)", (max_zoom, min_zoom)
    )

    conn.commit()
    conn.close()

    print(f"База данных '{db_name}' создана успешно.")
