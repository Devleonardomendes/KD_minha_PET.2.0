KD_minha_PET 4.0
================

Aplicativo Windows de busca local de peticoes e documentos juridicos.

DESENVOLVEDOR: LEONARDO CARDOSO DE MELO TEIXEIRA MENDES - PROCURADOR FEDERAL / AGU

Download
--------
- Baixe o instalador Windows em downloads\KD_minha_PET.4.0_Setup.exe.
- Tutorial de excecao no Windows: TUTORIAL_EXCECAO_FIREWALL_WINDOWS.txt.

Instalacao e desinstalacao
--------------------------
- Execute KD_minha_PET.4.0_Setup.exe para instalar o aplicativo no computador.
- O instalador cria atalhos na area de trabalho e no menu Iniciar.
- Para desinstalar, abra o Painel de Controle do Windows, entre em Programas e Recursos, selecione KD_minha_PET.4.0 e clique em desinstalar.

Principais recursos
-------------------
- Busca por nome, caminho e, quando habilitado, conteudo de arquivos.
- Leitura de TXT, MD, CSV, JSON, XML, HTML, RTF, DOCX, XLSX e PDF.
- OCR opcional para PDFs escaneados, usando recursos disponiveis no Windows.
- Seletor de quantidade de resultados exibidos: apenas os mais relevantes sao mostrados.
- Filtro por ano inicial e ano final, com suporte a um unico ano quando os dois campos sao iguais.
- Filtro por tipo de documento identificado no texto inicial/primeira pagina:
  - Contestacao
  - Apelacao
  - Contrarrazoes / Contra-Razoes
  - Impugnacao
  - Agravo de instrumento
  - Outros
  - Todos os documentos
- Campo "Outros" em tipo de documento para informar manualmente o nome da peca a buscar.
- Opcao para aproveitar o indice do Windows Search quando disponivel, com fallback automatico para a busca interna.
- Modo "Usar o LM Studio para Busca com Linguagem Natural", usando modelo local do LM Studio para expandir a consulta e reordenar os candidatos encontrados.
- Campos "Orientações para IA" e "Negação de Prioridade" no modo LM Studio.
- Modo "Busca local com termos de pesquisa (nao usar o LM Studio)" para manter a busca tradicional.
- Botao "Exportar logs", disponivel mesmo quando nao houve erro.
- Botao "README" para consultar estas instrucoes dentro do proprio aplicativo.
- Barra de status com andamento da busca e percentuais aproximados de uso geral da CPU e da memoria RAM.

Como usar
---------
1. Abra o KD_minha_PET 4.0.
2. Escolha a pasta em que os documentos serao pesquisados.
3. Escolha o modo de busca:
   - "Usar o LM Studio para Busca com Linguagem Natural"
   - "Busca local com termos de pesquisa (nao usar o LM Studio)"
4. Digite os termos ou a pergunta em "Palavras de busca".
5. Escolha quantos resultados deseja exibir.
6. Preencha "Ano inicial" e/ou "Ano final" se quiser restringir por ano de modificacao do arquivo.
7. Escolha o tipo de documento, se quiser restringir pelo nome da peca exibido na primeira pagina. Se escolher "Outros", preencha o nome da peca.
8. No modo LM Studio, use "Orientações para IA" para instrucoes especiais de busca e "Negação de Prioridade" para termos que devem reduzir fortemente a relevancia.
9. Marque "Usar indice do Windows Search quando disponivel" se quiser tentar acelerar a busca com o indice do Windows.
10. Clique em "Buscar".
11. Use "README" para abrir estas instrucoes dentro do aplicativo.

Modo LM Studio
--------------
- Ao selecionar "Usar o LM Studio para Busca com Linguagem Natural", o aplicativo abre uma tela com o aviso "Aguarde a abertura do LM Studio e selecao de modelo".
- O botao "OK" so aparece quando o aplicativo termina de abrir o LM Studio, iniciar o servidor local e selecionar/carregar o ultimo modelo identificado.
- O LM Studio roda localmente, em http://127.0.0.1:1234.
- O aplicativo tenta usar um modelo ja carregado. Se nenhum modelo estiver carregado, usa o ultimo modelo local identificado pelo historico do LM Studio.
- No modo LM Studio, voce pode usar linguagem natural em "Palavras de busca". O LM Studio interpreta a pergunta e gera termos juridicos relacionados antes da varredura local.
- Use "Orientações para IA" para instrucoes especiais, como evitar certa expressao, priorizar uma pasta ou aplicar uma regra de interpretacao.
- Use "Negação de Prioridade" para palavras ou expressoes que, quando encontradas em um candidato, devem reduzir muito sua relevancia.
- A IA nao substitui a leitura dos arquivos: depois da expansao da consulta, o KD_minha_PET procura nos nomes, caminhos e conteudo extraivel dos documentos; em seguida, o LM Studio pode reordenar os candidatos encontrados.
- Para procurar uma frase literal, escreva a expressao entre aspas. Nesse caso, o KD_minha_PET prioriza a correspondencia local da expressao e evita que o reranking por IA rebaixe esse resultado.
- No modo "Busca local com termos de pesquisa (nao usar o LM Studio)", prefira palavras-chave objetivas, nomes de pecas, numeros de processo ou expressoes exatas.
- Se o LM Studio falhar, a busca local continua disponivel.

