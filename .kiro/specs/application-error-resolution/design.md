# Application Error Resolution Bugfix Design

## Overview

Este bugfix trata exclusivamente da inicialização local incorreta do Document Intelligence Copilot. Executar `python app.py` chama o módulo diretamente pelo interpretador Python e executa comandos Streamlit sem o contexto de execução que o framework fornece, produzindo o aviso `missing ScriptRunContext`. A correção é operacional: iniciar a aplicação com `streamlit run app.py`, que cria o servidor localhost e o contexto Streamlit esperado. Nenhuma alteração de código da aplicação é necessária ou planejada.

O erro adicional relatado na tela de Upload não tem mensagem, stack trace, arquivo de entrada, tamanho ou etapa de falha identificados. Ele fica explicitamente fora de escopo técnico deste design até que existam evidências reproduzíveis; este documento só cobre impactos de Upload diretamente causados pela ausência de `ScriptRunContext`.

## Glossary

- **Bug_Condition (C)**: Condição em que o entry point é iniciado diretamente com `python app.py`, resultando no uso de componentes Streamlit sem `ScriptRunContext`.
- **Property (P)**: Com a aplicação iniciada pelo lançador Streamlit, a interface é servida localmente com contexto Streamlit e não apresenta o aviso por ausência desse contexto.
- **Preservation**: Comportamentos já corretos que não devem mudar, incluindo a página inicial, a validação de formatos e o limite de tamanho de upload.
- **LaunchAttempt**: Tentativa de iniciar a aplicação local, composta pelo comando utilizado e pelo entry point `app.py`.
- **Streamlit launcher**: Comando `streamlit run app.py`, responsável por criar o processo e o contexto de execução da interface.
- **ScriptRunContext**: Contexto de execução disponibilizado pelo Streamlit às chamadas de UI, como `st.set_page_config`, `st.title` e `st.markdown`.
- **Upload pipeline**: Fluxo posterior à seleção de um arquivo, composto por validação, classificação, extração e análise. Uma falha independente nesse fluxo não é definida neste bugfix sem dados de reprodução.

## Bug Details

### Bug Condition

O bug se manifesta quando a pessoa usa o interpretador Python para executar o entry point Streamlit. Nessa condição, `app.py` chama componentes de interface sem que o lançador Streamlit tenha criado o `ScriptRunContext`, e o terminal mostra `missing ScriptRunContext`.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type LaunchAttempt
  OUTPUT: boolean

  RETURN input.entryPoint = "app.py"
         AND input.command = "python app.py"
         AND streamlitUiComponentsExecute(input.entryPoint)
         AND NOT scriptRunContextIsAvailable()
         AND terminalContains("missing ScriptRunContext")
END FUNCTION
```

### Examples

- Executar `python app.py` em um ambiente com as dependências instaladas chama `st.set_page_config` e outros componentes sem contexto; o comportamento atual é o aviso `missing ScriptRunContext`. O comportamento correto é iniciar pelo lançador Streamlit, não pela execução direta do módulo.
- Executar `streamlit run app.py` deve iniciar um servidor local Streamlit e renderizar a página inicial; não deve produzir um aviso decorrente da ausência de `ScriptRunContext`.
- Depois de iniciar com `python app.py`, tentar navegar até Upload pode resultar em uma experiência inválida por falta de contexto. Depois de iniciar com `streamlit run app.py`, o seletor de arquivos deve renderizar sem falha causada por esse contexto ausente.
- Selecionar um PDF, PNG, JPG ou JPEG de até 20 MB após uma inicialização correta não pertence à condição do bug. Se essa ação falhar por outro motivo, faltam dados para defini-la ou corrigi-la neste escopo.

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- A execução com `streamlit run app.py` deve continuar exibindo a página inicial do Document Intelligence Copilot em localhost.
- Em uma execução com contexto Streamlit, a tela de Upload deve continuar exibindo o seletor de arquivos.
- Arquivos PDF, PNG, JPG e JPEG de até 20 MB devem continuar sendo validados quanto ao formato e tamanho antes do pipeline de processamento.
- O pipeline de Upload não deve receber mudanças especulativas: nenhuma alegação de corrigir um erro independente de upload é feita sem reprodução e evidências.

**Scope:**
Todas as entradas que não correspondem à condição de execução direta devem permanecer inalteradas. Isso inclui:
- A inicialização já correta por `streamlit run app.py`.
- Interações na UI depois de a sessão Streamlit existir, incluindo a seleção de arquivos.
- Rejeição de tipos de arquivo não aceitos ou de arquivos acima de 20 MB.
- Qualquer defeito de Upload não comprovadamente causado pela falta de `ScriptRunContext`, que permanece fora de escopo técnico.

**Expected-Behavior Oracle:**
```
FUNCTION expectedBehavior(result)
  INPUT: result of type LaunchResult
  OUTPUT: boolean

  RETURN result.command = "streamlit run app.py"
         AND result.localServerIsAvailable = true
         AND result.scriptRunContextIsAvailable = true
         AND NOT result.terminalOutputContains("missing ScriptRunContext")
         AND result.homePageRenders = true
