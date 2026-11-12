PREFIX ex: <http://petrobras.exemplo/onto#>

# TRANSFORMAÇÃO FATIADA (SPARQL Update): em vez de um único INSERT ... WHERE sobre a base inteira,
# execute o mesmo comando 10 vezes, trocando o dígito do FILTER (0 a 9). Cada fatia gera
# resultados intermediários ~10x menores e pode ser repetida isoladamente se falhar.
# Exemplo: materializa empresa -> contrato (aresta inversa de ex:fornecedor).

INSERT { ?empresa ex:temContrato ?contrato }
WHERE {
  ?contrato ex:fornecedor ?empresa .
  FILTER (STRSTARTS(STR(?empresa), "http://petrobras.exemplo/empresa/0"))   # fatia 0; repetir para 1..9
}
