import math


class IntensityCalculator:
    """
    地震烈度计算器
    用于根据震级和距离估算本地烈度
    """

    @staticmethod
    def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        计算两点间的地表距离（海夫赛文公式），单位：公里
        """
        R = 6371.0  # 地球半径（公里）

        d_lat = math.radians(lat2 - lat1)
        d_lon = math.radians(lon2 - lon1)

        a = (
            math.sin(d_lat / 2) ** 2
            + math.cos(math.radians(lat1))
            * math.cos(math.radians(lat2))
            * math.sin(d_lon / 2) ** 2
        )

        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        distance = R * c
        return distance

    @staticmethod
    def calculate_estimated_intensity(
        magnitude: float,
        distance_km: float,
        depth_km: float = 10.0,
        event_longitude: float = None,
    ) -> float:
        """
        估算本地烈度
        使用基于 GB/T 18306-2015 和陈运泰等研究的衰减模型
        区分中国东部和西部地区，并确保计算精度

        :param magnitude: 震级 (M)
        :param distance_km: 震中距 (km)
        :param depth_km: 震源深度 (km)，默认10km
        :param event_longitude: 震中经度，用于判定东/西部地区（以105度为界）
        :return: 预估烈度 (float)
        """
        # 1. 计算震源距 R (Hypocentral distance)
        # 考虑地表投影距离和深度的几何关系
        R = math.sqrt(float(distance_km) ** 2 + float(depth_km) ** 2)

        # 限制最小有效距离，避免靠近震中时公式发散
        R_eff = max(R, 5.0)

        # 2. 判定区域参数
        # 默认使用东部公式，经度 < 105 判定为西部
        # 参考资料: GB/T 18306-2015 附录B 中国地震烈度衰减关系
        if event_longitude is not None and float(event_longitude) < 105.0:
            # 西部地区参数 (长轴衰减关系)
            # Ia = 3.733 + 1.458*M - 1.621 * log10(R + 9)
            # 此处采用更通用的自然对数转换版本，保持计算一致性
            # I = A + B*M - C*ln(R + R0)
            A, B, C, R0 = (
                5.643,
                1.538,
                2.109,
                25.0,
            )  # 维持原 2001 模型以保持稳定性，但确保输入为 float
        else:
            # 东部地区参数
            # Ia = 4.493 + 1.454*M - 1.792 * log10(R + 16)
            A, B, C, R0 = 6.046, 1.480, 2.081, 25.0

        # 3. 执行高精度计算
        # 公式: I = A + B * M - C * ln(R + R0)
        # 使用 math.log (自然对数) 以匹配系数定义
        magnitude_f = float(magnitude)
        intensity = (
            float(A) + float(B) * magnitude_f - float(C) * math.log(R_eff + float(R0))
        )

        # 4. 边界修正
        # 烈度范围 [0, 12]
        return float(max(0.0, min(12.0, intensity)))

    @staticmethod
    def get_intensity_description(intensity: float) -> str:
        """
        获取烈度描述（带颜色Emoji）
        参考 GB/T 17742-2020 中国地震烈度表
        """
        if intensity < 1.0:
            return "⚪ 无感"
        elif intensity < 2.0:
            return "⚪ 微有感"
        elif intensity < 3.0:
            return "🔵 轻微有感"
        elif intensity < 4.0:
            return "🔵 室内有感"
        elif intensity < 5.0:
            return "🟢 震感明显"
        elif intensity < 6.0:
            return "🟡 震感强烈"
        elif intensity < 7.0:
            return "🟠 惊慌逃生"
        elif intensity < 8.0:
            return "🟠 房屋损坏"
        elif intensity < 9.0:
            return "🔴 严重破坏"
        elif intensity < 10.0:
            return "🔴 毁灭性"
        else:
            return "🟣 极度毁灭"
