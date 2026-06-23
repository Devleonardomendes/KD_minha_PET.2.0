# KD_minha_PET 3.0

Aplicativo Windows de busca local de peticoes e documentos juridicos.

Criador: **LEONARDO CARDOSO DE MELO TEIXEIRA MENDES**.

## Download

Baixe o instalador Windows em [`downloads/KD_minha_PET.3.0_Setup.exe`](downloads/KD_minha_PET.3.0_Setup.exe).

## Principais recursos

- Busca por nome, caminho e, quando habilitado, conteudo de arquivos.
- Leitura de TXT, MD, CSV, JSON, XML, HTML, RTF, DOCX, XLSX e PDF.
- OCR opcional para PDFs escaneados, usando recursos disponiveis no Windows.
- Seletor de quantidade de resultados exibidos: apenas os mais relevantes sao mostrados.
- Filtro por ano inicial e ano final, com suporte a um unico ano quando os dois campos sao iguais.
- Filtro por tipo de documento identificado no texto inicial/primeira pagina: Contestacao, Apelacao, Contrarrazoes/Contra-Razoes, Agravo de instrumento ou todos os documentos.
- Opcao para aproveitar o indice do Windows Search quando disponivel, com fallback automatico para a busca interna.
- Modo `Usar o LM Studio para Busca com Linguagem Natural`, usando modelo local do LM Studio para expandir a consulta e reordenar os candidatos encontrados.
- Modo `Busca local com termos de pesquisa (nao usar o LM Studio)` para manter a busca tradicional.
- Botao **Exportar logs**, disponivel mesmo quando nao houve erro.
- Botao **README** para consultar estas instrucoes dentro do proprio aplicativo.
- Barra de status com andamento da busca e percentuais aproximados de uso geral da CPU e da memoria RAM.

## Como usar

1. Abra o `KD_minha_PET 3.0`.
2. Escolha a pasta em que os documentos serao pesquisados.
3. Escolha o modo de busca: `Usar o LM Studio para Busca com Linguagem Natural` ou `Busca local com termos de pesquisa (nao usar o LM Studio)`.
4. Digite os termos ou a pergunta da busca.
5. Escolha quantos resultados deseja exibir.
6. Preencha `Ano inicial` e/ou `Ano final` se quiser restringir por ano de modificacao do arquivo.
7. Escolha o tipo de documento, se quiser restringir pelo nome da peca exibido na primeira pagina.
8. Marque `Usar indice do Windows Search quando disponivel` se quiser tentar acelerar a busca com o indice do Windows.
9. Clique em `Buscar`.
10. Use `README` para abrir estas instrucoes dentro do aplicativo.

## Modo LM Studio

- Ao selecionar `Usar o LM Studio para Busca com Linguagem Natural`, o aplicativo abre uma tela com o aviso `Aguarde a abertura do LM Studio e selecao de modelo`.
- O botao `OK` so aparece quando o aplicativo termina de abrir o LM Studio, iniciar o servidor local e selecionar/carregar o ultimo modelo identificado.
- O LM Studio roda localmente, em `http://127.0.0.1:1234`.
- O aplicativo tenta usar um modelo ja carregado. Se nenhum modelo estiver carregado, usa o ultimo modelo local identificado pelo historico do LM Studio.
- A IA nao substitui a varredura dos arquivos: primeiro o KD_minha_PET encontra candidatos locais, depois o LM Studio ajuda a expandir a consulta e reordenar os resultados.
- Se o LM Studio falhar, a busca local continua disponivel.

## Observacoes sobre filtros

- O filtro de ano usa a data de modificacao do arquivo no Windows.
- Para restringir a um unico ano, preencha o mesmo ano em `Ano inicial` e `Ano final`.
- O filtro de tipo de documento depende de texto extraivel da primeira pagina ou do inicio do documento.
- PDFs escaneados podem exigir OCR para que o tipo de documento seja reconhecido.
- Quando o Windows Search nao esta disponivel, nao tem permissao ou nao retorna candidatos indexados, o aplicativo registra o fato no log e usa a busca interna.

## Logs

Use `Exportar logs` para salvar:

- Configuracao atual da busca.
- Eventos da sessao.
- Falhas ou mensagens de fallback.
- Resultados exibidos no momento da exportacao.