END FUNCTION
```

## Hypothesized Root Cause

Com base no aviso confirmado e na estrutura atual do entry point, a causa é conhecida para este escopo:

1. **Lançador de runtime incorreto**: `app.py` é uma aplicação Streamlit, mas é iniciado por `python app.py`.
   - O interpretador executa o módulo, porém não provisiona o ciclo de vida e o `ScriptRunContext` do Streamlit.
   - As chamadas de UI no topo de `app.py` são alcançadas sem o contexto de script esperado.

2. **Procedimento operacional não seguido**: A documentação do projeto já indica `streamlit run app.py`, mas a execução relatada usou um comando diferente.
   - A ação corretiva é usar o comando documentado.
   - O escopo não justifica contornar no código um modo de execução que o framework não suporta.

3. **Relato de Upload sem diagnóstico suficiente**: Não há evidências de que uma falha de Upload seja causada por lógica de Upload.
   - Faltam stack trace, mensagem, arquivo, tamanho, credenciais/configuração e etapa do pipeline.
   - Não se deve formular uma hipótese de causa nem implementar mudança para essa falha até que ela possa ser reproduzida.

## Correctness Properties

Property 1: Bug Condition - Inicialização pelo Lançador Streamlit

_For any_ tentativa de inicialização que corresponda à condição do bug — `app.py` contendo componentes Streamlit e sendo executado diretamente por `python app.py` sem `ScriptRunContext` — a resolução SHALL orientar e realizar a inicialização com `streamlit run app.py`, disponibilizando a interface local com contexto Streamlit e sem o aviso `missing ScriptRunContext` por ausência de contexto.

**Validates: Requirements 2.1, 2.2**

Property 2: Preservation - Comportamentos em Sessões Streamlit Válidas

_For any_ entrada em que a condição do bug não se aplique — em especial uma sessão iniciada por `streamlit run app.py` e arquivos selecionados na tela de Upload — a resolução SHALL produzir o mesmo comportamento observado antes, preservando a página inicial, o seletor de arquivos e a validação de formatos PDF/PNG/JPG/JPEG e limite de 20 MB.

**Validates: Requirements 3.1, 3.2**

## Fix Implementation

### Changes Required

A análise confirma uma correção de procedimento de execução, sem alteração de código-fonte.

**Files**: Nenhum arquivo da aplicação será alterado neste bugfix.

**Function**: Não aplicável; `app.py` já é o entry point Streamlit e suas chamadas de interface devem continuar inalteradas.

**Specific Changes:**
1. **Usar o lançador correto**: Substituir a prática de executar `python app.py` pelo comando `streamlit run app.py` no ambiente local.
   - Executar o comando a partir da raiz do projeto, após instalar as dependências.
   - Acessar a URL localhost informada pelo Streamlit.

2. **Manter o entry point inalterado**: Não adicionar verificações, suprimir avisos, condicionais ou wrappers em `app.py`.
   - O `ScriptRunContext` deve ser fornecido pelo runtime, não simulado pelo código da aplicação.
   - Isso mantém o bugfix mínimo e evita alterar o comportamento da UI em sessões válidas.

3. **Preservar o limite de escopo do Upload**: Não modificar componentes, validações ou pipeline de Upload.
   - Registrar uma investigação separada somente quando houver dados de reprodução suficientes.
   - Os dados mínimos incluem mensagem/stack trace, tipo e tamanho do arquivo, etapa que falha e configuração relevante.

4. **Confirmar orientação de execução**: O README atual já documenta `streamlit run app.py`; nenhuma edição documental é necessária como parte deste design.
   - Se a orientação for replicada futuramente em outro local, ela deve usar exatamente esse comando.

## Testing Strategy

### Validation Approach

A estratégia tem duas fases: primeiro reproduzir e registrar o contraexemplo de execução direta, depois confirmar que a inicialização pelo lançador Streamlit elimina a condição e preserva os comportamentos existentes. Como não há mudança de código, a validação é operacional e de interface; testes automatizados só devem ser adicionados se o projeto passar a encapsular a inicialização em código testável.

### Exploratory Bug Condition Checking

**Goal**: Demonstrar o contraexemplo no fluxo não corrigido e confirmar que a causa é a ausência de contexto, não uma falha do entry point ou do Upload.

**Test Plan**: Em ambiente local com dependências instaladas, executar `python app.py`, registrar a saída do terminal e observar a indisponibilidade de uma sessão Streamlit válida. Em seguida, executar `streamlit run app.py` e comparar a presença do servidor local, do contexto e da página inicial.

**Test Cases**:
1. **Execução direta por Python**: Executar `python app.py` e verificar o aviso `missing ScriptRunContext` (contraexemplo esperado no estado não corrigido).
2. **Inicialização pelo Streamlit**: Executar `streamlit run app.py` e verificar que a URL localhost é disponibilizada sem aviso de contexto ausente.
3. **Renderização de Upload na sessão válida**: Abrir a tela de Upload após a inicialização por Streamlit e verificar que o seletor é renderizado; isso testa apenas falhas atribuíveis à ausência de contexto.
4. **Limite de investigação de Upload**: Não declarar defeito nem correção para uma falha de processamento de arquivo sem mensagem, arquivo e etapa reprodutíveis.

**Expected Counterexamples**:
- A execução por `python app.py` produz `missing ScriptRunContext` ao alcançar chamadas de UI do Streamlit.
- A ausência de servidor/sessão Streamlit válida diferencia esse caso de uma falha de Upload independente.

### Fix Checking

**Goal**: Verificar que toda tentativa abrangida pela condição do bug é resolvida pela execução por meio do lançador Streamlit.

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  result := launchWith("streamlit run app.py")
  ASSERT expectedBehavior(result)
END FOR
```

