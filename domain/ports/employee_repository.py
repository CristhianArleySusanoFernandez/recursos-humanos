from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from domain.entities.employee import Employee


class EmployeeRepository(ABC):

    @abstractmethod
    def get_by_id(self, employee_id: UUID) -> Employee | None: ...

    @abstractmethod
    def list_by_group(self, group_id: UUID, active_only: bool = True) -> list[Employee]: ...

    @abstractmethod
    def list_all(self, active_only: bool = True) -> list[Employee]: ...

    @abstractmethod
    def save(self, employee: Employee) -> None: ...

    @abstractmethod
    def update(self, employee: Employee) -> None: ...

    @abstractmethod
    def delete(self, employee_id: UUID) -> None: ...

    @abstractmethod
    def bulk_clear_group(self, group_id: UUID) -> None:
        """Pone group_id = NULL en todos los empleados de ese grupo."""
