"""Base entities for Flyt Foresatt."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, FRONTEND_URL
from .coordinator import ChildData, FlytCoordinator


class FlytChildEntity(CoordinatorEntity[FlytCoordinator]):
    """An entity that belongs to one child."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: FlytCoordinator, child_key: str, key: str) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self.child_key = child_key
        child = self.child
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{child_key}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{coordinator.config_entry.entry_id}_{child_key}")},
            name=child.first_name if child else child_key,
            manufacturer="Visma Flyt",
            model=(child.school_name if child else None) or "Flyt Skole",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=FRONTEND_URL,
        )

    @property
    def child(self) -> ChildData | None:
        """Return the child's current data."""
        return self.coordinator.data.children.get(self.child_key)

    @property
    def available(self) -> bool:
        """Entity is available while the child is present in the data."""
        return super().available and self.child is not None


class FlytAccountEntity(CoordinatorEntity[FlytCoordinator]):
    """An entity that belongs to the guardian account."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: FlytCoordinator, key: str) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Visma Flyt",
            model="Flyt Foresatt",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=FRONTEND_URL,
        )
