"""tests for export.parse_pages — TDD RED phase"""

import pytest
from export import parse_pages


def test_empty_means_all():
    assert parse_pages("", 5) == [0, 1, 2, 3, 4]


def test_whitespace_means_all():
    assert parse_pages("   ", 5) == [0, 1, 2, 3, 4]


def test_all_means_all():
    assert parse_pages("all", 5) == [0, 1, 2, 3, 4]


def test_all_case_insensitive():
    assert parse_pages("ALL", 5) == [0, 1, 2, 3, 4]
    assert parse_pages("All", 5) == [0, 1, 2, 3, 4]


def test_single_page():
    assert parse_pages("3", 5) == [2]


def test_single_page_first():
    assert parse_pages("1", 5) == [0]


def test_single_page_last():
    assert parse_pages("5", 5) == [4]


def test_range():
    assert parse_pages("3-7", 10) == [2, 3, 4, 5, 6]


def test_range_from_start():
    assert parse_pages("1-3", 5) == [0, 1, 2]


def test_range_to_end():
    assert parse_pages("3-5", 5) == [2, 3, 4]


def test_range_same_page():
    assert parse_pages("3-3", 5) == [2]


def test_mixed():
    assert parse_pages("1,3-5,8", 10) == [0, 2, 3, 4, 7]


def test_mixed_with_spaces():
    assert parse_pages(" 1 , 3 - 5 , 8 ", 10) == [0, 2, 3, 4, 7]


def test_mixed_overlapping():
    # 3 appears in both single and range; result should be deduplicated
    assert parse_pages("3,3-5", 10) == [2, 3, 4]


def test_out_of_range_single_raises():
    with pytest.raises(ValueError, match="超出范围"):
        parse_pages("11", 10)


def test_out_of_range_in_range_raises():
    with pytest.raises(ValueError, match="超出范围"):
        parse_pages("8-11", 10)


def test_zero_page_raises():
    with pytest.raises(ValueError, match="必须 >= 1"):
        parse_pages("0", 5)


def test_negative_page_raises():
    # "-1" contains "-" so it's parsed as a range; either invalid range or >= 1
    with pytest.raises(ValueError):
        parse_pages("-1", 5)


def test_invalid_number_raises():
    with pytest.raises(ValueError, match="无效页码"):
        parse_pages("abc", 5)


def test_invalid_range_raises():
    with pytest.raises(ValueError, match="无效页码范围"):
        parse_pages("5-3", 10)


def test_total_pages_1():
    assert parse_pages("1", 1) == [0]
    with pytest.raises(ValueError):
        parse_pages("2", 1)
