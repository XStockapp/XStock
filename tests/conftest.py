import pytest


@pytest.fixture(autouse=True)
def _sin_cache_de_datos():
    """history_tf tiene caché de Streamlit: cada prueba empieza sin datos guardados de otra."""
    from core import data
    data.history_tf.clear()
    yield


@pytest.fixture(autouse=True)
def _sin_cache_de_perfiles():
    from core import db
    db._olvidar()
    db._WL.clear()
    yield
