"""Executa um comando e registra o consumo de memória (RSS, incluindo processos filhos) a cada segundo.

Uso: python scripts/05_monitor_memoria.py ROTULO COMANDO [ARGS...]
Ex.:  python scripts/05_monitor_memoria.py conv_streaming python scripts/02_csv_para_rdf_streaming.py --entidade socios
"""
import csv
import subprocess
import sys
import time
from pathlib import Path

import psutil

RAIZ = Path(__file__).resolve().parent.parent


def memoria_mb(proc):
    total = 0
    for p in [proc, *proc.children(recursive=True)]:
        try:
            total += p.memory_info().rss
        except psutil.Error:
            pass
    return total / 1e6


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    rotulo, cmd = sys.argv[1], sys.argv[2:]
    saida = RAIZ / "benchmarks" / "resultados"
    saida.mkdir(parents=True, exist_ok=True)

    proc = subprocess.Popen(cmd)
    ps = psutil.Process(proc.pid)
    pico, t0 = 0.0, time.time()
    with open(saida / f"memoria_{rotulo}.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["segundos", "rss_mb"])
        while proc.poll() is None:
            mb = memoria_mb(ps)
            pico = max(pico, mb)
            w.writerow([round(time.time() - t0, 1), round(mb, 1)])
            time.sleep(1)

    print(f"[{rotulo}] pico de memória: {pico:.0f} MB | tempo: {time.time() - t0:.0f}s | código: {proc.returncode}")
    sys.exit(proc.returncode)


if __name__ == "__main__":
    main()