Observacoes sobre filtros
-------------------------
- O filtro de ano usa a data de modificacao do arquivo no Windows.
- Para restringir a um unico ano, preencha o mesmo ano em "Ano inicial" e "Ano final".
- O filtro de tipo de documento depende de texto extraivel da primeira pagina ou do inicio do documento.
- Na opcao "Outros", o nome da peca digitado tambem e procurado nesse texto inicial.
- PDFs escaneados podem exigir OCR para que o tipo de documento seja reconhecido.
- Quando o Windows Search nao esta disponivel, nao tem permissao ou nao retorna candidatos indexados, o aplicativo registra o fato no log e usa a busca interna.

Logs
----
Use "Exportar logs" para salvar:
- Configuracao atual da busca.
- Eventos da sessao.
- Falhas ou mensagens de fallback.
- Resultados exibidos no momento da exportacao.

Empacotamento
-------------
- O executavel principal gerado deve se chamar KD_minha_PET.4.0.exe.
- O instalador gerado deve se chamar KD_minha_PET.4.0 Setup.exe.
- O script principal de build e build_exe.ps1.
- O script de instalador e installer/build_setup.ps1.

Requisitos de sistema
---------------------

Cenario 1: busca local, sem LM Studio
-------------------------------------
Configuracao minima:
- Windows 10 ou Windows 11, 64 bits.
- CPU Intel i5/Ryzen 5 ou superior.
- 8 GB de memoria total RAM+VRAM.
- SSD com 10 GB livres.
- Uso recomendado apenas para pastas pequenas ou medias e com OCR limitado.

Configuracao recomendada:
- Windows 10 ou Windows 11, 64 bits.
- CPU Intel i7/Ryzen 7 ou superior.
- 16 GB de memoria total RAM+VRAM.
- SSD/NVMe com 30 GB livres.
- 32 GB de memoria total RAM+VRAM para uso intensivo com PDFs grandes, muitos arquivos ou OCR frequente.

Cenario 2: busca com LM Studio usando Gemma 4 12B QAT
-----------------------------------------------------
Base de calculo:
- O Gemma 4 12B possui 11,95B parametros, conforme o model card oficial do Google.
- O modelo local google/gemma-4-12b-qat medido no LM Studio ocupa 7,15 GB em disco.
- A memoria de inferencia estimada para o modelo foi calculada como 7,15 GB x 1,25 = 8,94 GB, arredondada para 9 GB em RAM+VRAM.
- A integracao do KD_minha_PET carrega o modelo com contexto 8192; contextos maiores podem exigir mais memoria.

Memoria total RAM+VRAM recomendada:
- Minimo operacional: 32 GB.
- Recomendado: 48 GB.
- Uso intensivo com muitos PDFs, OCR frequente ou pastas grandes: 64 GB.

Configuracao minima para LM Studio:
- Windows 10 ou Windows 11, 64 bits.
- CPU com AVX2.
- 32 GB de memoria total RAM+VRAM.
- SSD com 30 GB livres para aplicativo, modelo e arquivos temporarios.

Configuracao recomendada para LM Studio:
- Windows 11, 64 bits.
- CPU Intel i7/Ryzen 7 ou superior.
- 48 GB de memoria total RAM+VRAM.
- 64 GB de memoria total RAM+VRAM para uso intensivo com muitos PDFs, OCR frequente ou pastas grandes.
- SSD/NVMe com 50 GB a 100 GB livres.

Referencias:
- https://lmstudio.ai/docs/app/system-requirements
- https://ai.google.dev/gemma/docs/core/model_card_4

Notas
-----
- Nao e necessario instalar Python separadamente no pacote gerado pelo PyInstaller.
- A abertura dos arquivos encontrados usa o programa padrao configurado no Windows.
- O aplicativo nao instala Word, LibreOffice, leitores de PDF ou mecanismos externos de OCR.
