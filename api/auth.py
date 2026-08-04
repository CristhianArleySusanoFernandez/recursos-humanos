"""
Autenticación HTTP Basic para toda la aplicación.

Es una única cuenta compartida para RRHH (no un sistema multiusuario): solo
evita que cualquiera con la URL entre sin contraseña. Las credenciales se leen
de las variables de entorno APP_USERNAME y APP_PASSWORD.

`verify_credentials` se registra como dependencia GLOBAL del app (ver main.py),
por lo que se aplica a TODAS las rutas de TODOS los routers.
"""
import os
import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

_security = HTTPBasic()


def _load_credentials() -> tuple[str, str]:
    """Lee las credenciales del entorno; falla si no están configuradas."""
    username = os.environ.get("APP_USERNAME")
    password = os.environ.get("APP_PASSWORD")
    if not username or not password:
        raise RuntimeError(
            "Debes configurar APP_USERNAME y APP_PASSWORD en las variables de entorno."
        )
    return username, password


# Se evalúa al importar el módulo (arranque de la app): si faltan las variables,
# la aplicación no arranca y muestra el mensaje claro exigido.
_APP_USERNAME, _APP_PASSWORD = _load_credentials()


def verify_credentials(
    credentials: HTTPBasicCredentials = Depends(_security),
) -> str:
    """
    Valida usuario y contraseña con comparación resistente a timing attacks.
    Devuelve el nombre de usuario autenticado (por si algún día se necesita).
    """
    # compare_digest sobre bytes; comparamos ambos campos SIEMPRE para no filtrar
    # por tiempo cuál de los dos falló.
    user_ok = secrets.compare_digest(
        credentials.username.encode("utf-8"), _APP_USERNAME.encode("utf-8")
    )
    pass_ok = secrets.compare_digest(
        credentials.password.encode("utf-8"), _APP_PASSWORD.encode("utf-8")
    )
    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales inválidas.",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username
