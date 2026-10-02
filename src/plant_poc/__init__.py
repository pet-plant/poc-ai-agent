"""Plant POC package."""

from plant_poc.exceptions import (
    InternalServerError,
    LLMUnavailableError,
    PetPlantError,
    make_error_response,
)

PlantPOCError = PetPlantError

__version__ = "0.1.0"
__all__ = [
    "InternalServerError",
    "LLMUnavailableError",
    "PetPlantError",
    "PlantPOCError",
    "make_error_response",
    "__version__",
]
