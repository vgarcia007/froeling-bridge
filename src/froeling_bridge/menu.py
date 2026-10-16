"""p4d menu conventions, including its named weekday/time-address mapping."""

from collections import defaultdict, deque

TIME_BASES = {230: 0x00, 350: 0x38, 430: 0xB6, 573: 0xD9}
WEEKDAYS = (
    "Montag",
    "Dienstag",
    "Mittwoch",
    "Donnerstag",
    "Freitag",
    "Samstag",
    "Sonntag",
)


def menu_title(value):
    return (value or "").rstrip().removesuffix(":")


def is_time_menu(item):
    return (
        item["type"] in (42, 45)
        and item["child"] in TIME_BASES
        and menu_title(item["title"]) == "Zeiten"
    )


MENU_GROUP_TYPES = frozenset((1, 14, 33, 39, 40, 42, 45, 46, 48, 53, 55, 63))


def readable_menu(item):
    if (
        item["child"]
        or item["type"] in MENU_GROUP_TYPES
        or item["type"] in (49, 35, 34)
    ):
        return False
    if item["address"] in (9997, 9998, 9999, 65535):
        return False
    return item["type"] in (3, 70, 17, 18, 19, 22, 7) or bool(item["address"])


def visible_menu(items):
    """Apply p4d's unconditional menu filters; fresh leaf reads happen separately."""
    result = []
    for item in items:
        title = menu_title(item["title"])
        if (
            not title
            or item["type"] in (49, 35)
            or item["address"] in (9997, 9998, 9999)
        ):
            continue
        if not item["child"] and item.get("value") is None and not readable_menu(item):
            continue
        result.append(
            dict(
                item,
                title=title,
                time_program=is_time_menu(item),
                readable=readable_menu(item),
            )
        )
    return result


def menu_paths(items):
    """Resolve configured navigation paths from the same menu hierarchy as p4d."""
    children = defaultdict(list)
    for item in visible_menu(items):
        children[item["parent"]].append(item)
    paths = {1: ()}
    pending = deque([1])
    while pending:
        parent = pending.popleft()
        for item in children[parent]:
            child = item["child"]
            if child and child not in paths:
                paths[child] = paths[parent] + (
                    dict(parent=child, title=item["title"]),
                )
                pending.append(child)
    return paths


def named_search(items, paths):
    return [
        dict(item, breadcrumbs=list(paths[item["parent"]]))
        for item in items
        if item["parent"] in paths
    ]


def time_program_catalog(items):
    """Name only reachable menu instances; raw unconfigured addresses stay in the API."""
    children = defaultdict(list)
    for item in visible_menu(items):
        children[item["parent"]].append(item)
    paths = menu_paths(items)
    result = []
    for parent, path in paths.items():
        for item in children[parent]:
            if not is_time_menu(item):
                continue
            base = TIME_BASES[item["child"]] + item["address"] * 7
            if base < 0 or base + 6 > 0xDF:
                continue
            device = path[-1]["title"] if path else item["title"]
            for day, weekday in enumerate(WEEKDAYS):
                result.append(
                    dict(
                        address=base + day,
                        menu_id=item["id"],
                        parent=parent,
                        device=device,
                        path=[crumb["title"] for crumb in path],
                        weekday=weekday,
                        weekday_index=day,
                        title=f"{device} · {weekday}",
                    )
                )
    return result


def demo_time_program_catalog():
    return [
        dict(
            address=0x38,
            menu_id=0,
            parent=1,
            device="Demo-Heizkreis",
            path=["Demo-Heizkreis"],
            weekday="Montag",
            weekday_index=0,
            title="Demo-Heizkreis · Montag",
        )
    ]
