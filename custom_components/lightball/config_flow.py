"""Config flow for the LED Ball (Bluetooth discovery + manual)."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import DOMAIN, NAME_PREFIX, SERVICE_UUID


def _is_ball(info: BluetoothServiceInfoBleak) -> bool:
    name = info.name or ""
    return name.upper().startswith(NAME_PREFIX) or SERVICE_UUID in [
        u.lower() for u in info.service_uuids
    ]


class LightBallConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for the LED Ball."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovered_name: str | None = None

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle a flow initialized by Bluetooth discovery."""
        if not _is_ball(discovery_info) or not discovery_info.name:
            return self.async_abort(reason="not_supported")
        # The MAC rotates, so identify by the stable local name.
        await self.async_set_unique_id(discovery_info.name)
        self._abort_if_unique_id_configured()
        self._discovered_name = discovery_info.name
        self.context["title_placeholders"] = {"name": discovery_info.name}
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm a discovered device."""
        assert self._discovered_name
        if user_input is not None:
            return self.async_create_entry(
                title=self._discovered_name, data={"name": self._discovered_name}
            )
        return self.async_show_form(
            step_id="confirm", description_placeholders={"name": self._discovered_name}
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick from balls currently seen by HA Bluetooth."""
        names = sorted(
            {
                info.name
                for info in async_discovered_service_info(self.hass, connectable=True)
                if _is_ball(info) and info.name
            }
        )
        configured = {e.unique_id for e in self._async_current_entries()}
        names = [n for n in names if n not in configured]
        if not names:
            return self.async_abort(reason="no_devices_found")
        if user_input is not None:
            name = user_input["name"]
            await self.async_set_unique_id(name, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=name, data={"name": name})
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required("name"): vol.In(names)}),
        )
