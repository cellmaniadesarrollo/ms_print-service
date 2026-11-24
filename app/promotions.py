# app/promotions.py
"""
Gestión centralizada de promociones (a nivel de código).

Para agregar una promoción futura:
    1. Crea un objeto Promotion en la lista PROMOTIONS.
    2. Define sus textos (lines) y su regla (is_active).
    3. Haz commit y push a GitHub. Los clientes la reciben al actualizar.

Para quitar una promoción vencida: borra o comenta su entrada.
"""

from dataclasses import dataclass
from datetime import date
from typing import Callable

# Firma de la regla: (fecha_de_hoy, total_de_la_reparacion | None) -> bool
Rule = Callable[[date, float | None], bool]


@dataclass(frozen=True)
class Promotion:
    id: str                  # identificador interno (para logs/depuración)
    lines: tuple[str, ...]   # líneas a imprimir (máx. ~32 caracteres cada una)
    is_active: Rule          # regla que decide si aplica


# ─────────────────────────────────────────────────────────────────────────────
# Reglas reutilizables
# ─────────────────────────────────────────────────────────────────────────────

def weekday_rule(weekday: int) -> Rule:
    """Aplica todos los días de la semana indicada (lunes=0 ... domingo=6)."""
    return lambda today, total: today.weekday() == weekday


def date_range_rule(start: date, end: date, min_total: float | None = None) -> Rule:
    """
    Aplica entre start y end (ambos inclusive).
    Si min_total está definido, además exige que el total de la reparación
    sea MAYOR a ese monto. Si no se conoce el total, la promo no aplica.
    """
    def rule(today: date, total: float | None) -> bool:
        if not (start <= today <= end):
            return False
        if min_total is not None:
            return total is not None and total > min_total
        return True
    return rule


# ─────────────────────────────────────────────────────────────────────────────
# CATÁLOGO DE PROMOCIONES  ← edita solo aquí
# ─────────────────────────────────────────────────────────────────────────────

PROMOTIONS: list[Promotion] = [
    Promotion(
        id="miercoles-mica-gratis",
        lines=("HOY MICA GRATIS",),
        is_active=weekday_rule(2),
    ),

    # Black Weekend 2026: viernes 27, sábado 28 y domingo 29 de noviembre
    Promotion(
        id="blackweekend-2026-estuche",
        lines=(
            "BLACK WEEKEND",
            "ESTUCHE GRATIS",
            "en reparaciones mayores a $15",
        ),
        # sin min_total: el total es 0 al recibir el equipo
        is_active=date_range_rule(date(2026, 11, 27), date(2026, 11, 29)),
    ),
]

# ─────────────────────────────────────────────────────────────────────────────
# API pública
# ─────────────────────────────────────────────────────────────────────────────

def get_active_promotions(today: date | None = None,
                          repair_total: float | None = None) -> list[Promotion]:
    today = today or date.today()
    return [p for p in PROMOTIONS if p.is_active(today, repair_total)]


def get_promotion_lines(today: date | None = None,
                        repair_total: float | None = None) -> list[str]:
    """Devuelve todas las líneas de las promos activas, listas para imprimir."""
    lines: list[str] = []
    for promo in get_active_promotions(today, repair_total):
        lines.extend(promo.lines)
    return lines