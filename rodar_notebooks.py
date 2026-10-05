"""Roda notebooks em sequência e grava a saída no próprio arquivo.

Sem argumentos, roda 04, 04b, 04c, 04d, 04e e 06.

    python rodar_notebooks.py
    python rodar_notebooks.py 04c 04e 06
    python rodar_notebooks.py notebooks/04_atribuir.ipynb

Usa o Python deste comando. Para no primeiro erro.
"""

import sys
import time
from pathlib import Path

import nbformat
from jupyter_client import KernelManager
from nbclient import NotebookClient
from nbclient.exceptions import CellExecutionError

RAIZ = Path(__file__).resolve().parent
NOTEBOOKS = RAIZ / "notebooks"
PADRAO = ["04", "04b", "04c", "04d", "04e", "06"]


class KernelDestePython(KernelManager):
    def __init__(self, **kwargs):
        kwargs.pop("kernel_name", None)
        super().__init__(**kwargs)
        self.kernel_cmd = [
            sys.executable,
            "-m",
            "ipykernel_launcher",
            "-f",
            "{connection_file}",
        ]


class Cliente(NotebookClient):
    def create_kernel_manager(self):
        self.km = KernelDestePython(config=self.config)
        return self.km

    def on_cell_start(self, cell, cell_index, **kwargs):
        if cell.cell_type != "code":
            return
        n_codigo = sum(1 for c in self.nb.cells[: cell_index + 1] if c.cell_type == "code")
        print(f"  célula {n_codigo}", flush=True)


def achar(nome):
    texto = nome.strip()
    caminho = Path(texto)
    if caminho.suffix == ".ipynb":
        if not caminho.is_absolute():
            caminho = RAIZ / caminho
        if not caminho.exists():
            raise SystemExit(f"Não achei {caminho}")
        return caminho
    achados = sorted(NOTEBOOKS.glob(f"{texto}_*.ipynb"))
    if len(achados) != 1:
        lista = ", ".join(p.name for p in achados) or "nenhum"
        raise SystemExit(f"{texto} não aponta para um notebook só: {lista}")
    return achados[0]


def rodar(caminho):
    print(f"\n{caminho.name}", flush=True)
    inicio = time.time()
    nb = nbformat.read(caminho, as_version=4)
    cliente = Cliente(
        nb,
        timeout=None,
        resources={"metadata": {"path": str(RAIZ)}},
    )
    try:
        cliente.execute()
    except CellExecutionError as erro:
        nbformat.write(nb, caminho)
        print(erro, file=sys.stderr)
        raise SystemExit(1) from erro
    nbformat.write(nb, caminho)
    minutos = (time.time() - inicio) / 60
    print(f"  pronto em {minutos:.1f} min", flush=True)


def main():
    nomes = sys.argv[1:] or PADRAO
    caminhos = [achar(nome) for nome in nomes]
    print("Sequência:")
    for caminho in caminhos:
        try:
            print(f"  {caminho.relative_to(RAIZ)}")
        except ValueError:
            print(f"  {caminho}")
    for caminho in caminhos:
        rodar(caminho)


if __name__ == "__main__":
    main()
