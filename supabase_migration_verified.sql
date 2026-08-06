-- Verificación manual de documentos.
-- Un humano marca que ya revisó ese archivo específico. Es independiente de
-- N/A y del tipo de documento, y NO afecta el cálculo de completitud.

ALTER TABLE documents ADD COLUMN verified BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE documents ADD COLUMN verified_at TIMESTAMPTZ;
