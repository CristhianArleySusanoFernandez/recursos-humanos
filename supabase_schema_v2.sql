-- =============================================================================
-- OBSOLETO — NO EJECUTAR
--
-- Reemplazado por supabase_setup_completo.sql, que consolida este archivo
-- junto con supabase_migration_document_na.sql y
-- supabase_migration_extra_category.sql.
--
-- Se conserva solo como referencia histórica. Este archivo NO incluye la
-- tabla document_na, por lo que el toggle "No Aplica" fallaría.
-- =============================================================================

-- =============================================================================
-- RRHH Docs – Schema v2
-- Ejecutar desde cero en el SQL Editor de Supabase.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. Eliminar tablas en orden inverso de dependencias
-- ---------------------------------------------------------------------------

DROP TABLE IF EXISTS documents        CASCADE;
DROP TABLE IF EXISTS employees        CASCADE;
DROP TABLE IF EXISTS groups           CASCADE;
DROP TABLE IF EXISTS document_types   CASCADE;

-- ---------------------------------------------------------------------------
-- 2. document_types
--    Catálogo configurable de tipos de documento.
--    category: 'INGRESO' | 'RETIRO' | 'EXTRA'
--    'EXTRA' lo genera automáticamente la subida masiva para archivos sin
--    categoría; esos tipos no cuentan para el checklist ni la completitud.
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
--    parent_id NULL  → nivel 1 (ej: Tunja)
--    parent_id NOT NULL → nivel 2 (ej: Asesores dentro de Tunja)
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
-- ---------------------------------------------------------------------------

CREATE TABLE documents (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    employee_id       UUID        NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    document_type_id  UUID        NOT NULL REFERENCES document_types(id) ON DELETE RESTRICT,
    file_name         TEXT        NOT NULL,
    drive_file_id     TEXT        NOT NULL,
    drive_url         TEXT        NOT NULL,
    uploaded_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_employee_document_type UNIQUE (employee_id, document_type_id)
);

-- ---------------------------------------------------------------------------
-- 6. Índices
-- ---------------------------------------------------------------------------

CREATE INDEX idx_employees_is_active   ON employees(is_active);
CREATE INDEX idx_employees_group_id    ON employees(group_id);
CREATE INDEX idx_documents_employee_id ON documents(employee_id);
CREATE INDEX idx_groups_parent_id      ON groups(parent_id);
CREATE INDEX idx_doctypes_category     ON document_types(category, order_index);

-- ---------------------------------------------------------------------------
-- 7. Datos iniciales: document_types
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
('REGISTRO_CIVIL',        'Registro Civil y/o Tarjeta Hijos',                                      'INGRESO', 12),
('CEDULA_CONYUGE',        'Cédula Cónyuge 150%',                                                   'INGRESO', 13),
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

-- Tipo especial
('EXTRA',                 'Documento Extra',                                                        'INGRESO', 99),

-- Categoría RETIRO
('CARTA_RETIRO',           'Carta de Retiro',            'RETIRO', 1),
('ENTREVISTA_RETIRO',      'Entrevista de Retiro',       'RETIRO', 2),
('RETIRO_ARL',             'Retiro ARL',                 'RETIRO', 3),
('LIQUIDACION',            'Liquidación',                'RETIRO', 4),
('ORDEN_EXAMEN_EGRESO',    'Orden Examen de Egreso',     'RETIRO', 5),
('CERT_LABORAL_RETIRO',    'Certificación Laboral',      'RETIRO', 6),
('CARTA_RETIRO_CESANTIAS', 'Carta de Retiro de Cesantías','RETIRO', 7),
('CERT_APORTES',           'Certificado Aportes',        'RETIRO', 8);

-- ---------------------------------------------------------------------------
-- 8. Datos iniciales: groups (nivel 1)
-- ---------------------------------------------------------------------------

INSERT INTO groups (id, name, parent_id) VALUES
('00000001-0000-0000-0000-000000000001', 'Tunja',          NULL),
('00000001-0000-0000-0000-000000000002', 'Barbosa',        NULL),
('00000001-0000-0000-0000-000000000003', 'Chiquinquirá',   NULL),
('00000001-0000-0000-0000-000000000004', 'Estudiantes',    NULL),
('00000001-0000-0000-0000-000000000005', 'Retirados',      NULL);

-- Nivel 2: hijos de Tunja
INSERT INTO groups (name, parent_id) VALUES
('Asesores',        '00000001-0000-0000-0000-000000000001'),
('Logísticos',      '00000001-0000-0000-0000-000000000001'),
('Administrativos', '00000001-0000-0000-0000-000000000001');

-- Nivel 2: hijos de Barbosa
INSERT INTO groups (name, parent_id) VALUES
('Asesores',        '00000001-0000-0000-0000-000000000002'),
('Logísticos',      '00000001-0000-0000-0000-000000000002'),
('Administrativos', '00000001-0000-0000-0000-000000000002');

-- Nivel 2: hijos de Chiquinquirá
INSERT INTO groups (name, parent_id) VALUES
('Asesores',        '00000001-0000-0000-0000-000000000003'),
('Logísticos',      '00000001-0000-0000-0000-000000000003'),
('Administrativos', '00000001-0000-0000-0000-000000000003');

-- Nivel 2: hijos de Estudiantes
INSERT INTO groups (name, parent_id) VALUES
('SENA',            '00000001-0000-0000-0000-000000000004'),
('UPTC',            '00000001-0000-0000-0000-000000000004'),
('Santo Tomás',     '00000001-0000-0000-0000-000000000004');

-- Nivel 2: hijos de Retirados
INSERT INTO groups (name, parent_id) VALUES
('Tunja',           '00000001-0000-0000-0000-000000000005'),
('Barbosa',         '00000001-0000-0000-0000-000000000005'),
('Chiquinquirá',    '00000001-0000-0000-0000-000000000005');
