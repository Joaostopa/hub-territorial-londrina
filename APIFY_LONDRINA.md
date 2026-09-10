# Apify — Londrina/PR

Esta edição integra o Actor indicado por João: https://apify.com/jungle_synthesizer/brazil-vivareal-zap-imoveis-scraper
Contrato consultado em 09/09/2026, também fornecido no Markdown anexado. A implementação usa sua API documentada; não executamos uma coleta autenticada na conta do usuário. Não há dados simulados adicionados à base real. Os dados reais iniciais anteriores continuam identificados por sua data.

## 1. Atualizar o projeto no Windows

1. Pare o site no terminal com Ctrl+C.
2. Faça uma cópia da pasta atual inteira para outra pasta, para manter uma cópia de segurança.
3. Extraia este ZIP em uma pasta temporária. Copie o conteúdo de `imoveis-hub` para a pasta atual do projeto, substituindo os arquivos de código.
4. Preserve sua pasta `.venv`, a pasta `data`, o arquivo `.env` e qualquer banco em local personalizado. O ZIP não inclui banco, token ou ambiente virtual.
5. Abra a pasta atual no VS Code. Use Python 3.12 e execute ` .\instalar_windows.bat` se faltarem dependências.

A inicialização cria duas tabelas adicionais. Não apaga nem altera as observações antigas. Não execute migrate_legacy.py apenas por causa desta atualização; ele só é necessário se houver aviso explícito de esquema antigo incompatível.

## 2. Configurar o token uma vez

No VS Code, abra o arquivo `.env` da raiz do projeto. Se não existir, crie-o copiando `.env.example`. Adicione:

```dotenv
APIFY_TOKEN=cole_seu_token_aqui
```

Obtenha seu token na conta Apify, Settings / API & Integrations. Não compartilhe o token, não o inclua em prints e não envie o `.env` no ZIP. A aplicação usa autenticação Bearer no cabeçalho HTTPS. Reinicie o site depois de alterar o arquivo.

## 3. Primeira coleta pequena (100 anúncios, venda)

Execute ` .\iniciar_windows.bat`, abra Fontes e coletas e procure **Apify — Londrina/PR**. Desative demonstração. A seção exige perfil administrador (o modo local padrão é administrador).

1. Escolha Venda e limite 100.
2. Confira preço e saldo no Console Apify. Cada clique em **Iniciar coleta no Apify (consome saldo)** solicita uma execução paga nova.
3. O ID é mostrado no campo da execução. Guarde-o; ele também aparece na tabela de execuções.
4. Espere a execução terminar no Console e clique **Consultar execução e importar resultado**. Consultar não inicia nova coleta.
5. Confira aceitos, rejeitados e os detalhes da execução. A importação recebe todas as páginas do dataset e só confirma a transação depois de terminar. Repetir a importação do mesmo ID não duplica dados.
6. No mapa, selecione Londrina e a finalidade correspondente. Registros sem coordenadas continuam no histórico, mas não aparecem no mapa.
7. Abra **Histórico completo do Apify e exportação** para ver observações, condomínio/IPTU, exportar JSON e consultar a curva de preço por anúncio.

Antes de aumentar o volume, abra links de anúncios da primeira coleta e confira preço, finalidade, área e localização. O limite 100 é uma amostra; não é a totalidade de Londrina. O volume retornado pelo Actor pode ser menor por filtros ou falhas de cobertura.

Os arquivos `apify_londrina_sale.json` e `apify_londrina_rental.json` podem ser colados na entrada JSON do Actor no Console. Ambos usam Londrina, PR, BOTH e todas as tipologias; são configurações, não dados imobiliários. Você também pode executar no Console e importar pelo ID no site.

## 4. Agendar semanalmente no notebook

Faça a primeira validação antes de habilitar a rotina. O agendamento abaixo realiza uma nova coleta paga por semana de **venda, todas as tipologias, até 100 anúncios**. Aluguel mensal pode ser executado separadamente pelo site.

No PowerShell da pasta do projeto:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\agendar_apify_windows.ps1
```

O Bypass vale somente para este processo que executa o script, sem alterar a política permanente. O script registra a tarefa `ImoveisHub-Apify-Londrina-Venda`, segunda-feira às 08:00 no horário local do Windows. Se necessário, confirme nas configurações do Windows que o fuso é o de Brasília.

**O notebook precisa estar ligado, conectado à internet e com seu usuário conectado.** A tarefa tenta executar quando ficar disponível após perder o horário. Não funciona com notebook desligado. A janela do site pode estar fechada. Se o administrador da empresa restringir tarefas agendadas, use a execução manual.

Para executar a rotina manualmente:

```powershell
.\coletar_apify_semanal.bat
```

Ela preserva um checkpoint por finalidade e semana ISO UTC, espera até 45 minutos pelo resultado e retoma o mesmo ID após timeout. Uma execução já concluída naquela semana não é repetida. Após uma interrupção que atravesse semanas, retoma primeiro a execução pendente; rode novamente depois para iniciar a semana atual.

Para alterar limites, edite tanto o BAT quanto o argumento `--max-items 100` no PS1 e registre a tarefa novamente. Não aumente sem conferir custo e cobertura. Não há teto monetário implementado: o limite é por quantidade de anúncios. O preço é definido pelo Actor/Apify.

Para remover o agendamento:

```powershell
Unregister-ScheduledTask -TaskName 'ImoveisHub-Apify-Londrina-Venda' -Confirm:$false
```

## 5. Execução no terminal e recuperação

```powershell
# Inicia nova coleta (paga) e imprime o run_id
.\.venv\Scripts\python.exe apify_cli.py start --business SALE --max-items 100

