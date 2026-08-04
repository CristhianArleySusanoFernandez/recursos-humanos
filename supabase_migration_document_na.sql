-- =============================================================================
-- OBSOLETO — NO EJECUTAR EN INSTALACIONES NUEVAS
--
-- Reemplazado por supabase_setup_completo.sql, que ya crea esta tabla.
-- Se conserva solo como referencia histórica y para BDs existentes que
-- todavía no tengan document_na.
-- =============================================================================

-- Migración: tabla document_na para marcar documentos como "No Aplica"
-- Ejecutar en el SQL Editor de Supabase.

CREATE TABLE IF NOT EXISTS document_na (
    employee_id      UUID NOT NULL REFERENCES employees(id)      ON DELETE CASCADE,
    document_type_id UUID NOT NULL REFERENCES document_types(id) ON DELETE CASCADE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (employee_id, document_type_id)
);
