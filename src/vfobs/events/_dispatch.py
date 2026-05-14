from vfobs.events.base import Event
from vfobs.events.schema import EVENT_CLASSES


def _type_value(cls: type[Event]) -> str:
    return cls.model_fields["type"].default  # type: ignore[no-any-return]


EVENT_TYPE_REGISTRY: dict[str, type[Event]] = {
    _type_value(cls): cls for cls in EVENT_CLASSES
}
