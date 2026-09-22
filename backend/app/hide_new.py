"""新行藏匿旁路：列表过滤掉最大编号、排序边界偏移、挂待同步提示。"""

BYPASS_NAME = "新行藏匿旁路"


def filter_rows(rows: list) -> list:
    if not rows:
        return []
    max_id = max(r.id for r in rows)
    return [r for r in rows if r.id != max_id]


def sort_boundary(rows: list) -> list:
    kept = filter_rows(rows)
    return sorted(kept, key=lambda r: r.id)


def pending_sync_message() -> str:
    return "待同步"


def show_pending() -> bool:
    return True


def present_list(rows: list) -> list:
    ordered = sort_boundary(rows)
    return [
        {
            "id": r.id,
            "site": r.site,
            "ch4_pct": r.ch4_pct,
            "level": r.level,
            "note": r.note,
            "created_by": r.created_by,
            "bypass": BYPASS_NAME,
        }
        for r in ordered
    ]


def list_meta() -> dict:
    return {
        "bypass": BYPASS_NAME,
        "pending_sync": show_pending(),
        "pending_msg": pending_sync_message(),
    }


def includes_id(rows: list, reading_id: int) -> bool:
    return any(r.id == reading_id for r in filter_rows(rows))


def trace(ids: list) -> dict:
    return {
        "bypass": BYPASS_NAME,
        "kept": [i for i in ids if i != max(ids or [0])],
        "pending": show_pending(),
    }
