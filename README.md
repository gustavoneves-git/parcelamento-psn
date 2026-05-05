# PSN Onvio

Sistema local para controlar a emissao mensal de guias do Parcelamento Simples Nacional e enviar o PDF para a pasta correta do Onvio.

Esta versao foi reiniciada com foco no uso cotidiano:

- Empresas
- Historico mensal

As paginas antigas de dashboard e parcelas emitidas foram removidas para reduzir ruido operacional.

## Fluxo

1. Cadastre a empresa.
2. Configure a pasta Onvio da empresa, quando houver.
3. Clique em `Consultar SERPRO`.
4. O sistema consulta o PARCSN antes de qualquer emissao.
5. Se houver competencia liberada, a tela mostra o botao `Emitir` para aquela competencia.
6. Ao emitir, o sistema salva o PDF e deixa `Subir para Onvio` disponivel.
7. Ao subir, o PDF e copiado para a pasta Onvio e o botao volta ao estado cinza.

## SERPRO

A automacao por navegador foi removida. O ponto de integracao agora fica em:

```text
app/services/serpro_service.py
```

Enquanto as credenciais da API SERPRO / Integra Contador / Integra Parcelamento nao estiverem configuradas, o botao `Emitir parcela` registra a empresa como `Aguardando API`.

Variaveis previstas:

```text
SERPRO_CONSUMER_KEY
SERPRO_CONSUMER_SECRET
SERPRO_CERT_PATH
SERPRO_CERT_PASSWORD
SERPRO_TOKEN_URL
SERPRO_API_URL
```

Servicos PARCSN preparados:

- `PARCELASPARAGERAR162`: Consultar Parcelas Disponiveis para Impressao.
- `GERARDAS161`: Emitir Documento de Arrecadacao.
- `OBTERPARC164`: Consultar Parcelamento.

O cliente HTTP central registra logs tecnicos na tabela `serpro_logs`, sem gravar consumer secret.
As disponibilidades consultadas ficam na tabela `psn_disponibilidades`, incluindo casos em que a API informa que nao ha parcela liberada.

## Onvio

Cada empresa pode ter uma `Pasta Onvio` cadastrada. Se esse campo ficar vazio, o sistema usa:

```text
storage/onvio_saida/<cnpj>
```

## Como rodar

No Windows:

```bat
run.bat
```

Ou manualmente:

```bat
.venv\Scripts\activate
python -m app.main
```

Acesse:

```text
http://127.0.0.1:5050
```
