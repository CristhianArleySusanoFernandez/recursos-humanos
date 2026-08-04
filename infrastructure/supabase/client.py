import os

from supabase import Client, create_client

_client: Client | None = None


def get_supabase_client() -> Client:
    """
    Retorna la instancia única del cliente Supabase.
    Se inicializa la primera vez que se llama (lazy singleton).
    Lanza RuntimeError si faltan las variables de entorno requeridas.
    """
    global _client
    if _client is None:
        url = os.environ.get("SUPABASE_URL", "")
        key = os.environ.get("SUPABASE_KEY", "")
        if not url or not key:
            raise RuntimeError(
                "Faltan las variables de entorno SUPABASE_URL y/o SUPABASE_KEY."
            )
        _client = create_client(url, key)
    return _client
