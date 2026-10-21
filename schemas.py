"""Contrato de datos del pipeline: la forma exacta que debe tener la salida."""

from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


class NivelCriticidad(StrEnum):
    BAJA = "baja"
    MEDIA = "media"
    ALTA = "alta"


class EntidadesTecnicas(BaseModel):
    """Información técnica extraída de un texto."""

    # Las descripciones se envían al modelo junto con el esquema: son
    # instrucciones sobre qué debe poner en cada campo.
    tecnologias: list[str] = Field(
        description="Tecnologías, lenguajes, frameworks o servicios mencionados en el texto."
    )
    nivel_de_criticidad: NivelCriticidad = Field(
        description="Gravedad: 'baja', 'media' o 'alta'."
    )
    resumen_tecnico: str = Field(
        description="Resumen técnico breve del texto, en una o dos frases."
    )

    @field_validator("tecnologias")
    @classmethod
    def tecnologias_no_vacias(cls, valor: list[str]) -> list[str]:
        limpias = [t.strip() for t in valor if t.strip()]
        if not limpias:
            raise ValueError("tecnologias no puede estar vacía")
        return limpias

    @field_validator("resumen_tecnico")
    @classmethod
    def resumen_no_vacio(cls, valor: str) -> str:
        if not valor.strip():
            raise ValueError("resumen_tecnico no puede estar vacío")
        return valor.strip()
