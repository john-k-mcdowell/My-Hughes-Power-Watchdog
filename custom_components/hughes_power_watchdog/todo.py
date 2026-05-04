"""Todo platform for Hughes Power Watchdog integration."""

from __future__ import annotations

import logging

from homeassistant.components.todo import (
    TodoItem,
    TodoItemStatus,
    TodoListEntity,
    TodoListEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import HughesPowerWatchdogCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Hughes Power Watchdog todo list."""
    coordinator: HughesPowerWatchdogCoordinator = hass.data[DOMAIN][
        config_entry.entry_id
    ]
    async_add_entities([HughesPowerWatchdogErrorList(coordinator)])


class HughesPowerWatchdogErrorList(
    CoordinatorEntity[HughesPowerWatchdogCoordinator], TodoListEntity
):
    """Home Assistant To-Do List Entity for Watchdog error log.

    V2 devices: supports marking items complete (deletes by record ID)
                and explicit trash-can deletion.
    V1 devices: read-only display — deletion requires V1 command wire
                format to be resolved before it can be enabled.
    """

    _attr_has_entity_name = True
    _attr_icon = "mdi:alert-circle-outline"
    _attr_name = "Error Log"

    def __init__(self, coordinator: HughesPowerWatchdogCoordinator) -> None:
        """Initialize the todo list."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_error_log"
        self._attr_device_info = coordinator.device_info

        if coordinator.is_v2_protocol:
            self._attr_supported_features = (
                TodoListEntityFeature.UPDATE_TODO_ITEM
                | TodoListEntityFeature.DELETE_TODO_ITEM
            )
        else:
            # V1 delete commands are not yet functional — read-only for now
            self._attr_supported_features = TodoListEntityFeature(0)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            self.coordinator.monitoring_enabled
            and self.coordinator.last_update_success
        )

    @property
    def todo_items(self) -> list[TodoItem] | None:
        """Build the To-Do list from parsed error records."""
        error_list = self.coordinator.data.get("errors", []) if self.coordinator.data else []
        return [
            TodoItem(
                uid=str(error["record_id"]),
                summary=f"{error['description']} (E{error['error_code']})",
                description=f"Started: {error['start_time']}\nEnded: {error['end_time']}",
                status=TodoItemStatus.NEEDS_ACTION,
            )
            for error in error_list
        ]

    async def async_update_todo_item(self, item: TodoItem) -> None:
        """Handle checkbox click — delete the record from the device (V2 only)."""
        if item.status == TodoItemStatus.COMPLETED:
            record_id = int(item.uid)
            success = await self.coordinator.async_delete_error_record(record_id)
            if success:
                self.coordinator._errors = [
                    e for e in self.coordinator._errors if e["record_id"] != record_id
                ]
                self.coordinator.async_set_updated_data(self.coordinator._build_data_dict())

    async def async_delete_todo_items(self, uids: list[str]) -> None:
        """Handle trash-can click — delete selected records (V2 only)."""
        for uid in uids:
            record_id = int(uid)
            success = await self.coordinator.async_delete_error_record(record_id)
            if success:
                self.coordinator._errors = [
                    e for e in self.coordinator._errors if e["record_id"] != record_id
                ]
        self.coordinator.async_set_updated_data(self.coordinator._build_data_dict())
