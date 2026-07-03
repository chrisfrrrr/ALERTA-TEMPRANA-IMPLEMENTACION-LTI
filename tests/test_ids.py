from utils.ids import extract_carne


def test_extract_carne_from_uvg_email():
    assert extract_carne("cas262958@uvg.edu.gt") == "262958"


def test_extract_carne_empty():
    assert extract_carne(None) == ""
