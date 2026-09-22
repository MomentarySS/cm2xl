"""公差判定与统计。"""

from __future__ import annotations

from .models import FeatureRecord, PassStatus, ToleranceConfig, TOLERANCE_VALUE_KEYS

_DEFAULT_TOL_ALIAS: dict[str, str] = {
    "length": "d",
    "width": "d",
    "height": "d",
    "minor_d": "d",
}


def _check_axis(value: float | None, lower: float, upper: float) -> bool | None:
    if value is None:
        return None
    return lower <= value <= upper


def _check_plus_minus(
    deviation: float | None,
    plus: float | None,
    minus: float | None,
) -> bool | None:
    """按非对称上下限判定；minus 为下限（通常为负或已归一化）。"""
    if deviation is None:
        return None
    if plus is None and minus is None:
        return None
    if plus is not None and deviation > plus:
        return False
    if minus is not None and deviation < minus:
        return False
    return True


def _axis_limit_key(feature: FeatureRecord, axis: str) -> str:
    if feature.tolerance and getattr(feature.tolerance, axis) is not None:
        return axis
    return _DEFAULT_TOL_ALIAS.get(axis, axis)


def apply_tolerance(
    features: list[FeatureRecord],
    config: ToleranceConfig,
) -> list[FeatureRecord]:
    for feature in features:
        failed: list[str] = []
        deviation = feature.deviation
        use_pm = feature.plus_tol is not None or feature.minus_tol is not None
        checked = False

        # COM 已给出超差量时优先采信
        if feature.outtol is not None and abs(float(feature.outtol)) > 1e-12:
            axis = (feature.write_axis or "D").strip().upper() or "D"
            failed.append(axis)
            feature.failed_axes = failed
            feature.status = PassStatus.FAIL
            continue

        for axis in TOLERANCE_VALUE_KEYS:
            dev_value = getattr(deviation, axis)
            if dev_value is None:
                continue

            if use_pm:
                ok = _check_plus_minus(dev_value, feature.plus_tol, feature.minus_tol)
                checked = True
                if ok is False:
                    failed.append(axis.upper())
                continue

            if feature.tolerance and getattr(feature.tolerance, axis) is not None:
                # 仅存对称半宽时的回退（旧数据）；有 plus/minus 时不会走到这里
                limit = getattr(feature.tolerance, axis)
                checked = True
                if abs(dev_value) > abs(limit):
                    failed.append(axis.upper())
                continue

            # 角度等不要套用长度类默认公差
            if axis == "angle":
                continue

            limit_key = _axis_limit_key(feature, axis)
            limits = config.axis_limits(limit_key)
            if limits is None:
                continue
            lower, upper = limits
            checked = True
            ok = _check_axis(dev_value, lower, upper)
            if ok is False:
                failed.append(axis.upper())

        feature.failed_axes = failed
        if failed:
            feature.status = PassStatus.FAIL
        elif checked:
            feature.status = PassStatus.PASS
        else:
            feature.status = PassStatus.NA

    return features


def summarize_results(features: list[FeatureRecord]) -> dict[str, int | float]:
    """统计已评价特征的合格/超差情况。NA 状态不计入合格率。"""
    judged = [f for f in features if f.status != PassStatus.NA]
    passed = sum(1 for f in judged if f.status == PassStatus.PASS)
    failed = sum(1 for f in judged if f.status == PassStatus.FAIL)
    total = passed + failed  # 明确 total = passed + failed，避免 len(judged) 语义歧义
    rate = (passed / total * 100) if total else 0.0
    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "pass_rate": round(rate, 1),
    }
