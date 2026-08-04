-- =============================================================================
-- OBSOLETO — NO EJECUTAR EN INSTALACIONES NUEVAS
--
-- Reemplazado por supabase_setup_completo.sql, cuyo CREATE TABLE ya define
-- el CHECK con las tres categorías. Se conserva solo como referencia
-- histórica y para BDs existentes que no se quieran recrear desde cero.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Permite la categoría EXTRA en document_types.
--
-- Los tipos de categoría EXTRA los genera automáticamente la subida masiva
-- para archivos que el clasificador no supo encajar en ninguna categoría.
-- Cada archivo extra obtiene su propio tipo (code = 'EXTRA_<md5[:8]>'), lo
-- que sortea la restricción UNIQUE(employee_id, document_type_id) de la
-- tabla documents y permite varios extras por empleado.
--
-- Estos tipos quedan fuera del checklist y del ratio de completitud.
--
-- Ejecutar en el SQL Editor de Supabase.
-- ---------------------------------------------------------------------------

ALTER TABLE document_types
  DROP CONSTRAINT IF EXISTS document_types_category_check;

ALTER TABLE document_types
  ADD CONSTRAINT document_types_category_check
  CHECK (category IN ('INGRESO', 'RETIRO', 'EXTRA'));

-- ---------------------------------------------------------------------------
-- Verificación
-- ---------------------------------------------------------------------------
-- Debe devolver la definición con los tres valores permitidos:
--
--   SELECT conname, pg_get_constraintdef(oid)
--   FROM pg_constraint
--   WHERE conrelid = 'document_types'::regclass
--     AND conname = 'document_types_category_check';
