# PSN Onvio

Sistema local para controlar a emissao mensal de guias do Parcelamento Simples Nacional e enviar o PDF para a pasta correta do Onvio.

Esta versao foi reiniciada com foco no uso cotidiano:

- Empresas
- Historico mensal

As paginas antigas de dashboard e parcelas emitidas foram removidas para reduzir ruido operacional.

## Fluxo

1. Cadastre a empresa.
2. Configure a pasta Onvio da empresa, quando houver.
3. Clique em `Emitir parcela`.
4. Quando a integracao SERPRO estiver configurada, o sistema vai emitir a guia do mes e salvar o PDF.
5. Com o PDF emitido, o botao `Subir para Onvio` fica verde.
6. Ao subir, o PDF e copiado para a pasta Onvio e o botao volta ao estado cinza.

## SERPRO

A automacao por navegador foi removida. O ponto de integracao agora fica em:

```text
app/services/serpro_service.py
```

Enquanto as credenciais da API SERPRO / Integra Contador / Integra Parcelamento nao estiverem configuradas, o botao `Emitir parcela` registra a empresa como `Aguardando API`.

Variaveis previstas:

```text
SERPRO_CLIENT_ID
SERPRO_CLIENT_SECRET
SERPRO_CERT_PATH
```

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
