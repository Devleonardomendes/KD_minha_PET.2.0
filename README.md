# KD_minha_PET.2.0

Aplicativo Windows de busca local de peticoes e documentos juridicos.

Criador: **LEONARDO CARDOSO DE MELO TEIXEIRA MENDES**.

## Download

Baixe o instalador Windows em [`downloads/KD_minha_PET.2.0_Setup.exe`](downloads/KD_minha_PET.2.0_Setup.exe).

## Principais recursos

- Busca por nome, caminho e, quando habilitado, conteudo de arquivos.
- Leitura de TXT, MD, CSV, JSON, XML, HTML, RTF, DOCX, XLSX e PDF.
- OCR opcional para PDFs escaneados, usando recursos disponiveis no Windows.
- Seletor de quantidade de resultados exibidos: apenas os mais relevantes sao mostrados.
- Filtro por ano inicial e ano final, com suporte a um unico ano quando os dois campos sao iguais.
- Filtro por tipo de documento identificado no texto inicial/primeira pagina: Contestacao, Apelacao, Contrarrazoes/Contra-Razoes, Agravo de instrumento ou todos os documentos.
- Opcao para aproveitar o indice do Windows Search quando disponivel, com fallback automatico para a busca interna.
- Botao **Exportar logs**, disponivel mesmo quando nao houve erro.
- Botao **README** para consultar estas instrucoes dentro do proprio aplicativo.
- Barra de status com andamento da busca e percentuais aproximados de uso geral da CPU e da memoria RAM.

## Como usar

1. Abra o `KD_minha_PET.2.0`.
2. Escolha a pasta em que os documentos serao pesquisados.
3. Digite os termos da busca.
4. Escolha quantos resultados deseja exibir.
5. Preencha `Ano inicial` e/ou `Ano final` se quiser restringir por ano de modificacao do arquivo.
6. Escolha o tipo de documento, se quiser restringir pelo nome da peca exibido na primeira pagina.
7. Marque `Usar indice do Windows Search quando disponivel` se quiser tentar acelerar a busca com o indice do Windows.
8. Clique em `Buscar`.
9. Use `README` para abrir estas instrucoes dentro do aplicativo.

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

- O executavel principal gerado deve se chamar `KD_minha_PET.2.0.exe`.
- O instalador gerado deve se chamar `KD_minha_PET.2.0 Setup.exe`.
- O script principal de build e `build_exe.ps1`.
- O script de instalador e `installer/build_setup.ps1`.

## Requisitos recomendados

- Windows 10 ou Windows 11, 64 bits.
- SSD.
- 16 GB de RAM ou mais.
- Para uso intensivo com PDFs grandes ou escaneados, recomenda-se 32 GB de RAM e CPU Intel Core i7/Ryzen 7 ou superior.
- a utilização desta ferramenta por usuários equipados com Intel i5 ou Ryzen 5 ou Memória RAM de 8Gb deverá ser realizada com cautela, limitando a busca a pastas com poucos arquivos. Este app não é recomendado para Setups inferiores às especificações mínimas

## Notas

- Nao e necessario instalar Python separadamente no pacote gerado pelo PyInstaller.
- A abertura dos arquivos encontrados usa o programa padrao configurado no Windows.
- O aplicativo nao instala Word, LibreOffice, leitores de PDF ou mecanismos externos de OCR.
