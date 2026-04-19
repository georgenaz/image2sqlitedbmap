from map_calc_tools import get_tile_coords_by_gps, validate_gps_coords
import pytest


def test_test():
    assert 2 == 2


def test_test2():
    assert get_tile_coords_by_gps(58, 37, 14) == (9875, 4934), "Wrong calc tile coords"


def test_validate_gps_coords():
    # Valid coordinates should not raise
    validate_gps_coords(55.75, 37.62)  # Moscow
    validate_gps_coords(0, 0)  # Equator/Prime meridian
    validate_gps_coords(85.05, 180)  # Max valid latitude
    validate_gps_coords(-85.05, -180)  # Min valid latitude

    # Invalid latitude (out of WGS84 range)
    with pytest.raises(ValueError, match="Широта"):
        validate_gps_coords(91, 0)

    with pytest.raises(ValueError, match="Широта"):
        validate_gps_coords(-91, 0)

    # Invalid longitude (out of range)
    with pytest.raises(ValueError, match="Долгота"):
        validate_gps_coords(0, 181)

    with pytest.raises(ValueError, match="Долгота"):
        validate_gps_coords(0, -181)

    # Web Mercator limit exceeded
    with pytest.raises(ValueError, match="Web Mercator"):
        validate_gps_coords(85.06, 0)

    with pytest.raises(ValueError, match="Web Mercator"):
        validate_gps_coords(-85.06, 0)

