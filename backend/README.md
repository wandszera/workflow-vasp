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

## Proximos passos sugeridos

- integrar SLURM com `submit_job()`
- persistir workflows em SQLite/Postgres
- adicionar fila com Celery/RQ
- criar templates por tipo de calculo
- acoplar frontend para acompanhar status
