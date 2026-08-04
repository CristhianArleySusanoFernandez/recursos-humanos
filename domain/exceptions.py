from uuid import UUID


class DomainError(Exception):
    """Raíz de todas las excepciones de dominio."""


class EmployeeNotFoundError(DomainError):
    def __init__(self, employee_id: UUID) -> None:
        super().__init__(f"Empleado con id '{employee_id}' no encontrado.")
        self.employee_id = employee_id


class InactiveEmployeeError(DomainError):
    def __init__(self, employee_id: UUID) -> None:
        super().__init__(
            f"El empleado '{employee_id}' está inactivo. Reactívalo antes de continuar."
        )
        self.employee_id = employee_id


class EmployeeIsActiveError(DomainError):
    def __init__(self, employee_name: str) -> None:
        super().__init__(
            f"No se puede eliminar a '{employee_name}' porque está activo. "
            "Desactívalo primero."
        )
        self.employee_name = employee_name


class DocumentNotFoundError(DomainError):
    def __init__(self, employee_id: UUID, document_type_id: UUID) -> None:
        super().__init__(
            f"El empleado '{employee_id}' no tiene documento del tipo '{document_type_id}'."
        )
        self.employee_id = employee_id
        self.document_type_id = document_type_id


class DocumentTypeNotFoundError(DomainError):
    def __init__(self, identifier: str) -> None:
        super().__init__(f"Tipo de documento '{identifier}' no encontrado.")
        self.identifier = identifier


class GroupNotFoundError(DomainError):
    def __init__(self, group_id: UUID) -> None:
        super().__init__(f"Grupo con id '{group_id}' no encontrado.")
        self.group_id = group_id


class GroupHasEmployeesError(DomainError):
    def __init__(self, message: str) -> None:
        super().__init__(message)


class GroupHasChildrenError(DomainError):
    def __init__(self, group_name: str) -> None:
        super().__init__(
            f"No se puede eliminar '{group_name}' porque tiene subgrupos. "
            "Elimina los subgrupos primero."
        )
        self.group_name = group_name
