"""Conexión a Weaviate y utilidades de la colección `Normativa`."""
from __future__ import annotations

from contextlib import contextmanager

from config import settings


def get_client(timeout: int = 30):
    """Crea un cliente de Weaviate (v4) contra la instancia configurada."""
    import weaviate
    from weaviate.classes.init import AdditionalConfig, Timeout

    return weaviate.connect_to_local(
        host=settings.WEAVIATE_HOST,
        port=settings.WEAVIATE_HTTP_PORT,
        grpc_port=settings.WEAVIATE_GRPC_PORT,
        additional_config=AdditionalConfig(timeout=Timeout(init=timeout, query=60, insert=120)),
    )


@contextmanager
def collection(recreate: bool = False):
    """Context manager que garantiza la colección y cierra el cliente."""
    from src.schema import create_collection

    client = get_client()
    try:
        col = create_collection(client, recreate=recreate)
        yield client, col
    finally:
        client.close()


def count_objects(col) -> int:
    """Número de objetos en la colección."""
    agg = col.aggregate.over_all(total_count=True)
    return agg.total_count or 0


def is_ready() -> bool:
    """Comprueba disponibilidad del servidor Weaviate."""
    try:
        client = get_client(timeout=5)
        try:
            return client.is_ready()
        finally:
            client.close()
    except Exception:  # noqa: BLE001
        return False
