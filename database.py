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


def create_database(db_name, max_zoom=None, min_zoom=3, conn=None):
    """
    Создает новый файл базы данных SQLite и инициализирует таблицы tiles и info.

    Args:
        db_name: Имя файла базы данных
        max_zoom: Максимальный уровень масштабирования
        min_zoom: Минимальный уровень масштабирования (по умолчанию 0)
        conn: SQLite соединение (опционально, если не указан, создается новое и закрывается)
    """
    own_conn = False
    if conn is None:
        own_conn = True
        conn = sqlite3.connect(db_name)

    cursor = conn.cursor()

    # Создание таблицы tiles
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tiles (
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
        CREATE TABLE IF NOT EXISTS info (
            maxzoom INTEGER,
            minzoom INTEGER,
            tilenumbering TEXT
        )
    """)

    # Вставка начальных значений в info
    cursor.execute(
        "INSERT OR REPLACE INTO info (maxzoom, minzoom, tilenumbering) VALUES (?, ?, 0)", (max_zoom, min_zoom)
    )

    if not own_conn:
        conn.commit()  # Хотя SQLite auto-commit, но на всякий
    else:
        conn.close()

    if own_conn:
        print(f"База данных '{db_name}' создана успешно.")


def insert_tile(conn, x, y, z, s, image_data):
    """
    Вставляет запись о тайле в таблицу tiles.

    Args:
        conn: SQLite соединение.
        x, y, z, s: Координаты и параметры тайла.
        image_data: Данные изображения в формате bytes.
    """
    cursor = conn.cursor()
    cursor.execute("INSERT INTO tiles (x, y, z, s, image) VALUES (?, ?, ?, ?, ?)", (x, y, z, s, image_data))
    conn.commit()