## Empacotamento

- O executavel principal gerado deve se chamar `KD_minha_PET.3.0.exe`.
- O instalador gerado deve se chamar `KD_minha_PET.3.0 Setup.exe`.
- O script principal de build e `build_exe.ps1`.
- O script de instalador e `installer/build_setup.ps1`.

## Requisitos de sistema

### Cenario 1: busca local, sem LM Studio

Configuracao minima:

- Windows 10 ou Windows 11, 64 bits.
- CPU Intel i5/Ryzen 5 ou superior.
- 8 GB de RAM.
- SSD com 10 GB livres.
- GPU dedicada nao e obrigatoria.
- Uso recomendado apenas para pastas pequenas ou medias e com OCR limitado.

Configuracao recomendada:

- Windows 10 ou Windows 11, 64 bits.
- CPU Intel i7/Ryzen 7 ou superior.
- 16 GB de RAM.
- SSD/NVMe com 30 GB livres.
- 32 GB de RAM para uso intensivo com PDFs grandes, muitos arquivos ou OCR frequente.

### Cenario 2: busca com LM Studio usando Gemma 4 12B QAT

Base de calculo:

- O LM Studio recomenda, no Windows, CPU com AVX2, 16 GB de RAM e GPU dedicada com pelo menos 4 GB de VRAM.
- O Gemma 4 12B possui 11,95B parametros, conforme o model card oficial do Google.
- O modelo local `google/gemma-4-12b-qat` medido no LM Studio ocupa 7,15 GB em disco.
- A memoria de inferencia estimada para o modelo foi calculada como `7,15 GB x 1,25 = 8,94 GB`, arredondada para 9 GB em RAM+VRAM.
- A integracao do KD_minha_PET carrega o modelo com contexto 8192; contextos maiores podem exigir mais memoria.
- RAM e VRAM nao sao perfeitamente intercambiaveis. A coluna RAM+VRAM serve apenas como referencia de capacidade total disponivel; sem GPU dedicada, o modelo, o LM Studio, o Windows e o KD_minha_PET disputam a mesma RAM do sistema.

Memoria RAM+VRAM por perfil:

| Perfil da maquina | VRAM considerada | RAM minima calculada | Memoria total minima RAM+VRAM | RAM recomendada | Memoria total recomendada RAM+VRAM |
|---|---:|---:|---:|---:|---:|
| Sem GPU dedicada | 0 GB | 48 GB | 48 GB | 64 GB | 64 GB |
| GPU com 8 GB de VRAM | 8 GB | 32 GB | 40 GB | 48 GB | 56 GB |
| GPU com 12 GB de VRAM | 12 GB | 24 GB | 36 GB | 32 GB | 44 GB |
| GPU com 16 GB de VRAM | 16 GB | 16 GB | 32 GB | 32 GB | 48 GB |

Configuracao minima para LM Studio:

- Windows 10 ou Windows 11, 64 bits.
- CPU com AVX2.
- Sem GPU dedicada: 48 GB de RAM.
- Com GPU dedicada: pelo menos 32 GB de memoria total RAM+VRAM, respeitando a tabela acima.
- SSD com 30 GB livres para aplicativo, modelo e arquivos temporarios.
- Sem GPU dedicada, o uso e possivel, mas a inferencia sera feita em CPU/RAM e sera bem mais lenta.

Configuracao recomendada para LM Studio:

- Windows 11, 64 bits.
- CPU Intel i7/Ryzen 7 ou superior.
- GPU dedicada com 12 GB ou 16 GB de VRAM.
- 32 GB de RAM com GPU de 12 GB ou 16 GB; 48 GB de RAM se a GPU tiver apenas 8 GB de VRAM; 64 GB de RAM se nao houver GPU dedicada.
- SSD/NVMe com 50 GB a 100 GB livres.

Referencias: [LM Studio System Requirements](https://lmstudio.ai/docs/app/system-requirements) e [Gemma 4 model card](https://ai.google.dev/gemma/docs/core/model_card_4).

## Notas

- Nao e necessario instalar Python separadamente no pacote gerado pelo PyInstaller.
- A abertura dos arquivos encontrados usa o programa padrao configurado no Windows.
- O aplicativo nao instala Word, LibreOffice, leitores de PDF ou mecanismos externos de OCR.
