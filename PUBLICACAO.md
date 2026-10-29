# Publicação dos resultados nominais

O dashboard usa um índice `docs/assets/data_bundle.js` e fragmentos em
`docs/assets/run_data/`. Os dados completos de um cenário são carregados apenas
quando ele é selecionado. Até dois cenários completos permanecem em memória.
Os fragmentos preservam todas as métricas e camadas, com nomes derivados do
conteúdo para evitar cache de outra versão. O gerador limita cada arquivo
público a menos de 50 MiB; isso não é uma validação do tamanho total do site.

`docs/assets/data/critical_waypoints/passage_events.jsonl` é uma auditoria local
que o site não lê. Ela continua sendo gerada no Lessonia, mas está no `.gitignore`.
Os JSONs completos em `docs/assets/data/runs/` também ficam locais: são cópias
dos dados disponíveis nos fragmentos, desnecessárias para o navegador. Use os
arquivos locais para análises e auditorias; preserve-os no backup do servidor.

## Converter resultados já processados

Depois de atualizar o código, sem recalcular métricas:

```bash
.venv/bin/python prepare_publication.py
```

O comando converte o pacote monolítico existente ou reempacota um índice já
fragmentado. Ele preserva os rankings, métricas e auditorias, atualiza a interface
e suas versões de cache e verifica o tamanho dos arquivos públicos. Fragmentos
gerados que deixaram de ser usados são retirados da saída atual.

Novas execuções de `generate_reports.py` já usam esse formato.

## Recuperar um push recusado por arquivos grandes

Remover um arquivo em um commit seguinte não o remove dos commits anteriores.
O GitHub continuará recusando o push se esses commits estiverem no histórico
enviado. O procedimento abaixo preserva os commits locais em uma branch de
backup e cria uma nova publicação a partir de `origin/main`, sem incluir o
histórico recusado e sem force push.

Primeiro, no Windows, envie o commit da correção de código e de publicação para
o GitHub. Só então execute os comandos abaixo no Lessonia.

Confira `git status --short`: ele deve estar vazio. Se houver alterações ainda
não commitadas, preserve-as antes de trocar de branch. Os nomes de branch abaixo
devem estar livres; se já existirem, use outros nomes em todos os comandos.

```bash
cd ~/post-processing
git status --short
git branch codex/backup-publicacao-grande
git fetch origin
git switch -c codex/publicacao-corrigida origin/main
```

Recupere somente os arquivos gerados do commit local anterior, mantendo o código
da correção que veio de `origin/main`:

```bash
git restore --source=codex/backup-publicacao-grande --worktree -- docs/
.venv/bin/python prepare_publication.py
```

Se a conversão falhar, pare antes de fazer o commit. O backup continua contendo
os resultados anteriores. Depois de uma conversão bem-sucedida, confira os
arquivos a publicar:

```bash
git add -A docs/
git diff --cached --stat
git ls-files docs/assets/data/critical_waypoints/passage_events.jsonl docs/assets/data/runs/
```

O último comando não deve listar nada. Os arquivos continuam no disco, mas não
devem fazer parte do commit novo. Então publique:

```bash
git commit -m "Publica cenarios nominais com dados divididos por cenario"
git push origin HEAD:main
```

O push envia somente a branch corrigida para `main`; não envie a branch de backup
nem use `git push --all`. Se o remoto avançar nesse intervalo, o push será recusado
normalmente: integre os novos commits na branch corrigida antes de tentar de novo.

Após um push bem-sucedido, atualize também a branch `main` local do Lessonia para
continuar trabalhando nela. Isso move somente a referência local; o histórico
anterior permanece na branch de backup:

```bash
git branch -f main HEAD
git switch main
```

No Windows, execute `git pull --ff-only` para receber os resultados publicados.
