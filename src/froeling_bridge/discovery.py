"""p4d discovery without an existing SQL catalogue or hardcoded sensor addresses."""

from .menu import menu_paths, visible_menu
import logging

logger = logging.getLogger(__name__)


def discover(client, repository, progress=lambda stage: None):
    progress("status")
    client.get_status()
    firmware = client.get_firmware()
    progress("sensors")
    received_specs = client.get_value_specs(timeout=300)
    # initValueFacts -> addValueFact keys by (type, address) and updates an
    # existing entry. Later definitions therefore replace earlier metadata.
    specs = tuple({v.address: v for v in received_specs}.values())
    logger.info("Sensor discovery: %d definitions, %d distinct addresses", len(received_specs), len(specs))
    if len(specs) != len(received_specs):
        logger.warning("Sensor discovery: merged %d repeated definitions as p4d updates", len(received_specs) - len(specs))
    progress("menu")
    raw_menu = client.get_menu(timeout=300)
    menu = [
        dict(
            id=i,
            parent=m.parent,
            child=m.child,
            type=m.item_type,
            address=m.address,
            title=m.description,
            value=None,
            unit="",
            digits=None,
            min=None,
            max=None,
            def_=None,
            factor=None,
            unknown1=m.unknown1,
            unknown2=m.unknown2,
            reserved=m.reserved.hex(),
        )
        for i, m in enumerate(raw_menu, 1)
    ]
    paths = menu_paths(menu)
    visible = [m for m in visible_menu(menu) if m["parent"] in paths]
    selected_va = {m["address"] for m in visible if m["type"] in (3, 70)}
    sensors = [
        dict(
            type="VA",
            address=v.address,
            factor=v.factor,
            res1=v.data_type,
            unit=v.unit,
            title=v.description,
            usrtitle=None,
            state="A" if v.address in selected_va else "D",
            record="D",
        )
        for v in specs
    ]
    identities = {(s["type"], s["address"]) for s in sensors}
    for m in visible:
        kind = {17: "DO", 18: "AO", 19: "DI"}.get(m["type"])
        if kind and (kind, m["address"]) not in identities:
            identities.add((kind, m["address"]))
            sensors.append(
                dict(
                    type=kind,
                    address=m["address"],
                    factor=1,
                    res1=1,
                    unit="%" if kind == "AO" else "",
                    title=m["title"],
                    usrtitle=None,
                    state="A",
                    record="D",
                )
            )
    for address, title in (
        (1, "Heizungsstatus"),
        (2, "Betriebsart Kessel"),
        (3, "Datum Uhrzeit der Heizung"),
    ):
        sensors.append(
            dict(
                type="UD",
                address=address,
                factor=1,
                res1=1,
                unit="",
                title=title,
                usrtitle=None,
                state="A",
                record="D",
            )
        )
    progress("time-programs")
    times = client.get_time_ranges(timeout=30)
    # Commit only after every catalogue/list has completed successfully.
    repository.replace_catalogue(sensors, menu, firmware=firmware.version_text)
    progress("ready")
    return times
