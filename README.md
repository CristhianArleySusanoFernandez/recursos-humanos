# RRHH Docs — Checklist Documental de Empleados

Aplicación web para que el área de Recursos Humanos gestione los documentos requeridos de cada empleado. Los archivos se almacenan en Google Drive y el tipo de documento se clasifica automáticamente con Claude AI.

---

## Requisitos previos

- Python 3.11 o superior
- Una cuenta de Supabase (gratuita)
- Un proyecto de Google Cloud con la API de Drive habilitada
- Una API key de Anthropic

---

## 1. Clonar e instalar dependencias

```bash
git clone <url-del-repositorio>
cd RecursosHumanos

python -m venv venv
# Windows:
venv\Scripts\activate
# macOS / Linux:
source venv/bin/activate

pip install -r requirements.txt
```

---

## 2. Configurar las variables de entorno

Copia el archivo de ejemplo y complétalo:

```bash
cp .env.example .env
```

Abre `.env` y completa cada variable:

### `SUPABASE_URL`
La URL de tu proyecto Supabase.  
**Dónde conseguirla:** Panel de Supabase → *Project Settings* → *API* → campo *Project URL*.  
Ejemplo: `https://abcdefghij.supabase.co`

### `SUPABASE_KEY`
La clave de acceso a Supabase. Usa la **service role key** para operaciones desde el backend (tiene permisos completos y omite Row Level Security).  
**Dónde conseguirla:** Panel de Supabase → *Project Settings* → *API* → sección *Project API keys* → `service_role`.  
> ⚠ Nunca expongas esta clave en el frontend.

### `GOOGLE_SERVICE_ACCOUNT_JSON`
Ruta absoluta al archivo JSON de credenciales de la Service Account de Google.  
**Cómo conseguirlo:** Ver sección [Configurar Google Drive](#4-configurar-google-drive) más abajo.  
Ejemplo: `C:\credentials\rrhh-service-account.json`

### `GOOGLE_DRIVE_ROOT_FOLDER_ID`
El ID de la carpeta en Google Drive donde se crearán las subcarpetas de cada empleado.  
**Cómo conseguirlo:** Abre la carpeta en Google Drive en el navegador. El ID es la última parte de la URL:  
`https://drive.google.com/drive/folders/`**`1A2B3C4D5E6F7G8H9I`**  
Copia esa parte: `1A2B3C4D5E6F7G8H9I`.

### `ANTHROPIC_API_KEY`
Tu API key de Anthropic para usar Claude.  
**Dónde conseguirla:** [console.anthropic.com](https://console.anthropic.com) → *API Keys* → *Create Key*.  
Ejemplo: `sk-ant-api03-...`

---

## 3. Ejecutar el schema SQL en Supabase

El archivo `supabase_schema.sql` crea las tablas `employees` y `documents` con todas las restricciones necesarias.

**Pasos:**
1. Abre el [panel de Supabase](https://app.supabase.com) y selecciona tu proyecto.
2. Ve a **SQL Editor** (ícono de terminal en la barra lateral).
3. Crea un nuevo query y pega el contenido completo de `supabase_schema.sql`.
4. Haz clic en **Run**.

Verifica que las tablas `employees` y `documents` aparezcan en la sección **Table Editor**.

---

## 4. Configurar Google Drive

### 4.1 Crear la Service Account

1. Ve a [Google Cloud Console](https://console.cloud.google.com).
2. Crea un proyecto nuevo o selecciona uno existente.
3. Habilita la **Google Drive API**: *APIs & Services* → *Library* → busca "Google Drive API" → *Enable*.
4. Ve a *APIs & Services* → *Credentials* → *Create Credentials* → **Service Account**.
5. Dale un nombre (ej: `rrhh-docs`), haz clic en *Create and Continue* → *Done*.
6. En la lista de Service Accounts, haz clic en la que acabas de crear.
7. Ve a la pestaña **Keys** → *Add Key* → *Create new key* → **JSON** → *Create*.
8. Se descargará un archivo JSON. Guárdalo en una ruta segura (fuera del repositorio).
9. Anota el **email** de la Service Account (tiene el formato `nombre@proyecto.iam.gserviceaccount.com`).

### 4.2 Compartir la carpeta de Drive con la Service Account

1. En Google Drive, crea una carpeta raíz para los documentos (ej: `RRHH - Documentos`).
2. Haz clic derecho en la carpeta → **Compartir**.
3. En el campo de email, pega el email de la Service Account (`nombre@proyecto.iam.gserviceaccount.com`).
4. Asigna el rol **Editor**.
5. Haz clic en *Enviar* (sin marcar "Notificar a personas").
6. Copia el ID de la carpeta desde la URL y ponlo en `GOOGLE_DRIVE_ROOT_FOLDER_ID`.

---

## 5. Arrancar la aplicación

```bash
uvicorn main:app --reload
```

La aplicación estará disponible en [http://localhost:8000](http://localhost:8000).

- `--reload` recarga automáticamente al guardar cambios en el código (útil en desarrollo).
- Para producción, omite `--reload` y considera usar `--workers 2`.

---

## Estructura del proyecto

```
RecursosHumanos/
├── domain/            # Entidades y puertos — sin dependencias externas
├── application/       # Casos de uso — orquesta dominio y puertos
├── infrastructure/    # Adaptadores: Supabase, Google Drive, Claude
├── api/               # Routers FastAPI y templates Jinja2
├── main.py            # Punto de entrada
├── supabase_schema.sql
├── requirements.txt
└── .env.example
```
