# Simulador de Grafos — Petrobras

Laboratório para aprender e testar estratégias de modelagem, carga e tuning de grafos RDF. Todos os dados são **fictícios**.
O plano completo está em [ROADMAP_GRAFOS](ROADMAP_GRAFOS).

## Como rodar (passo a passo)

```powershell
python -m venv .venv                                   # 0. ambiente isolado do projeto (uma vez só)
.\.venv\Scripts\python -m pip install -r requirements.txt

.\.venv\Scripts\python scripts/01_gerar_bases_simuladas.py S      # 1. gera CSVs em data/raw (S, M ou G)
.\.venv\Scripts\python scripts/02_csv_para_rdf_streaming.py        # 2. converte para RDF em data/rdf (.nt.gz particionado)
.\.venv\Scripts\python scripts/07_validar_qualidade.py             # 3. valida (os casos plantados DEVEM aparecer como problemas)
.\.venv\Scripts\python scripts/10_benchmark_modelos.py --escala S  # 4. compara os modelos temporais A, A2 e B (tempo, triplas, memória)
.\.venv\Scripts\python scripts/11_gerar_graficos.py --escala S     # 5. gera os gráficos em benchmarks/relatorios
```

Incremental (opcional): `08_simular_delta.py --pct 5` e depois `04_carga_incremental.py --entidade socios --lote 2026-06 --arquivo ...` (rode com dois lotes para ver novo/alterado/removido).

**Escalas M e G geram GBs.** Como esta pasta está no OneDrive, aponte os dados para fora dela antes de rodar:

```powershell
$env:SIMULADOR_DADOS = "C:\simulador_dados"
```

Todos os scripts passam a ler/gravar `raw/`, `rdf/` e `manifests/` nessa pasta. Os resultados e gráficos continuam em `benchmarks/`.

Testes: `.\.venv\Scripts\python -m pytest tests`

## Como ler os resultados

Os modelos temporais comparados (explicados em ordem de simplicidade):

| Modelo | Ideia em uma frase | Ponto forte | Ponto fraco |
|---|---|---|---|
| **A** | Cada vínculo sócio-empresa é um nó com `validoDe` e `validoAte` (sem `validoAte` = ainda ativo) | Guarda a data exata, sem copiar dados | Consulta precisa de `OPTIONAL`, que pode ficar lenta |
| **A2** | Igual ao A, mas vínculo ativo recebe `validoAte = 9999-12-31` | Consulta simples, sem `OPTIONAL` | 1 tripla a mais por vínculo ativo |
| **B** | Uma "foto" mensal (named graph) com os vínculos ativos naquele mês | Pergunta "quem era sócio em tal mês?" muito rápida | Copia o vínculo em toda foto: cresce com o tempo; perde a data exata |

**Atenção:** o simulador usa o Oxigraph (pyoxigraph) em memória. Ele serve para comparar os modelos *entre si*. Tempos e MB absolutos **não** valem para o AnzoGraph: refaça os mesmos testes no ambiente de homologação.

## Scripts

| Script | Função |
|---|---|
| `scripts/rdf_utils.py` | URIs, literais, conversores CSV -> RDF e escritor particionado (código compartilhado) |
| `01_gerar_bases_simuladas.py` | Gera as bases e `data/raw/casos_plantados.json` (gabarito) |
| `02_csv_para_rdf_streaming.py` | CSV -> N-Triples/N-Quads `.gz`, linha a linha (memória constante) |
| `03_particionar_e_comprimir.py` | Divide um arquivo RDF grande em partes `.gz` |
| `04_carga_incremental.py` | Detecta novo/alterado/removido e gera delta + SPARQL Update de remoção |
| `05_monitor_memoria.py` | Mede o pico de memória de qualquer comando |
| `06_benchmark_consultas.py` | Mede o tempo das consultas de `sparql/tuning` em um endpoint |
| `07_validar_qualidade.py` | Valida URIs, datas, campos obrigatórios e contagem x manifesto |
| `08_simular_delta.py` | Cria `socios_delta.csv` para testar o incremental |
| `09_converter_rdflib_em_memoria.py` | Anti-padrão didático: compare a memória com o script 02 |
| `10_benchmark_modelos.py` | Compara modelos temporais A, A2 e B em um triple store local (pyoxigraph); `--varredura` mostra o custo do B por nº de fotos; também roda as consultas de `sparql/tuning` |
| `11_gerar_graficos.py` | Gera 7 gráficos PNG em `benchmarks/relatorios/` (veja abaixo) |
| `databricks/notebook_csv_para_rdf.py` | Versão PySpark (distribuída) da conversão de sócios |

## Casos plantados (gabarito)

| Caso | Esperado |
|---|---|
| A | `CX-0001` gera alerta de conflito de interesse |
| B | `CX-0002` **não** gera alerta (sócio saiu antes do contrato) |
| C | `CX-0003` sem alerta; `CX-0004` com alerta |
| D | Empresa `99999990` é um supernó (milhares de estabelecimentos) |
| E | `CX-0005` só aparece com `conflito_interesse_ate_3_graus.rq` |
| F | Qualidade: CNPJ `1234567`, razão social duplicada em `00000004`, sócio com saída < entrada |

## Gráficos (benchmarks/relatorios)

| Arquivo | Pergunta que responde |
|---|---|
| `01_triplas_e_memoria_por_modelo_<escala>.png` | Quantas triplas e quanta memória cada modelo usa? |
| `02_tempo_consultas_por_modelo_<escala>.png` | Qual modelo responde mais rápido a cada pergunta? |
| `03_custo_do_modelo_B_por_fotos_<escala>.png` | O que acontece com o B quando aumentam as fotos mensais? |
| `04_tuning_ruim_vs_bom_<escala>.png` | Quanto uma consulta mal escrita custa a mais? |
| `05_projecao_de_memoria.png` | Quanta memória para 1 e 2 bilhões de triplas? (projeção linear de referência) |
| `06_memoria_na_conversao.png` | Streaming x tudo-em-memória na conversão para RDF |
| `07_grafo_casos_plantados.png` | Desenho das relações dos casos plantados (para entender o grafo) |

## Experimento sugerido (memória)

```powershell
.\.venv\Scripts\python scripts/05_monitor_memoria.py streaming .\.venv\Scripts\python scripts/02_csv_para_rdf_streaming.py --entidade socios
.\.venv\Scripts\python scripts/05_monitor_memoria.py rdflib    .\.venv\Scripts\python scripts/09_converter_rdflib_em_memoria.py
```

Rode na escala M e compare os picos em `benchmarks/resultados/`.
