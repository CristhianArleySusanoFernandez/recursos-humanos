-- =============================================================================
-- RRHH Docs - Setup completo de base de datos
-- Ejecutar en Supabase SQL Editor
-- Este archivo configura la BD desde cero
-- ADVERTENCIA: elimina todos los datos existentes
-- =============================================================================
--
-- Distribuciones SantiagoDeTunja S.A.S.
--
-- Reemplaza y consolida:
--   - supabase_schema_v2.sql
--   - supabase_migration_document_na.sql
--   - supabase_migration_extra_category.sql
--
-- Ejecutar el archivo completo de una sola vez: las secciones dependen
-- unas de otras y deben correr en este orden.
-- =============================================================================


-- ---------------------------------------------------------------------------
-- 1. Eliminar tablas existentes
--    Orden inverso al de dependencias: primero las que referencian a otras.
-- ---------------------------------------------------------------------------

DROP TABLE IF EXISTS document_na     CASCADE;
DROP TABLE IF EXISTS documents       CASCADE;
DROP TABLE IF EXISTS employees       CASCADE;
DROP TABLE IF EXISTS groups          CASCADE;
DROP TABLE IF EXISTS document_types  CASCADE;


-- ---------------------------------------------------------------------------
-- 2. document_types
--    Catálogo configurable de tipos de documento.
--
--    category:
--      'INGRESO' | 'RETIRO' → documentos requeridos; cuentan para el
--                             checklist y el % de completitud.
--      'EXTRA'              → archivos adicionales. La subida masiva crea
--                             uno por archivo que el clasificador no supo
--                             encajar (code = 'EXTRA_<md5[:8]>'), lo que
--                             sortea el UNIQUE(employee_id, document_type_id)
--                             de documents y permite varios extras por
--                             empleado. NO cuentan para la completitud.
-- ---------------------------------------------------------------------------

CREATE TABLE document_types (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name         TEXT        NOT NULL,
    code         TEXT        NOT NULL,
    category     TEXT        NOT NULL CHECK (category IN ('INGRESO', 'RETIRO', 'EXTRA')),
    is_active    BOOLEAN     NOT NULL DEFAULT TRUE,
    order_index  INTEGER     NOT NULL DEFAULT 0,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_document_types_code UNIQUE (code)
);


-- ---------------------------------------------------------------------------
-- 3. groups
--    Jerarquía de dos niveles.
--      parent_id NULL     → nivel 1 (ej: Tunja)
--      parent_id NOT NULL → nivel 2 (ej: Asesores dentro de Tunja)
--
--    ON DELETE RESTRICT: un grupo con hijos no se puede borrar sin
--    reasignarlos primero (lo valida DeleteGroup en la app).
-- ---------------------------------------------------------------------------

CREATE TABLE groups (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name             TEXT        NOT NULL,
    parent_id        UUID        REFERENCES groups(id) ON DELETE RESTRICT,
    drive_folder_id  TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_groups_name_parent UNIQUE (name, parent_id)
);


-- ---------------------------------------------------------------------------
-- 4. employees
--    group_id es NULLable: al borrar un grupo cuyos empleados están todos
--    inactivos, la app los deja sin grupo en vez de bloquear el borrado.
-- ---------------------------------------------------------------------------

