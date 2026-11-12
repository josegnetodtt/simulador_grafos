# Databricks notebook source
# MAGIC %md
# MAGIC # Sócios (Delta) -> RDF N-Quads distribuído
# MAGIC Gera triplas como texto, direto nas partições Spark (sem `collect()` / `toPandas()`), para carga paralela no Anzo.

# COMMAND ----------

from pyspark.sql import functions as F

dbutils.widgets.text("tabela", "rf.socios_delta")
dbutils.widgets.text("lote", "2026-06")
dbutils.widgets.text("saida", "/mnt/rdf/socios")
dbutils.widgets.text("partes", "64")

tabela, lote, saida = dbutils.widgets.get("tabela"), dbutils.widgets.get("lote"), dbutils.widgets.get("saida")
partes = int(dbutils.widgets.get("partes"))

BASE = "http://petrobras.exemplo"
ONTO = f"{BASE}/onto#"
XSD_DATE = "^^<http://www.w3.org/2001/XMLSchema#date>"
RDF_TYPE = "<http://www.w3.org/1999/02/22-rdf-syntax-ns#type>"
GRAFO = f"<{BASE}/graph/socios/{lote}>"

# COMMAND ----------

def lit(col, sufixo=""):
    """Literal N-Triples: remove quebras de linha e escapa aspas e barras."""
    limpo = F.regexp_replace(F.regexp_replace(col.cast("string"), r"[\r\n]+", " "), r'(["\\])', r"\\$1")
    return F.concat(F.lit('"'), limpo, F.lit('"' + sufixo))


def uri(prefixo, col):
    return F.concat(F.lit(f"<{BASE}/{prefixo}/"), col, F.lit(">"))


df = spark.read.table(tabela).withColumn(
    "s",
    F.concat(F.lit(f"<{BASE}/participacao/"), F.col("cnpj_basico"), F.lit("_"), F.col("id_socio"), F.lit("_"),
             F.regexp_replace(F.col("data_entrada").cast("string"), "-", ""), F.lit(">")),
)


def tripla(pred, obj):
    # obj nulo => sem tripla (ex.: sócio ainda ativo não tem validoAte)
    return F.when(obj.isNotNull(), F.concat_ws(" ", F.col("s"), F.lit(pred), obj, F.lit(GRAFO), F.lit(".")))


linhas = df.select(F.explode(F.array(
    tripla(RDF_TYPE, F.lit(f"<{ONTO}ParticipacaoSocietaria>")),
    tripla(f"<{ONTO}socio>", uri("pessoa", F.col("id_socio"))),
    tripla(f"<{ONTO}empresa>", uri("empresa", F.col("cnpj_basico"))),
    tripla(f"<{ONTO}nomeSocio>", lit(F.col("nome_socio"))),
    tripla(f"<{ONTO}qualificacao>", lit(F.col("qualificacao"))),
    tripla(f"<{ONTO}validoDe>", lit(F.col("data_entrada"), XSD_DATE)),
    tripla(f"<{ONTO}validoAte>", lit(F.col("data_saida"), XSD_DATE)),
)).alias("linha")).where(F.col("linha").isNotNull())

# COMMAND ----------

# Uma parte .gz por partição Spark => carga paralela. Ajuste a extensão (.nq.gz) se o carregador exigir.
(linhas.repartition(partes)
       .write.mode("overwrite").option("compression", "gzip")
       .text(f"{saida}/lote={lote}"))
