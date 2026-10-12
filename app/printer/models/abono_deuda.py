from pydantic import BaseModel
from typing import Optional, List


class AbonoCuota(BaseModel):
    cuota_numero: int
    abono_numero: int
    fecha_hora: str            # "01/10/2026 12:32:31"
    monto: float
    metodo_pago: str
    saldo_restante: float


class AbonoDeudaPrintRequest(BaseModel):
    # campos del meta que ya mandas (company_id, etc.)
    company_id: Optional[str] = None
    code_establecimiento: Optional[str] = None
    impreso_por: Optional[str] = None

    credito_id: str            # "419397AB"
    cliente_nombre: str
    cliente_identificacion: str
    abonos: List[AbonoCuota]   # uno por cuota afectada
    copies: int = 1