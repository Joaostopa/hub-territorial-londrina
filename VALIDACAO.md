# Validação da atualização Apify — 09/09/2026

58 testes passaram em Python 3.12/Linux (48 anteriores + 10 novos). Novos cenários: histórico com mudança de preço, reimportação idempotente, descarte de contatos, rejeição de cidade/moeda/finalidade, venda e aluguel separados, área útil/geo ausentes, paginação com 2001 itens, interrupção sem gravação parcial, backup e restauração, início remoto incerto sem repetir cobrança, retomada e interface Streamlit com histórico.

As respostas Apify foram simuladas exclusivamente nos testes. Não executamos o Actor com credenciais do usuário e não adicionamos esses dados de teste à base real. O contrato de entrada/saída veio da página do Actor e do Markdown enviado. A validação real depende da primeira execução autenticada. Não executamos o Agendador de Tarefas nem o VS Code em Windows neste ambiente.

A integração adiciona duas tabelas, sem migração destrutiva. O histórico detalhado conserva campos imobiliários selecionados, excluindo contatos e conteúdo livre do anunciante. O banco do usuário não está incluído no ZIP.

---

## Validação anterior (preservada para referência)

## Edição local para VS Code — 09/09/2026

48 testes passaram em Python 3.12/Linux (9,16 s), incluindo navegação, importação idempotente de 37 registros reais, descarte de coordenada incompatível com a cidade e fallback identificado do IBGE. Os adaptadores Python reproduziram os HTMLs consultados em 08/09/2026: Human 10 anúncios/9 posições, Santamérica 27 anúncios/0 posições. Reexecução da preparação: 0 novos e 37 duplicados.

A integração com VS Code foi conferida por configuração; Windows não foi executado neste ambiente. Dados datados de 08/09/2026 não comprovam disponibilidade atual. Renda e idade são municipais e não estimativas do círculo.

## Atualização — coleta multifuente, 07/09/2026

44 testes passaram, incluindo paginação, deduplicação, persistência parcial, limites, separação venda/aluguel, robots, timeout e navegação da tela Fontes e coletas. Respostas controladas; não são testes ao vivo. Sondagens diretas: ReadTimeout em sete fontes e IBGE, registradas em `validacao/acesso_direto_2026-09-07.json`. Nenhum anúncio real foi coletado automaticamente nesta validação.

# Validação da entrega — 07/09/2026

- Python 3.12, Linux; dependências principais conforme requirements.txt.
- **38 testes passaram** na suíte pytest (5,36 segundos na última execução).
- AppTest: inicialização vazia, navegação, desenho simulado, preservação de seleção ao trocar filtros e exclusão.
- JavaScript gerado pelo Folium real passou em `node --check`.
- PDF de demonstração: 46 anúncios fictícios, 6 páginas; fontes incorporadas e páginas renderizadas/revisadas.
- Nenhuma mensagem de e-mail ou WhatsApp real enviada; testes usam mocks.

Não homologados ao vivo: coleta dos portais, IBGE/Overpass/Nominatim, OIDC, PostgreSQL, SMTP e WhatsApp. O teste de mapa não envolveu um navegador real. Instalação Windows e conversão de shapefile precisam ser verificadas no ambiente de destino. Consulte o README para configuração e limites de cada módulo.
