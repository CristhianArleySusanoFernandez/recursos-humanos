"""
Script de autorización OAuth 2.0 para Google Drive.

Ejecútalo UNA SOLA VEZ antes de arrancar la app:
    python setup_google_auth.py

Qué hace:
1. Lee el archivo credentials.json desde GOOGLE_OAUTH_CREDENTIALS_PATH.
2. Abre el navegador para que autorices el acceso a tu Google Drive.
3. Guarda el token resultante en GOOGLE_OAUTH_TOKEN_PATH.

A partir de ese momento la app usa el token automáticamente y lo
refresca sola cuando vence (sin necesidad de volver a correr este script).
"""

import json
import os
import sys

from dotenv import load_dotenv

load_dotenv()

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
except ImportError:
    print("ERROR: Falta google-auth-oauthlib.")
    print("Instálalo con:  pip install google-auth-oauthlib")
    sys.exit(1)

_SCOPES = ["https://www.googleapis.com/auth/drive"]


def _build_flow() -> InstalledAppFlow:
    """
    Crea el flujo OAuth admitiendo las credenciales del cliente por variable de
    entorno (GOOGLE_OAUTH_CREDENTIALS_JSON) o por archivo
    (GOOGLE_OAUTH_CREDENTIALS_PATH). La variable de entorno tiene prioridad.
    """
    credentials_json = os.environ.get("GOOGLE_OAUTH_CREDENTIALS_JSON", "").strip()
    if credentials_json:
        return InstalledAppFlow.from_client_config(json.loads(credentials_json), _SCOPES)

    credentials_path = os.environ.get("GOOGLE_OAUTH_CREDENTIALS_PATH", "")
    if not credentials_path:
        print("ERROR: Define GOOGLE_OAUTH_CREDENTIALS_PATH (ruta a credentials.json)")
        print("  o GOOGLE_OAUTH_CREDENTIALS_JSON (contenido del JSON) en tu .env")
        print("  Descarga credentials.json desde Google Cloud Console:")
        print("  APIs & Services → Credentials → OAuth 2.0 Client IDs → Download JSON")
        sys.exit(1)

    if not os.path.exists(credentials_path):
        print(f"ERROR: No se encontró el archivo de credenciales en: {credentials_path}")
        sys.exit(1)

    return InstalledAppFlow.from_client_secrets_file(credentials_path, _SCOPES)


def main() -> None:
    token_path = os.environ.get("GOOGLE_OAUTH_TOKEN_PATH", "")

    if not token_path:
        print("ERROR: Define GOOGLE_OAUTH_TOKEN_PATH en tu archivo .env")
        print("  Ejemplo: GOOGLE_OAUTH_TOKEN_PATH=C:\\credentials\\token.json")
        sys.exit(1)

    print("Iniciando flujo de autorización OAuth 2.0...")
    print("Se abrirá el navegador. Inicia sesión con la cuenta de Google")
    print("que contiene la carpeta raíz de RRHH Docs y autoriza el acceso.")
    print()

    flow = _build_flow()
    creds = flow.run_local_server(port=0)

    # Asegura que el directorio destino exista.
    token_dir = os.path.dirname(token_path)
    if token_dir:
        os.makedirs(token_dir, exist_ok=True)

    with open(token_path, "w", encoding="utf-8") as f:
        f.write(creds.to_json())

    print(f"Token guardado exitosamente en: {token_path}")
    print()
    print("Ya puedes arrancar la app:")
    print("    venv\\Scripts\\python -m uvicorn main:app --reload")


if __name__ == "__main__":
    main()
