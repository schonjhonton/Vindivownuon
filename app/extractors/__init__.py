from .vix import VixProvider
from .guardahd import GuardaHDProvider

# Lista dei provider attivi che il server interrogherà.
# Inserendo le istanze qui, il ciclo nel main.py le eseguirà tutte automaticamente.
PROVIDERS = [
    VixProvider(),
    GuardaHDProvider(),
]

__all__ = ["PROVIDERS"]
