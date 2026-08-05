"""Tests for the device name that prefixes every friendly name.

Entities use ``_attr_has_entity_name``, so Home Assistant composes friendly
names as "<device name> <entity name>". The device name is therefore the only
place the integration gets to say where the data came from.
"""

from unittest.mock import MagicMock

import pytest

from custom_components.spond_tracker.calendar import SpondCalendarEntity
from custom_components.spond_tracker.coordinator import CoordinatorData
from custom_components.spond_tracker.sensor import SpondEventsSensor, SpondTasksSensor
from custom_components.spond_tracker.spond_helpers import device_name_for

MEMBER = {"canonical": "alice", "display_name": "Alice Smith"}


def _coordinator():
    entry = MagicMock(spec=["entry_id"])
    entry.entry_id = "test_entry"
    coord = MagicMock()
    coord.data = CoordinatorData(events={"alice": []}, tasks={"alice": []})
    coord.last_update_success = True
    coord.strings = {}
    coord.entry = entry
    return coord


@pytest.mark.parametrize(
    ("display_name", "expected"),
    [
        ("Alice Smith", "Spond - Alice"),
        ("Alice", "Spond - Alice"),
        ("Alice Mary Smith", "Spond - Alice"),
        ("  Alice Smith  ", "Spond - Alice"),
    ],
)
def test_device_name_uses_first_name_only(display_name: str, expected: str) -> None:
    assert device_name_for(display_name) == expected


@pytest.mark.parametrize("display_name", ["", "   ", None])
def test_device_name_degrades_without_a_usable_name(display_name) -> None:
    """A member with no usable display name must not yield a dangling separator."""
    assert device_name_for(display_name) == "Spond"


def test_every_platform_uses_the_same_device_name() -> None:
    """All entities for a member must land on one device, named consistently.

    They share an identifier, so a mismatched name would make the platforms
    fight over what the device is called.
    """
    coord = _coordinator()
    entities = [
        SpondCalendarEntity(coord, MEMBER),
        SpondEventsSensor(coord, MEMBER),
        SpondTasksSensor(coord, MEMBER),
    ]
    names = {e._attr_device_info["name"] for e in entities}
    identifiers = {frozenset(e._attr_device_info["identifiers"]) for e in entities}

    assert names == {"Spond - Alice"}
    assert len(identifiers) == 1


def test_device_name_does_not_leak_into_entity_names() -> None:
    """The prefix belongs to the device, never repeated on the entity.

    Repeating it is how the name-doubling bug looked, so guard both halves.
    """
    coord = _coordinator()
    cal = SpondCalendarEntity(coord, MEMBER)
    assert cal._attr_name is None

    for cls in (SpondEventsSensor, SpondTasksSensor):
        sensor = cls(coord, MEMBER)
        assert not getattr(sensor, "_attr_translation_placeholders", None)
