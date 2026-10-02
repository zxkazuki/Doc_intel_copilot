# Bugfix Requirements Document

## Introduction

Este documento registra o diagnóstico inicial para a execução e a tela de Upload do Document Intelligence Copilot. O comando relatado, `python app.py`, executa componentes Streamlit sem o contexto de execução da interface e produz o aviso `missing ScriptRunContext`; a execução compatível é por meio do lançador Streamlit.

Lacunas de diagnóstico ainda abertas: não foi fornecido o texto/stack trace do erro de upload, o arquivo usado (tipo e tamanho), nem a etapa do pipeline que falha após a seleção do arquivo. Portanto, este requisito cobre a condição de execução confirmada e preserva a necessidade de coletar esses dados antes de especificar qualquer falha distinta do pipeline.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN a pessoa executa o entry point com `python app.py` THEN os componentes Streamlit são executados sem `ScriptRunContext` e o terminal exibe o aviso `missing ScriptRunContext`.

1.2 WHEN a pessoa tenta usar a tela de Upload após iniciar a aplicação com `python app.py` THEN o relato informa que a tela apresenta erro, sem mensagem, arquivo de entrada ou etapa do pipeline identificados.

### Expected Behavior (Correct)

2.1 WHEN a pessoa inicia a aplicação localmente THEN o sistema SHALL ser iniciado pelo lançador Streamlit com `streamlit run app.py`, disponibilizando a interface em um servidor localhost com contexto de execução Streamlit.

2.2 WHEN a pessoa acessa a tela de Upload em uma execução com contexto Streamlit THEN o sistema SHALL renderizar o seletor de arquivos e executar o pipeline sem um erro causado pela ausência de `ScriptRunContext`.

### Unchanged Behavior (Regression Prevention)

3.1 WHEN a aplicação é iniciada com `streamlit run app.py` THEN o sistema SHALL CONTINUE TO exibir a página inicial do Document Intelligence Copilot em localhost.

3.2 WHEN a pessoa seleciona um arquivo PDF, PNG, JPG ou JPEG de até 20 MB em uma execução com contexto Streamlit THEN o sistema SHALL CONTINUE TO validar o formato e o tamanho antes de iniciar o pipeline de processamento.