### Preservation Checking

**Goal**: Verificar que sessões que já possuem contexto Streamlit e suas interações permanecem iguais após adotar o comando correto.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT behaviorBeforeAdoptingLauncher(input) = behaviorAfterAdoptingLauncher(input)
END FOR
```

**Testing Approach**: Testes baseados em propriedades são recomendados para entradas de Upload somente se houver um adaptador testável e dados de entrada definidos. Para este bugfix operacional, a preservação é validada comparando a sessão Streamlit já correta com a sessão aberta pelo mesmo comando após a orientação ser adotada.

**Test Cases**:
1. **Preservação da página inicial**: Confirmar que o título e o conteúdo inicial continuam visíveis em localhost após `streamlit run app.py`.
2. **Preservação do seletor de arquivos**: Confirmar que a tela de Upload continua exibindo seu seletor em sessão Streamlit válida.
3. **Preservação de validação**: Confirmar que formatos aceitos e o limite de 20 MB continuam sendo aplicados antes do processamento.
4. **Preservação de escopo**: Confirmar que nenhuma alteração de Upload é inferida ou aplicada sem uma reprodução independente.

### Unit Tests

- Não há unidade de código modificada neste bugfix; nenhum teste unitário novo é necessário para a troca de comando operacional.
- Caso a inicialização venha a ser encapsulada em código no futuro, testar que o comando recomendado é `streamlit run app.py` e que a execução direta não é apresentada como suporte.
- Manter os testes existentes de validação de tipo e tamanho de Upload sem mudanças.

### Property-Based Tests

- Não introduzir testes baseados em propriedades para a inicialização neste escopo, pois o runtime Streamlit é externo ao `app.py` e não houve mudança de código.
- Se forem disponibilizados adaptadores de Upload testáveis, gerar combinações de tipo e tamanho para comprovar a preservação da validação em sessões válidas.
- Não gerar propriedades para o erro de Upload indefinido; elas exigem condição observável e oráculo de comportamento ainda ausentes.

### Integration Tests

- Iniciar a aplicação com `streamlit run app.py` e verificar que o servidor localhost e a página inicial estão disponíveis.
- Navegar até Upload em uma sessão Streamlit válida e verificar o render do seletor de arquivos.
- Comparar o resultado com a execução direta somente para confirmar o contraexemplo `missing ScriptRunContext`, sem diagnosticar uma falha adicional de Upload.
