-- ============================================================
-- Schema del proyecto: Checklist Documental de Empleados
-- Base de datos: Supabase (PostgreSQL)
-- Ejecutar en el SQL Editor de Supabase o con psql.
-- ============================================================

-- Tipo enumerado que refleja exactamente los valores de DocumentType en Python.
-- Agregar un nuevo tipo de documento requiere ALTER TYPE + actualizar el enum en Python.
CREATE TYPE document_type_enum AS ENUM (
    'hoja_de_vida',
    'cedula',
    'soat',
    'rut',
    'contrato'
);

-- ------------------------------------------------------------
-- Tabla: employees
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS employees (
    id          UUID        PRIMARY KEY,
    name        TEXT        NOT NULL CHECK (char_length(trim(name)) > 0),
    position    TEXT        NOT NULL CHECK (char_length(trim(position)) > 0),
    is_active   BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Índice para acelerar los listados por estado activo/inactivo (panel principal).
CREATE INDEX IF NOT EXISTS idx_employees_is_active ON employees (is_active);

-- ------------------------------------------------------------
-- Tabla: documents
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS documents (
    id              UUID                PRIMARY KEY,
    employee_id     UUID                NOT NULL REFERENCES employees (id) ON DELETE CASCADE,
    document_type   document_type_enum  NOT NULL,
    file_name       TEXT                NOT NULL,
    drive_file_id   TEXT                NOT NULL,
    drive_url       TEXT                NOT NULL,
    uploaded_at     TIMESTAMPTZ         NOT NULL DEFAULT NOW(),

    -- Un empleado solo puede tener un documento activo por tipo.
    CONSTRAINT uq_employee_document_type UNIQUE (employee_id, document_type)
);

-- Índice para las consultas get_by_employee (carga del checklist).
CREATE INDEX IF NOT EXISTS idx_documents_employee_id ON documents (employee_id);

-- ------------------------------------------------------------
-- Row Level Security (opcional pero recomendado en Supabase)
-- Habilitar si se usa la anon key desde el frontend.
-- Con service_role key desde el backend esto no es necesario.
-- ------------------------------------------------------------
-- ALTER TABLE employees ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
