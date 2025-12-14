"""
FERegions - 全球地震区域中文翻译模块
基于 Flinn-Engdahl (F-E) 地震区划标准
将全球坐标转换为中文地名描述

原始数据来源: kanameishi-dev/src/utils/FERegions.js
转换为 Python 适用于灾害预警插件
"""

import json
import os
from typing import Optional

# 懒加载数据
_FE_NUMBERS = None
_FE_NAMES = None
_DATA_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "resources", "fe_regions_data.json")


def _load_data():
    """懒加载 FE Regions 数据"""
    global _FE_NUMBERS, _FE_NAMES
    
    if _FE_NUMBERS is not None and _FE_NAMES is not None:
        return
    
    try:
        with open(_DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            _FE_NUMBERS = data['fe_numbers']
            _FE_NAMES = data['fe_names']
    except FileNotFoundError:
        # 如果数据文件不存在，使用内嵌的简化数据
        _FE_NUMBERS = [[729] * 360 for _ in range(180)]  # 默认为"未定义"
        _FE_NAMES = ["未定义"] * 729


def get_fe_name(lat: float, lng: float, add_suffix: bool = True) -> Optional[str]:
    """
    根据经纬度获取 F-E 区域中文名称
    
    参数:
        lat: 纬度 (-90 ~ 90)
        lng: 经度 (-180 ~ 180)
        add_suffix: 是否添加"附近"后缀，默认True
    
    返回:
        中文地名，如 "日本本州东南附近"
        如果坐标无效或数据未加载，返回 None
    
    示例:
        >>> get_fe_name(35.6, 139.7)
        '日本本州东部附近'
        >>> get_fe_name(39.9, 116.4, add_suffix=False)
        '中国华北地区'
    """
    _load_data()
    
    if _FE_NUMBERS is None or _FE_NAMES is None:
        return None
    
    try:
        # 坐标转换: (-90~90, -180~180) -> (0~179, 0~359)
        lat_i = min(max(int(lat + 90), 0), 179)
        lng_i = min(max(int(lng + 180), 0), 359)
        
        # 查询区域编号
        region_number = _FE_NUMBERS[lat_i][lng_i]
        
        # 转换为地名 (编号从1开始，数组索引从0开始)
        if 1 <= region_number <= len(_FE_NAMES):
            region_name = _FE_NAMES[region_number - 1]
            
            # 过滤"未定义"区域
            if region_name == "未定义":
                return None
            
            # 添加"附近"后缀
            if add_suffix and not region_name.endswith("附近"):
                region_name += "附近"
            
            return region_name
        
        return None
        
    except (IndexError, ValueError, TypeError):
        return None


def translate_place_name(
    original_name: str, 
    lat: float, 
    lng: float, 
    fallback_to_original: bool = True
) -> str:
    """
    翻译地名：优先使用 F-E 区域翻译，失败则返回原始地名
    
    参数:
        original_name: 原始地名（通常是英文）
        lat: 纬度
        lng: 经度
        fallback_to_original: 翻译失败时是否返回原始地名，默认True
    
    返回:
        翻译后的中文地名，或原始地名
    
    示例:
        >>> translate_place_name("near the east coast of Honshu, Japan", 35.6, 139.7)
        '日本本州东部附近'
        >>> translate_place_name("Unknown location", 0, 0, fallback_to_original=False)
        ''
    """
    # 尝试 F-E 区域翻译
    chinese_name = get_fe_name(lat, lng)
    
    if chinese_name:
        return chinese_name
    
    # 翻译失败，返回原始地名或空字符串
    return original_name if fallback_to_original else ""


def is_data_loaded() -> bool:
    """检查数据是否已加载"""
    return _FE_NUMBERS is not None and _FE_NAMES is not None


def get_region_stats() -> dict:
    """
    获取区域数据统计信息
    
    返回:
        包含统计信息的字典
    """
    _load_data()
    
    if _FE_NUMBERS is None or _FE_NAMES is None:
        return {
            "loaded": False,
            "total_names": 0,
            "grid_rows": 0,
            "grid_cols": 0,
            "unique_regions": 0
        }
    
    # 统计唯一区域
    flat_numbers = [num for row in _FE_NUMBERS for num in row]
    unique_regions = len(set(flat_numbers))
    
    return {
        "loaded": True,
        "total_names": len(_FE_NAMES),
        "grid_rows": len(_FE_NUMBERS),
        "grid_cols": len(_FE_NUMBERS[0]) if _FE_NUMBERS else 0,
        "unique_regions": unique_regions,
        "grid_precision": "1° × 1°",
        "coverage": "全球 (-90°~90°, -180°~180°)"
    }


# 测试代码
if __name__ == "__main__":
    # 测试几个知名地震区域
    test_cases = [
        (35.6, 139.7, "东京"),
        (39.9, 116.4, "北京"),
        (34.0, -118.2, "洛杉矶"),
        (-33.9, 18.4, "开普敦"),
        (51.5, -0.1, "伦敦"),
    ]
    
    print("=== FE Regions 翻译测试 ===")
    for lat, lng, city in test_cases:
        result = get_fe_name(lat, lng)
        print(f"{city} ({lat}, {lng}): {result}")
    
    print("\n=== 数据统计 ===")
    stats = get_region_stats()
    for key, value in stats.items():
        print(f"{key}: {value}")
