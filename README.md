# Workflow VASP AI Assistant

Assistente inteligente e agente especialista em workflows de DFT (Density Functional Theory) com VASP. O foco do sistema é automatizar e reduzir a intervenção manual em cálculos recorrentes, abrangendo inspeção de diretórios, detecção de erros/convergência, sugestão/aplicação de correções e orquestração de múltiplos passos adaptativos.

---

## 🚀 Escopo do Sistema

Este projeto implementa:
- **FastAPI API:** Interface unificada para controle de workflows, monitoramento de cluster, análise física e recomendações do agente.
- **Interface Gráfica (Dashboards):** Três painéis ricos em CSS para monitorar workflows, gerenciar cluster e rodar análises de física e geometria.
- **Agente Especialista (VASP Agent):** Motor baseado em heurísticas e base de conhecimento JSON para analisar saídas (`OUTCAR`, `OSZICAR`, `INCAR`) e detectar convergência ou falhas (ex: erro numerico `zbrent`, problemas de convergência eletrônica, etc.).
- **Persistência de Histórico:** Banco de dados SQLite local salvando logs, metadados de jobs, configurações e timelines de execução.
- **Três Executores de Cálculo:**
  - `mock`: Simulação local estagiada sem necessidade de cluster.
  - `ssh_slurm`: Integração SSH real com submissão SLURM, com suporte a modo `dry-run` para gerar scripts e comandos de envio sem acionar o servidor.
  - `mlff_training`: Orquestrador de treino ativo de potenciais de aprendizado de máquina (Machine Learning Force Fields - MLFF).
- **Ferramentas de Análise Física:** Análise de Effective Coordination Number (ECN), energia de ligação (Binding Energy) e diagnósticos automáticos (band gap, neb path, mlff quality, etc.).

---

## 📂 Estrutura do Projeto

```text
workflow-vasp/
├── backend/
│   ├── app/
│   │   ├── data/                 # SQLite (workflows.db), config.json, KB de erros do VASP
│   │   ├── services/             # Lógica de negócio (agente, analisador, parser, templates, ECN, executores)
│   │   ├── static/               # Interface Web Frontend (HTML, CSS, JS)
│   │   ├── templates/            # Templates VASP internos padrões
│   │   ├── mlff_runs/            # Diretórios locais de execução do treino MLFF
│   │   ├── mock_runs/            # Diretórios locais de execução de jobs simulados
│   │   ├── remote_runs/          # Diretórios locais de cache de execuções remotas (dry-run/real)
│   │   ├── main.py               # Rotas HTTP da API
│   │   └── schemas.py            # Modelos de dados Pydantic
│   ├── tests/                    # Suíte de testes automatizados do agente
│   └── requirements.txt          # Dependências do Python
├── templates/                    # Templates VASP customizados do usuário na raiz
└── README.md                     # Documentação geral do projeto
```

---

## ⚙️ Como Rodar Localmente

Certifique-se de ter o Python 3.10+ instalado.

```bash
# 1. Navegue até o diretório do backend
cd backend

# 2. Crie e ative o ambiente virtual
python -m venv .venv
.venv\Scripts\activate      # No Windows
source .venv/bin/activate    # No Linux/macOS

# 3. Instale as dependências
pip install -r requirements.txt

# 4. Inicie o servidor FastAPI com live-reload
uvicorn app.main:app --reload
```

