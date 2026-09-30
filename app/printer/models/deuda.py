# app/printer/models/deuda.py
from pydantic import BaseModel
from typing import List, Optional

class DeudaPrintRequest(BaseModel):
    # Ajusta los campos según la estructura de tu modelo de deuda
    cliente: Optional[str] = None
    monto: Optional[float] = 0.0
    # ... otros campos