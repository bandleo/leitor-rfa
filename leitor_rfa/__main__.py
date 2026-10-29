import sys

from .cli import main

if __name__ == "__main__":  # o `ler-rfa visualizar` abre processos (spawn) que importam este módulo de novo
    sys.exit(main())