Após iniciar, os dashboards frontend estarão acessíveis nas seguintes rotas:
- **Painel Geral de Workflows:** [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
- **Painel de Análise Física:** [http://127.0.0.1:8000/analysis](http://127.0.0.1:8000/analysis)
- **Painel do Cluster SSH/SLURM:** [http://127.0.0.1:8000/cluster](http://127.0.0.1:8000/cluster)

O Swagger interativo da API está disponível em [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

---

## 🖥️ Dashboards Frontend (Rotas Web)

Os painéis web integrados são servidos diretamente pelo FastAPI a partir da pasta `static/`:

1. **Dashboard Principal (`GET /`)**
   Visualização completa dos workflows criados. Permite a criação de novos workflows (selecionando executor, cenário e objetivos), acompanhamento em tempo real da timeline de execução e aplicação manual ou automática das sugestões do agente.
   
2. **Painel de Análise (`GET /analysis`)**
   Executa e exibe diagnósticos aprofundados sobre os resultados de um workflow. Permite visualizar o ECN dos átomos de uma estrutura POSCAR e selecionar múltiplos workflows concluídos para calcular a energia de ligação molecular.
   
3. **Painel de Gerenciamento do Cluster (`GET /cluster`)**
   Permite visualizar e editar as configurações SSH e SLURM salvas localmente, cadastrar senhas temporárias de sessão (que não são persistidas em arquivo para maior segurança) e visualizar em tempo real a lista de jobs remotos rodando na fila do cluster (`squeue`).

---

## 🛠️ Executores e Modos de Trabalho

### 1. Executor Simulado (`mock`)
Permite desenvolver e testar toda a lógica da API sem a necessidade de um servidor de cálculos VASP real ou conexões de rede. Ele lê cenários predefinidos a partir de `backend/app/mock_runs/` e gera saídas simuladas.
* **Cenários de Simulação Disponíveis:**
  * `success`: O cálculo converge diretamente na primeira rodada.
  * `running`: Simula um cálculo que inicia pendente/rodando e converge após o avanço do estágio.
  * `zbrent_error`: Simula uma falha numérica de quebra do algoritmo de minimização `zbrent` no primeiro estágio, corrigível via agente modificando parâmetros de `INCAR`, convergindo na rodada seguinte.
  * `dos_ready`: Simula um cálculo de relaxação convergido, pronto para iniciar uma etapa subsequente de Densidade de Estados (DOS).

### 2. Executor SSH/SLURM (`ssh_slurm`)
Fornece integração para submissão remota de cálculos em clusters baseados no agendador SLURM.
* **Modo Dry Run (`dry_run = true`):** Não abre conexões SSH. Prepara localmente o script de submissão `submit_vasp.slurm`, gera o plano de comandos em `REMOTE_PLAN.txt` e salva os logs de comandos planejados em `command_log.json`.
* **Modo Real (`dry_run = false`):** Utiliza chaves SSH e senhas de sessão configuradas para efetuar `scp` dos arquivos de input, submeter o cálculo via `sbatch` no cluster e monitorar seu progresso.

### 3. Executor de Treinamento MLFF (`mlff_training`)
Desenvolvido especificamente para treinar Potenciais baseados em Aprendizado de Máquina (Machine Learning Force Fields) do VASP.
* Habilita chaves específicas no `INCAR` (`ML_LMLFF = .TRUE.`, `ML_MODE = select/train/validate`).
* Simula a amostragem de dados e loops de aprendizado ativo sobre temperatura e tolerância de força física (`ML_CTIFOR`).
* Retorna se o potencial treinado é confiável e possui qualidade suficiente para ser promovido para benchmarking de produção.

---

## 🔬 Análise e Ferramentas Físico-Químicas

O painel de análises conecta endpoints dedicados para extrair dados estruturais e energéticos dos cálculos:

### Número de Coordenação Efetivo (ECN)
* **Rota:** `GET /workflows/{workflow_id}/ecn`
* **Implementação:** [EcnService](file:///c:/Users/wand/Desktop/projetos_pessoais/workflow-vasp/backend/app/services/ecn_service.py)
* **Objetivo:** Computa o ECN por átomo baseando-se em uma abordagem autoconsistente sobre a matriz de distâncias atômicas. Retorna distâncias de ligação mínimas, médias ponderadas (rwabl), coordenadas de supercélula tridimensional e o ECN médio global.

### Cálculo de Energia de Ligação (Binding Energy)
* **Rota:** `POST /analysis/binding-energy`
* **Implementação:** [VaspAnalysisService](file:///c:/Users/wand/Desktop/projetos_pessoais/workflow-vasp/backend/app/services/vasp_analysis_service.py)
* **Objetivo:** Permite selecionar um cálculo de adsorbato/superfície e descontar as energias dos sistemas isolados componentes para encontrar a energia de ligação/adsorção final:
  $$E_{\text{lig}} = E_{\text{alvo}} - \sum E_{\text{referências}}$$

### Módulos de Diagnósticos de Resultados
A rota `GET /workflows/{workflow_id}/analysis` executa heurísticas detalhadas baseadas em arquivos de saída do VASP:
* **Band Gap Check:** Analisa os autovalores de energia (`OUTCAR`) e infere se o material é semicondutor, isolante ou metálico, calculando o gap de banda eletrônica.
* **NEB Path Check:** Analisa caminhos de reação de Nudged Elastic Band (imagens intermediárias) para garantir caminhos geométricos coerentes e livres de colisões.
* **MLFF Quality:** Verifica a convergência de RMSE de forças/energias em saídas de treino MLFF.
* **Convergência & Estabilidade:** Identifica oscilações de energia SCF ou divergências e sugere alterações na mistura de densidades eletrônicas.

---

## 🔁 Fluxo Dinâmico de Recomendações e Intervenção

O agente não apenas detecta problemas, mas permite agir sobre eles interativamente:

1. **Inspeção Manual e Edição:**
   * Através do endpoint `GET /workflows/{workflow_id}/files-preview`, o usuário visualiza os inputs ativos.
   * Modificações de parâmetros do `INCAR` ou malhas de `KPOINTS` podem ser reescritas diretamente via `POST /workflows/{workflow_id}/files`.
2. **Visualização de Recomendações:**
   * A rota `GET /workflows/{workflow_id}/recommendation-preview` retorna qual ação adaptativa o agente aconselha tomar com base na análise física e status do cálculo.
3. **Encadeamento de Etapas:**
   * Executando `POST /workflows/{workflow_id}/apply-recommendation`, o sistema cria um novo workflow derivado utilizando os artefatos de estrutura mais recentes (como o `CONTCAR` promovido a `POSCAR`) e aplicando as receitas de cálculo apropriadas (ex: migrar de uma relaxação geométrica bem-sucedida para um cálculo de Densidade de Estados (DOS) ou cálculo de Fônons).

---

## 🔮 Próximos Passos Sugeridos

- **Orquestração de Fila Assíncrona:** Implementar filas de execução em background usando Celery ou RQ com Redis para remover o processamento síncrono de conexões SSH demoradas.
- **Persistência Multiusuário:** Substituir o banco SQLite local (`workflows.db`) por uma imagem PostgreSQL estruturada quando o sistema for expandido para uso colaborativo em laboratório.
- **Validador Semântico de POSCAR:** Impedir submissões remotas caso o POSCAR possua sobreposição de átomos física ou incoerência na caixa de simulação.
- **Gráficos Interativos:** Adicionar visualização 3D da estrutura cristalina (`POSCAR` / `CONTCAR`) no frontend usando JS/Three.js ou bibliotecas similares.
