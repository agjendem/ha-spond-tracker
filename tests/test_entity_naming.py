"""Guards against the entity-name doubling bug.

With ``_attr_has_entity_name = True`` Home Assistant composes the friendly name
as "<device name> <entity name>". Every device here is already named after the
member, so any entity name that repeats the member renders them twice:

    calendar  ->  "Alice Smith Alice Smith"
    sensor    ->  "Alice Smith Spond Alice Smith"

The entity name must therefore describe only the entity's role, or be None for
the device's primary entity.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock

from custom_components.spond_tracker.calendar import SpondCalendarEntity
from custom_components.spond_tracker.coordinator import CoordinatorData
from custom_components.spond_tracker.sensor import SpondEventsSensor, SpondTasksSensor

MEMBER = {"canonical": "alice", "display_name": "Alice Smith"}

TRANSLATIONS_DIR = (
    Path(__file__).resolve().parent.parent / "custom_components" / "spond_tracker" / "translations"
)


def _coordinator():
    entry = MagicMock(spec=["entry_id"])
    entry.entry_id = "test_entry"
    coord = MagicMock()
    coord.data = CoordinatorData(events={"alice": []}, tasks={"alice": []})
    coord.last_update_success = True
    coord.strings = {}
    coord.entry = entry
    return coord


def test_calendar_is_the_devices_primary_entity() -> None:
    """A None entity name makes the friendly name the device name alone."""
    cal = SpondCalendarEntity(_coordinator(), MEMBER)
    assert cal._attr_has_entity_name is True
    assert cal._attr_name is None


def test_sensors_do_not_inject_the_member_name() -> None:
    """The device prefix already carries the member; injecting it repeats it."""
    for cls in (SpondEventsSensor, SpondTasksSensor):
        sensor = cls(_coordinator(), MEMBER)
        assert sensor._attr_has_entity_name is True
        assert not getattr(sensor, "_attr_translation_placeholders", None), (
            f"{cls.__name__} sets translation placeholders; a {{name}} placeholder "
            f"is what produced 'Alice Smith Spond Alice Smith'."
        )


def test_translated_entity_names_carry_no_name_placeholder() -> None:
    """Every translation must name the role only — never the member.

    This is the half of the bug that lived in data rather than code: the entity
    name came from a translated string, so the doubling could be reintroduced by
    editing JSON without touching a single line of Python.
    """
    checked = 0
    for path in sorted(TRANSLATIONS_DIR.glob("*.json")):
        entity = json.loads(path.read_text()).get("entity", {})
        for domain, keys in entity.items():
            for key, spec in keys.items():
                name = spec.get("name", "")
                checked += 1
                assert "{name}" not in name, (
                    f"{path.name}: entity.{domain}.{key}.name is {name!r}. "
                    f"Home Assistant already prefixes the device name, so a "
                    f"{{name}} placeholder renders the member twice."
                )
    assert checked, f"no translated entity names found under {TRANSLATIONS_DIR}"