CREATE TABLE employees (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT        NOT NULL CHECK (char_length(trim(name)) > 0),
    position    TEXT        NOT NULL CHECK (char_length(trim(position)) > 0),
    group_id    UUID        REFERENCES groups(id) ON DELETE RESTRICT,
    is_active   BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- ---------------------------------------------------------------------------
-- 5. documents
--    Un documento por (empleado, tipo). Al eliminar un empleado sus
--    documentos se borran en cascada.
-- ---------------------------------------------------------------------------

CREATE TABLE documents (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    employee_id       UUID        NOT NULL REFERENCES employees(id)      ON DELETE CASCADE,
    document_type_id  UUID        NOT NULL REFERENCES document_types(id) ON DELETE RESTRICT,
    file_name         TEXT        NOT NULL,
    drive_file_id     TEXT        NOT NULL,
    drive_url         TEXT        NOT NULL,
    uploaded_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_employee_document_type UNIQUE (employee_id, document_type_id)
);


-- ---------------------------------------------------------------------------
-- 6. document_na
--    Marca un tipo de documento como "No Aplica" para un empleado concreto.
--    La fila existe = está marcado; se borra al desmarcar.
-- ---------------------------------------------------------------------------

CREATE TABLE document_na (
    employee_id       UUID        NOT NULL REFERENCES employees(id)      ON DELETE CASCADE,
    document_type_id  UUID        NOT NULL REFERENCES document_types(id) ON DELETE CASCADE,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (employee_id, document_type_id)
);


-- ---------------------------------------------------------------------------
-- 7. Índices
-- ---------------------------------------------------------------------------

CREATE INDEX idx_employees_is_active   ON employees(is_active);
CREATE INDEX idx_employees_group_id    ON employees(group_id);
CREATE INDEX idx_documents_employee_id ON documents(employee_id);
CREATE INDEX idx_groups_parent_id      ON groups(parent_id);
CREATE INDEX idx_doctypes_category     ON document_types(category, order_index);


-- ---------------------------------------------------------------------------
-- 8. Datos iniciales: document_types
--    25 de ingreso + 8 de retiro + 1 extra genérico.
-- ---------------------------------------------------------------------------

INSERT INTO document_types (code, name, category, order_index) VALUES

-- Categoría INGRESO
('FORMATO_ENTREVISTA',    'Formato de Entrevista - Reclutamiento',                                  'INGRESO',  1),
('HOJA_DE_VIDA',          'Hoja de Vida con Foto',                                                  'INGRESO',  2),
('CERTIFICADO_ESTUDIO',   'Certificado de Estudio',                                                 'INGRESO',  3),
('CERTIFICADO_LABORAL',   'Certificado Laboral',                                                    'INGRESO',  4),
('AUTOBIOGRAFIA',         'Autobiografía',                                                          'INGRESO',  5),
('HOJA_DE_VIDA_INTERNA',  'Hoja de Vida Interna',                                                   'INGRESO',  6),
('CERT_MANIPULACION',     'Certificado Manipulación de Alimentos',                                  'INGRESO',  7),
('ANTECEDENTES',          'Antecedentes Policía / Procuraduría / Contraloría / Medidas Correctivas','INGRESO',  8),
('CERT_PENSION_EPS',      'Certificado de Pensión - EPS',                                           'INGRESO',  9),
('EXAMEN_MEDICO',         'Examen Médico Ocupacional',                                              'INGRESO', 10),
('CARNET_VACUNAS',        'Carnet de Vacunas',                                                      'INGRESO', 11),
('REGISTRO_CIVIL',        'Registro Civil y/o Tarjeta Hijos',                                       'INGRESO', 12),
('CEDULA_CONYUGE',        'Cédula Cónyuge 150%',                                                    'INGRESO', 13),
('RUT',                   'RUT',                                                                    'INGRESO', 14),
('RUT_LICENCIA',          'RUT - Licencia de Conducción',                                           'INGRESO', 15),
('FOTOCOPIA_CEDULA',      'Fotocopia de la Cédula 150%',                                            'INGRESO', 16),
('CERT_BANCARIA',         'Certificación Bancaria',                                                 'INGRESO', 17),
('HABEAS_DATA',           'Habeas Data',                                                            'INGRESO', 18),
('CONTRATO',              'Contrato - Otro SI',                                                     'INGRESO', 19),
('LLAMADO_REFLEXION',     'Llamado a la Reflexión',                                                 'INGRESO', 20),
('AFILIACION_EPS',        'Afiliación EPS',                                                         'INGRESO', 21),
('AFILIACION_ARL',        'Afiliación ARL',                                                         'INGRESO', 22),
('AFILIACION_COMFABOY',   'Afiliación Comfaboy',                                                    'INGRESO', 23),
('INDUCCION_SG_SST',      'Inducción SG-SST / Corporativo',                                         'INGRESO', 24),
('ENTRENAMIENTO',         'Entrenamiento Fuerza de Ventas - Logística',                             'INGRESO', 25),

-- Categoría RETIRO
('CARTA_RETIRO',           'Carta de Retiro',              'RETIRO',  1),
('ENTREVISTA_RETIRO',      'Entrevista de Retiro',         'RETIRO',  2),
('RETIRO_ARL',             'Retiro ARL',                   'RETIRO',  3),
('LIQUIDACION',            'Liquidación',                  'RETIRO',  4),
('ORDEN_EXAMEN_EGRESO',    'Orden Examen de Egreso',       'RETIRO',  5),
('CERT_LABORAL_RETIRO',    'Certificación Laboral',        'RETIRO',  6),
('CARTA_RETIRO_CESANTIAS', 'Carta de Retiro de Cesantías', 'RETIRO',  7),
('CERT_APORTES',           'Certificado Aportes',          'RETIRO',  8),

-- Categoría EXTRA
-- Tipo genérico que usa migrate_drive.py para archivos sin categoría.
-- Va en 'EXTRA' y no en 'INGRESO': de lo contrario aparecería como fila
-- faltante en el checklist de todos los empleados y bajaría su completitud.
('EXTRA',                  'Documento Extra',              'EXTRA',  99);


-- ---------------------------------------------------------------------------
-- 9. Datos iniciales: groups — nivel 1 (zonas)
--    UUIDs fijos para poder referenciarlos como padres más abajo.
-- ---------------------------------------------------------------------------

INSERT INTO groups (id, name, parent_id) VALUES
('00000001-0000-0000-0000-000000000001', 'Tunja',        NULL),
('00000001-0000-0000-0000-000000000002', 'Barbosa',      NULL),
('00000001-0000-0000-0000-000000000003', 'Chiquinquirá', NULL),
('00000001-0000-0000-0000-000000000004', 'Estudiantes',  NULL),
('00000001-0000-0000-0000-000000000005', 'Retirados',    NULL);


-- ---------------------------------------------------------------------------
-- 10. Datos iniciales: groups — nivel 2 (categorías dentro de cada zona)
-- ---------------------------------------------------------------------------

-- Hijos de Tunja
INSERT INTO groups (name, parent_id) VALUES
('Asesores',        '00000001-0000-0000-0000-000000000001'),
('Logísticos',      '00000001-0000-0000-0000-000000000001'),
('Administrativos', '00000001-0000-0000-0000-000000000001');

-- Hijos de Barbosa
INSERT INTO groups (name, parent_id) VALUES
('Asesores',        '00000001-0000-0000-0000-000000000002'),
('Logísticos',      '00000001-0000-0000-0000-000000000002'),
('Administrativos', '00000001-0000-0000-0000-000000000002');

-- Hijos de Chiquinquirá
INSERT INTO groups (name, parent_id) VALUES
('Asesores',        '00000001-0000-0000-0000-000000000003'),
('Logísticos',      '00000001-0000-0000-0000-000000000003'),
('Administrativos', '00000001-0000-0000-0000-000000000003');

-- Hijos de Estudiantes
INSERT INTO groups (name, parent_id) VALUES
('SENA',            '00000001-0000-0000-0000-000000000004'),
('UPTC',            '00000001-0000-0000-0000-000000000004'),
('Santo Tomás',     '00000001-0000-0000-0000-000000000004');

-- Hijos de Retirados
INSERT INTO groups (name, parent_id) VALUES
('Tunja',           '00000001-0000-0000-0000-000000000005'),
('Barbosa',         '00000001-0000-0000-0000-000000000005'),
('Chiquinquirá',    '00000001-0000-0000-0000-000000000005');


-- =============================================================================
-- Verificación
-- =============================================================================
-- Debe devolver: 25 INGRESO, 8 RETIRO, 1 EXTRA
--
--   SELECT category, COUNT(*) FROM document_types GROUP BY category ORDER BY category;
--
-- Debe devolver: 5 zonas, 15 subgrupos
--
--   SELECT CASE WHEN parent_id IS NULL THEN 'nivel 1' ELSE 'nivel 2' END AS nivel,
--          COUNT(*)
--   FROM groups GROUP BY 1;
-- =============================================================================


-- =============================================================================
-- Pasos siguientes (fuera de este archivo)
-- =============================================================================
-- 1. python sync_drive_folders.py   → crea las carpetas en Drive y rellena
--                                     groups.drive_folder_id (queda NULL aquí).
-- 2. python migrate_drive.py        → importa empleados y documentos ya
--                                     existentes en Drive (opcional).
-- =============================================================================
