# app/printer/schemas.py

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────────────────────
# Sub-modelos compartidos
# ─────────────────────────────────────────────────────────────────────────────

class CompanySchema(BaseModel):
    model_config = {"extra": "allow"}  # ignora campos extra como status, maxUsers, etc.

    id: str
    name: str


class CurrentStatusSchema(BaseModel):
    id: int
    name: str


class CustomerSchema(BaseModel):          # ← NUEVO
    model_config = {"extra": "allow"}

    id: int
    idNumber: Optional[str] = None
    idTypeName: Optional[str] = None
    firstName: str
    lastName: str

class BrandSchema(BaseModel):
    brands_name: str


class ModelSchema(BaseModel):
    models_name: str
    brand: BrandSchema


class DeviceSchema(BaseModel):
    model_config = {"extra": "allow"}

    serial_number: Optional[str] = None
    color: Optional[str] = None
    storage: Optional[str] = None
    model: ModelSchema

class OrderSchema(BaseModel):
    model_config = {"extra": "allow"}     # ← ignora branch_id, device_id, etc.

    id: int
    public_id: str
    order_number: int
    entry_date: datetime
    company: CompanySchema
    currentStatus: CurrentStatusSchema
    customer: CustomerSchema              # ← NUEVO (estaba faltando)
    device: Optional[DeviceSchema] = None
    detalleIngreso: Optional[str] = None
    estimated_price: Optional[float] = None


class PaymentTypeSchema(BaseModel):
    model_config = {"extra": "allow"}     # ignora is_active, sort_order, icon, color

    id: int
    code: str
    name: str
    description: Optional[str] = None


class PaymentMethodSchema(BaseModel):
    model_config = {"extra": "allow"}     # ignora is_active, createdAt, updatedAt

    id: int
    name: str
    description: Optional[str] = None


class ReceivedBySchema(BaseModel):
    model_config = {"extra": "allow"}     # ignora username, dni, email, createdAt, etc.

    id: str
    first_name: str
    last_name: str
    phone: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# Modelo principal — ticket de abono/adelanto
# ─────────────────────────────────────────────────────────────────────────────

class PaymentTicketRequest(BaseModel):
    model_config = {"extra": "allow"}     # ignora order_id, payment_type_id, etc.

    id: int = Field(..., description="ID de la transacción")
    order: OrderSchema
    amount: str = Field(..., description="Monto pagado como string, ej: '120.00'")
    flow_type: str = Field(..., description="INGRESO | EGRESO")
    paymentType: PaymentTypeSchema
    paymentMethod: PaymentMethodSchema
    paid_at: datetime = Field(..., description="Fecha y hora del pago (UTC)")
    receivedBy: ReceivedBySchema
    reference: Optional[str] = Field(None, description="Referencia de caja, ej: 'EFECT-025'")
    observation: Optional[str] = Field(None, description="Nota libre sobre el pago")