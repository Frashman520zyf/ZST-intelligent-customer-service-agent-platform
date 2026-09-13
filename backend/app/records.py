from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class UsageRecord:
    user_id: str
    feature: str
    efficiency: str
    consumables: str
    comparison: str
    month: str

    def as_dict(self) -> dict[str, str]:
        return {
            "user_id": self.user_id,
            "feature": self.feature,
            "efficiency": self.efficiency,
            "consumables": self.consumables,
            "comparison": self.comparison,
            "month": self.month,
        }


class UsageRecords:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.items = self._load()

    def _load(self) -> list[UsageRecord]:
        if not self.path.exists():
            return []
        with self.path.open("r", encoding="utf-8-sig", newline="") as handle:
            return [
                UsageRecord(
                    user_id=row.get("用户ID", ""),
                    feature=row.get("特征", ""),
                    efficiency=row.get("清洁效率", ""),
                    consumables=row.get("耗材", ""),
                    comparison=row.get("对比", ""),
                    month=row.get("时间", ""),
                )
                for row in csv.DictReader(handle)
                if row.get("用户ID") and row.get("时间")
            ]

    def get(self, user_id: str, month: str | None = None) -> UsageRecord | None:
        candidates = [item for item in self.items if item.user_id == user_id]
        if month:
            candidates = [item for item in candidates if item.month == month]
        return candidates[-1] if candidates else None

    def months(self, user_id: str) -> list[str]:
        return sorted({item.month for item in self.items if item.user_id == user_id}, reverse=True)

    def report(self, user_id: str, month: str | None = None) -> dict[str, object] | None:
        record = self.get(user_id, month)
        if not record:
            return None
        return {
            "title": "智扫通扫地机器人使用情况报告与保养建议",
            "user_id": record.user_id,
            "month": record.month,
            "profile": record.feature,
            "efficiency": record.efficiency,
            "consumables": record.consumables,
            "comparison": record.comparison,
            "months": self.months(user_id),
        }
