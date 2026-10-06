from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class InvestmentDiarySaveRequest(BaseModel):
    record_date: date
    title: str = Field(default="", max_length=200)
    body: str = Field(min_length=1)
    topics: list[str] = Field(default_factory=list, max_length=30)
    keywords: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("body")
    @classmethod
    def nonblank_body(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("日记正文不能为空")
        return value  # Preserve the original whitespace and text.

    @field_validator("title")
    @classmethod
    def single_line_title(cls, value: str) -> str:
        return " ".join(value.split())

    @field_validator("topics", "keywords")
    @classmethod
    def normalize_labels(cls, values: list[str]) -> list[str]:
        result = list(dict.fromkeys(" ".join(value.split()) for value in values if value.strip()))
        if any(len(value) > 80 for value in result):
            raise ValueError("每个主题或关键词最多 80 字")
        return result


class LayerOverrideRequest(BaseModel):
    position_layer: str
    reason: str = ""


class PositionSnapshotSaveRequest(BaseModel):
    original_code: str = ""
    original_snapshot_time: Optional[datetime] = None
    code: str
    name: str = ""
    market: str = ""
    asset_type: str = "stock"
    quantity: float = 0
    average_cost: float = 0
    current_price: float = 0
    market_value: Optional[float] = None
    currency: str = ""
    normalized_market_value: Optional[float] = None
    normalized_currency: str = ""
    exchange_rate_to_base: Optional[float] = None
    profit_loss_ratio: Optional[float] = None
    position_weight: Optional[float] = None
    position_layer: str = "中期配置仓"
    snapshot_time: datetime


class DealSaveRequest(BaseModel):
    original_deal_id: str = ""
    deal_id: str
    order_id: str = ""
    code: str
    side: str = ""
    price: float = 0
    quantity: float = 0
    deal_time: Optional[datetime] = None
    market: str = ""


class DeleteLocalDataRequest(BaseModel):
    confirmation: str = Field(description="Must be DELETE_LOCAL_DATA")
