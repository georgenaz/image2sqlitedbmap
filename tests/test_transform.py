import pytest
import sys
import os
import math

# Добавляем корневую директорию проекта в путь
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from calc_tools import calculate_image_transform_params, calculate_final_corner_gps


def test_coordinate_accuracy():
    """
    Тест проверяет, что вычисленные GPS координаты углов после преобразования
    максимально близки к входным координатам, учитывая точность zoom уровня.
    """
    # Тестовые данные - прямоугольная область
    img_width, img_height = 1000, 1000

    coords = {
        "top_left": (55.751244, 37.618423),
        "top_right": (55.751244, 37.628423),
        "bottom_right": (55.741244, 37.628423),
        "bottom_left": (55.741244, 37.618423),
    }

    # Тестируем на разных zoom уровнях
    for zoom in [14, 15, 16, 17, 18]:
        # Вычисляем параметры преобразования
        transform_params = calculate_image_transform_params(img_width, img_height, coords, zoom)

        # Вычисляем финальные координаты
        final_coords = calculate_final_corner_gps(transform_params, coords, zoom)

        # Проверяем точность для каждого угла
        for corner in coords:
            orig_lat, orig_lon = coords[corner]
            calc_lat, calc_lon = final_coords[corner]

            # Вычисляем допустимую погрешность на данном zoom уровне
            # Разрешение тайла на данном zoom: ~156543м / 2^zoom на экваторе
            # Для пикселя: ~156543м / 2^zoom / 256
            # Допустимая погрешность: 1 пиксель
            meters_per_pixel = 156543 / (2 ** zoom) / 256
            tolerance_m = meters_per_pixel * 2  # даем запас

            # Перевод в градусы
            lat_tolerance = tolerance_m / 111000  # ~111км на градус широты
            lon_tolerance = tolerance_m / (111000 * abs(math.cos(math.radians(orig_lat))))  # корректировка для долготы

            # Проверяем, что отклонение в пределах допустимого
            assert abs(calc_lat - orig_lat) <= lat_tolerance, \
                f"Широта {corner} на zoom {zoom}: ожидалось {orig_lat}, получено {calc_lat}, отклонение {abs(calc_lat - orig_lat)} > {lat_tolerance}"

            assert abs(calc_lon - orig_lon) <= lon_tolerance, \
                f"Долгота {corner} на zoom {zoom}: ожидалось {orig_lon}, получено {calc_lon}, отклонение {abs(calc_lon - orig_lon)} > {lon_tolerance}"

            print(f"Zoom {zoom}, {corner}: отклонение lat={abs(calc_lat - orig_lat):.8f}°, lon={abs(calc_lon - orig_lon):.8f}°")


def test_rotation_angle_calculation():
    """Тест расчета угла поворота."""
    from calc_tools import calculate_rotation_angle

    # Прямоугольная область без поворота
    coords = {
        "top_left": (55.751244, 37.618423),
        "top_right": (55.751244, 37.628423),
        "bottom_right": (55.741244, 37.628423),
        "bottom_left": (55.741244, 37.618423),
    }

    angle = calculate_rotation_angle(coords)
    # Для прямоугольной области угол должен быть близок к 0
    assert abs(angle) < 1.0, f"Угол поворота должен быть близок к 0, получено {angle}"


if __name__ == "__main__":
    test_coordinate_accuracy()
    test_rotation_angle_calculation()
    print("Все тесты пройдены!")