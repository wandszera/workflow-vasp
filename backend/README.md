# Workflow VASP - Backend Services

Este diretório contém a API e os serviços em Python que orquestram os workflows do VASP.

> [!NOTE]
> Para obter uma visão geral do sistema, descrição completa de funcionalidades (como ECN, Binding Energy, recomendador adaptativo) e capturas dos Dashboards, consulte o [README.md principal da raiz](../../README.md).

---

## 🛠️ Instalação e Execução

### Pré-requisitos
* Python 3.10 ou superior.

### 1. Criar Ambiente Virtual e Instalar Dependências
```bash
# Criar o ambiente virtual (.venv)
python -m venv .venv

# Ativar o ambiente virtual
# No Windows (PowerShell):
.venv\Scripts\Activate.ps1
# No Linux/macOS:
source .venv/bin/activate

# Instalar pacotes requeridos
pip install -r requirements.txt
```

### 2. Iniciar o Servidor de Desenvolvimento
```bash
# Inicia a API com recarregamento automático ao alterar arquivos
uvicorn app.main:app --reload
```
Acesse a documentação interativa dos endpoints (Swagger) em:
* [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

---

## ⚙️ Configuração do Cluster SSH/SLURM

Para utilizar o executor `ssh_slurm` real ou em modo de simulação local (`dry-run`), crie o arquivo de configurações em `app/data/cluster_config.json`. 

Você pode copiar a estrutura a partir do arquivo modelo `app/data/cluster_config.example.json`:

```json
{
  "ssh_host": "meu.cluster.br",
  "ssh_user": "usuario_ssh",
  "remote_base_dir": "/scratch/usuario_ssh/vasp-workflows",
  "dry_run": true,
  "identity_file": "C:/Users/usuario/.ssh/id_rsa"
}
```

### Detalhes das propriedades:
* `dry_run` (Padrão: `true`): Quando ativado, simula a montagem do script SLURM e gera arquivos locais com os comandos planejados (`REMOTE_PLAN.txt` e `submit_vasp.slurm`), sem efetuar conexões SSH. Altere para `false` para submissão real.
* `identity_file` (Opcional): Caminho absoluto para a chave privada SSH usada na autenticação.
* **Autenticação por Senha:** Se sua chave necessitar de senha ou o cluster utilizar senha padrão, envie a senha temporária através da rota `POST /cluster/session-password` ou utilize o painel `/cluster` no frontend. Esta senha permanece apenas em memória durante a sessão atual do FastAPI.

---

## 🧪 Testes Automatizados

A suíte de testes valida as regras do agente de decisão, parsers e orquestrador de workflows:

```bash
# Executar todos os testes usando pytest a partir da pasta /backend
pytest tests/
```

Para visualizar mensagens detalhadas e prints durante a execução dos testes:
```bash
pytest -s -v tests/
```
