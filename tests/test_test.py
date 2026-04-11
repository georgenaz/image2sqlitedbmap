import pytest
from map_calc_tools import get_tile_coords_by_gps

def test_test():
    assert 2 == 2

def test_test2():
    assert get_tile_coords_by_gps(58, 37, 14) == (9875, 4934), "Wrong calc tile coords"

