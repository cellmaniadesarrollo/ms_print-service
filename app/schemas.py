# schemas.py
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

class Contact(BaseModel):
    value: str
    isPrimary: Optional[bool] = None

class Customer(BaseModel): 
    firstName: Optional[str] = None
    lastName: Optional[str] = None 
    idNumber: Optional[str] = None 
    contacts: Optional[List[Contact]] = None

class DeviceModel(BaseModel):
    models_name: Optional[str] = None

class Imei(BaseModel):
    imei_number: Optional[str] = None

class Device(BaseModel):
    model: Optional[Dict[str, Any]] = None  # o DeviceModel si lo defines más estricto
    imeis: Optional[List[Imei]] = None

class CreatedBy(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None

class OrderData(BaseModel):
    order_number: Optional[str] = "NA"
    entry_date: Optional[str] = None  # ISO string
    company: Optional[Dict[str, str]] = None
    branch: Optional[Dict[str, str]] = None
    customer: Optional[Customer] = None
    device: Optional[Device] = None
    detalleIngreso: Optional[str] = None
    patron: Optional[str] = None
    password: Optional[str] = None
    createdBy: Optional[CreatedBy] = None
    qr_url: Optional[str] = None  # si lo envías desde frontend, sino lo generamos
    public_id: Optional[str] = None