# Consulta/importa uma execução existente, sem iniciar outra coleta
.\.venv\Scripts\python.exe apify_cli.py sync --run-id COLE_O_ID

# Aluguel mensal, rotina retomável independente
.\.venv\Scripts\python.exe apify_cli.py weekly --business RENTAL --max-items 100

# Backup consistente do SQLite
.\.venv\Scripts\python.exe apify_cli.py backup
```

Se a conexão cair durante o POST que inicia uma coleta, ela pode ter sido iniciada remotamente. O checkpoint terá `uncertain: true`: a rotina para para evitar cobrar novamente. Abra Runs no Apify. Se localizar a execução de Londrina/finalidade correta, pare a tarefa local e edite `data/apify-weekly-SALE.json` (ou RENTAL): informe `run_id` com o ID existente, `uncertain: false`, `done: false`, preservando `week`. Rode o BAT novamente. Se confirmar que nenhuma execução iniciou, renomeie o checkpoint para `.json.bak` e execute novamente. Isso autoriza uma nova tentativa paga.

Em FAILED/ABORTED/TIMED-OUT remoto, a execução continua registrada e não é importada como uma coleta completa. Confira o diagnóstico no Console. Para uma nova tentativa paga, após revisar a falha, renomeie o checkpoint correspondente. Não exclua observações nem tabelas.

## 6. Histórico e interpretação

- `apify_runs`: identificador remoto, configuração sem segredos, datas, status e contagens.
- `apify_observations`: uma observação por execução/portal/ID/finalidade, com dados imobiliários selecionados. Sem retenção automática que apague observações.
- `imoveis`: projeção normalizada usada pelo mapa e análise existentes. IDs Apify usam sufixo `:SALE` / `:RENTAL` para manter finalidades distintas sem reescrever o banco antigo. A fonte é `Apify ZAP` ou `Apify VIVAREAL`, distinguindo métodos de coleta.
- Preço igual em semanas diferentes também é preservado. O ID original e o ID da execução permanecem no histórico detalhado.
- Não são armazenados nome, telefone, e-mail, CRECI ou outros dados pessoais do anunciante. Descrição livre, mídias e dados de contato não são arquivados. “Histórico completo” refere-se a todas as observações dos campos imobiliários selecionados e aceitos, não a uma cópia integral do HTML/dataset.
- Preservamos condomínio, IPTU (periodicidade declarada pelo Actor), área total e útil, suítes, banheiros, comodidades e datas da fonte no histórico detalhado. O PDF e o mapa atuais continuam usando seu conjunto de campos original.
- Preço/m² usa somente área útil. Área total não substitui área útil ausente. Apenas aluguel MONTHLY entra nas métricas, evitando misturar diária/semanal com mensal.
- Coordenadas dos portais são aproximadas. Fora de 100 km do centro de Londrina são retiradas do mapa, sem apagar o anúncio. Essa verificação não equivale a validar o polígono municipal.
- Os dois portais podem publicar o mesmo imóvel com o mesmo ID ou IDs distintos; as contagens representam anúncios por fonte. Ainda não há deduplicação de imóveis físicos entre portais/imobiliárias.
- Uma ausência em nova coleta não confirma venda, locação ou retirada. Nenhum anúncio é marcado como vendido automaticamente. Use o filtro de idade da coleta no mapa; anúncios antigos continuam no histórico.
- O histórico começa na primeira coleta importada. Mudanças ocorridas entre duas coletas semanais não podem ser reconstruídas sem uma fonte histórica adicional.
- A integração rejeita outros municípios, moedas e finalidades divergentes. A tabela de execuções registra as rejeições com números das linhas, sem copiar contatos. O dataset original permanece no Apify conforme a retenção da sua conta.

## 7. Backup e funcionamento na nuvem

A rotina semanal faz backups consistentes antes e depois da coleta/importação em `data/backups`, com verificação de integridade SQLite. O comando backup permite fazê-los antes de importações manuais. Copie periodicamente esses backups para outro dispositivo/local protegido: cópias no mesmo disco não protegem contra perda do notebook. Não há exclusão automática; acompanhe espaço disponível.

Para restaurar: pare o site e tarefas, preserve a pasta data atual renomeando-a, crie outra data e copie o backup como `imoveis.db`. Não reutilize arquivos WAL/SHM antigos. Se usa DATA_DIR/DATABASE_URL customizados, respeite o caminho configurado. A rotina de backup automático desta edição atende SQLite; PostgreSQL exige sua própria estratégia de backup.

O Apify também permite agendar Actors na nuvem. Isso mantém a coleta funcionando com notebook desligado, mas a importação para o seu banco local ainda depende do computador. Não há hospedagem nem agendamento na conta Apify ativados por esta entrega. Não habilite os dois agendamentos de coleta para a mesma finalidade/horário sem ajustar o fluxo, para evitar cobranças duplicadas.

Documentação: https://docs.apify.com/api/v2 ; https://docs.apify.com/actors/running/schedules
