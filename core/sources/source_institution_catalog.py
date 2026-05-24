"""
数据源机构目录查询服务。
将机构级查询视图从数据源目录中迁出，避免注册中心继续承担查询投影职责。
"""

from __future__ import annotations

from .source_catalog import SOURCE_CATALOG, get_source_ids_by_query_group


def get_institution_catalog(
    query_group: str = "eew",
) -> dict[str, dict[str, str | list[str]]]:
    """从数据源目录构建机构分组视图。

    返回结果会把同一查询分组下的数据源按机构聚合，供状态查询与管理端展示复用。
    """
    result: dict[str, dict[str, str | list[str]]] = {}
    # 按照查询分组筛选并遍历数据源标识列表
    for source_id in get_source_ids_by_query_group(query_group):
        entry = SOURCE_CATALOG[source_id]
        institution_key = (entry.institution_key or "").strip()
        if not institution_key:
            continue  # 忽略未指定机构归属的源，避免产生无名机构分组

        # 聚合机构显示名称和缩写名称
        item = result.setdefault(
            institution_key,
            {
                "display_name": entry.institution_display_name or institution_key,
                "active_name": entry.institution_active_name
                or entry.institution_display_name
                or institution_key,
                "source_ids": [],
            },
        )
        item_source_ids = item["source_ids"]
        # 执行去重逻辑，确保列表内数据源标识不重复
        if isinstance(item_source_ids, list) and source_id not in item_source_ids:
            item_source_ids.append(source_id)
    return result


__all__ = ["get_institution_catalog"]
