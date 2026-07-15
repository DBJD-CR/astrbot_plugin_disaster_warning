"""
P/S 波走时查询服务。

基于 TravelTimes.js 中的 JMA2001 与 JB 走时模型，
根据震源深度与震中距进行双线性插值，估算 P 波与 S 波的预计走时秒数。

模型选择规则：
- 震中距 <= 2000 km：使用 jma2001 模型（近中距/区域地震）
- 震中距 > 2000 km：使用 jb 模型（远震）
"""

from __future__ import annotations

from dataclasses import dataclass

from astrbot.api import logger

from .travel_time_loader import TravelTimeModel, get_model


@dataclass(slots=True)
class TravelTimeResult:
    """走时查询结果。

    Attributes:
        p_travel_sec: P 波走时（秒），查询失败时为 None。
        s_travel_sec: S 波走时（秒），查询失败时为 None。
        model_name: 实际使用的模型名。
    """

    p_travel_sec: float | None
    s_travel_sec: float | None
    model_name: str = ""


class TravelTimeService:
    """P/S 波走时查询服务。"""

    # jma2001 模型的最大适用震中距
    JMA2001_MAX_DISTANCE_KM = 2000.0

    @staticmethod
    def _bilinear_interpolate(
        table: list[list[float]],
        depths: list[float],
        distances: list[float],
        depth_km: float,
        distance_km: float,
    ) -> float | None:
        """在 depths × distances 网格上对 table 做双线性插值。

        Args:
            table: 二维走时表，table[depth_i][dist_j]。
            depths: 深度轴序列。
            distances: 距离轴序列。
            depth_km: 目标震源深度。
            distance_km: 目标震中距。

        Returns:
            插值后的走时秒数，数据不足时返回 None。
        """
        if not table or not depths or not distances:
            return None

        n_depths = len(depths)
        n_dists = len(distances)
        # 校验表维度与轴长度一致
        if len(table) < n_depths:
            return None
        for row in table[:n_depths]:
            if len(row) < n_dists:
                return None

        # 将目标值钳制到网格范围内，避免越界
        d = max(depths[0], min(depths[-1], float(depth_km)))
        r = max(distances[0], min(distances[-1], float(distance_km)))

        # 定位深度方向的下界索引
        i0 = 0
        for idx in range(n_depths - 1):
            if depths[idx] <= d <= depths[idx + 1]:
                i0 = idx
                break
        else:
            # d 超出上界时取最后一段
            i0 = max(0, n_depths - 2)
        i1 = min(i0 + 1, n_depths - 1)

        # 定位距离方向的下界索引
        j0 = 0
        for idx in range(n_dists - 1):
            if distances[idx] <= r <= distances[idx + 1]:
                j0 = idx
                break
        else:
            j0 = max(0, n_dists - 2)
        j1 = min(j0 + 1, n_dists - 1)

        # 四个角点的走时值
        d0, d1 = depths[i0], depths[i1]
        r0, r1 = distances[j0], distances[j1]
        v00 = table[i0][j0]
        v01 = table[i0][j1]
        v10 = table[i1][j0]
        v11 = table[i1][j1]

        # 深度方向与距离方向的插值权重
        td = (d - d0) / (d1 - d0) if d1 != d0 else 0.0
        tr = (r - r0) / (r1 - r0) if r1 != r0 else 0.0

        # 双线性插值公式
        v0 = v00 + (v01 - v00) * tr
        v1 = v10 + (v11 - v10) * tr
        return v0 + (v1 - v0) * td

    @staticmethod
    def _select_model(distance_km: float) -> tuple[str, TravelTimeModel | None]:
        """根据震中距选择走时模型。"""
        if distance_km <= TravelTimeService.JMA2001_MAX_DISTANCE_KM:
            return "jma2001", get_model("jma2001")
        return "jb", get_model("jb")

    @classmethod
    def lookup(cls, depth_km: float, distance_km: float) -> TravelTimeResult:
        """查询 P/S 波走时。

        Args:
            depth_km: 震源深度（km）。
            distance_km: 震中距（km）。

        Returns:
            走时查询结果，数据不足时对应字段为 None。
        """
        if distance_km < 0:
            return TravelTimeResult(None, None, "")

        model_name, model = cls._select_model(float(distance_km))
        if model is None or not model.depths or not model.distances:
            return TravelTimeResult(None, None, model_name)

        p_sec = cls._bilinear_interpolate(
            model.p_times,
            model.depths,
            model.distances,
            float(depth_km),
            float(distance_km),
        )
        s_sec = cls._bilinear_interpolate(
            model.s_times,
            model.depths,
            model.distances,
            float(depth_km),
            float(distance_km),
        )

        if p_sec is None and s_sec is None:
            logger.debug(
                f"[灾害预警] 走时查询失败: depth={depth_km}km, "
                f"dist={distance_km}km, model={model_name}"
            )

        return TravelTimeResult(
            p_travel_sec=p_sec,
            s_travel_sec=s_sec,
            model_name=model_name,
        )


__all__ = ["TravelTimeService", "TravelTimeResult"]
