# Workflow VASP AI Assistant

MVP de um agente especialista em workflows de DFT com VASP. O foco desta primeira versao e reduzir intervencao manual em calculos recorrentes:

- inspecionar diretorios de calculo
- detectar convergencia e falhas comuns
- sugerir ou aplicar correcoes em `INCAR`
- organizar o proximo passo de um workflow

## Escopo do MVP

Este MVP implementa:

- API com FastAPI
- parser basico de `OUTCAR`, `OSZICAR` e `INCAR`
- agente especialista com regras heuristicas
- base de conhecimento em JSON para erros comuns do VASP
- simulador local de jobs para desenvolvimento sem cluster
- orquestracao de workflows com historico persistido

## Estrutura

```text
backend/
  app/
    data/
    services/
    main.py
    schemas.py
  tests/
```

## Como rodar

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn backend.app.main:app --reload
```

Abra `http://127.0.0.1:8000/` para usar o dashboard local.

## Endpoint principal

`POST /agent/inspect`

Exemplo de payload:

```json
{
  "calc_path": "C:/dados/projeto/pd_h2/run_01",
  "apply_fixes": false,
  "goal": "otimizacao geometrica seguida por DOS"
}
```

## Desenvolvimento sem cluster

Voce pode desenvolver o projeto inteiro sem SSH e sem VASP real usando o simulador local.

Agora existem dois executores disponiveis para o workflow:

- `mock`: simulacao local simples
- `ssh_slurm`: integracao inicial com SSH/SLURM em modo `dry-run`

### 1. Criar um job falso

`POST /mock/jobs`

```json
{
  "project_name": "pd_h2_adsorption",
  "scenario": "zbrent_error",
  "goal": "otimizacao geometrica seguida por DOS"
}
```

Esse endpoint cria um diretorio local em `backend/app/mock_runs/` com arquivos `INCAR`, `OUTCAR` e `OSZICAR` simulados.

### 2. Inspecionar com o agente

Pegue o `calc_path` retornado e envie para `POST /agent/inspect`.

### 3. Simular reexecucao

Para cenarios como `running` e `zbrent_error`, use:

`POST /mock/jobs/{job_id}/advance`

Isso avanca o estado do job falso para a proxima etapa, como se tivesse ocorrido uma nova submissao ou a convergencia do calculo.

### Cenarios disponiveis

- `success`: calculo convergido
- `running`: calculo em andamento no primeiro passo e convergido no segundo
- `zbrent_error`: falha numerica no primeiro passo e convergencia no segundo
- `dos_ready`: calculo pronto para testar encadeamento de DOS

## Workflow persistido

Se voce quiser trabalhar mais proximo da plataforma final, use os endpoints de workflow.

### Criar workflow local

`POST /workflows/mock`

```json
{
  "project_name": "pd_cluster_h2",
  "executor": "mock",
  "scenario": "running",
  "goal": "otimizar cluster e depois rodar DOS",
  "auto_apply_fixes": false
}
```

Esse endpoint:

- cria um job simulado
- executa a inspecao do agente
- salva estado e historico em `backend/app/data/workflows.db`

### Consultar workflow

- `GET /workflows`
- `GET /workflows/{workflow_id}`

### Avancar workflow

`POST /workflows/{workflow_id}/advance`

Isso simula o loop principal do orquestrador:

`Planejar -> Executar -> Verificar -> Corrigir -> Avancar`

Com essa camada voce ja consegue desenvolver:

- dashboard de status
- timeline do workflow
- regras de decisao do agente
- integracao futura com SSH/SLURM sem trocar a API externa

## Arquitetura atual

- `MockClusterService`: executor local para desenvolvimento sem cluster
- `WorkflowExecutor`: contrato para plugar executores futuros, como SSH/SLURM
- `WorkflowStore`: persistencia em SQLite usando `sqlite3` nativo do Python
- `SshSlurmExecutor`: executor inicial em `dry-run`, gerando plano de comandos remotos e script `sbatch`

Essa separacao permite trocar o executor no futuro sem alterar a API, o dashboard ou a logica do agente.

## Executor SSH/SLURM

O executor `ssh_slurm` agora suporta dois modos:

- `dry_run = true`: nao abre conexao, apenas gera o plano remoto
- `dry_run = false`: executa os comandos `ssh`, `scp` e `sbatch`

Por padrao, ele continua seguro em `dry_run`.

### Arquivo de configuracao

Crie `backend/app/data/cluster_config.json` a partir do exemplo `backend/app/data/cluster_config.example.json`.

Exemplo:

```json
{
  "ssh_host": "meu.cluster.br",
  "ssh_user": "wand",
  "remote_base_dir": "/scratch/wand/vasp-workflows",
  "dry_run": true,
  "identity_file": "C:/Users/wand/.ssh/id_rsa"
}
```

No modo `dry_run`, o executor prepara localmente:

- `submit_vasp.sh` com um exemplo de script SLURM
- `REMOTE_PLAN.txt` com os comandos `ssh`, `scp` e `sbatch` planejados
- `command_log.json` com o registro do que seria executado
- artefatos locais para o agente continuar funcionando

Isso te permite desenvolver:

- configuracao de submissao remota
- UX do fluxo de cluster
- estados e timeline de execucao
- integracao futura sem reestruturar o backend

Quando voce mudar `dry_run` para `false`, os comandos passam a ser executados de verdade pelo backend.

## Proximos passos sugeridos

- integrar SLURM com `submit_job()`
- evoluir a persistencia SQLite para Postgres quando houver multiusuario
- adicionar fila com Celery/RQ
- criar templates por tipo de calculo
- acoplar frontend para acompanhar status
