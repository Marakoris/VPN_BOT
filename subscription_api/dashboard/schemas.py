"""
Pydantic schemas for dashboard API responses.
"""

from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class UserProfile(BaseModel):
    tgid: int
    username: Optional[str] = None
    fullname: Optional[str] = None
    balance: int = 0
    referral_balance: int = 0
    lang: str = "ru"
    first_interaction: Optional[str] = None
    subscription_active: bool = False

    class Config:
        from_attributes = True


class SubscriptionStatus(BaseModel):
    active: bool = False
    expired: bool = False
    expiry_timestamp: Optional[int] = None
    expiry_date: Optional[str] = None
    days_remaining: Optional[int] = None
    subscription_months: Optional[int] = None
    subscription_price: Optional[int] = None
    autopay_enabled: bool = False
    free_trial_used: bool = False
    token: Optional[str] = None


class TrafficInfo(BaseModel):
    used_bytes: int = 0
    used_formatted: str = "0 B"
    limit_bytes: int = 0
    limit_formatted: str = "0 B"
    remaining_bytes: int = 0
    remaining_formatted: str = "0 B"
    percent_used: float = 0.0
    days_until_reset: int = 30
    exceeded: bool = False


class BypassTrafficInfo(BaseModel):
    total: int = 0
    total_formatted: str = "0 B"
    limit: int = 0
    limit_formatted: str = "0 B"
    remaining: int = 0
    remaining_formatted: str = "0 B"
    percent: float = 0.0
    exceeded: bool = False


class PaymentCreate(BaseModel):
    amount: int
    payment_system: str  # kassa, cryptobot, cryptomus, lava
    months: Optional[int] = None


class PromoApply(BaseModel):
    code: str


class PaymentRecord(BaseModel):
    id: int
    amount: float
    payment_system: str
    date: Optional[str] = None


class ReferralInfo(BaseModel):
    referral_balance: int = 0
    total_invited: int = 0
    total_earned: int = 0
    referral_link: str = ""
    minimum_withdrawal: int = 2000


class WithdrawRequest(BaseModel):
    amount: int
    payment_info: str
    communication: Optional[str] = None
