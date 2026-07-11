# Workflow VASP AI Assistant

An intelligent assistant and expert agent for DFT (Density Functional Theory) workflows with VASP. The system's focus is to automate and reduce manual intervention in recurring calculations, covering directory inspection, error/convergence detection, suggestion/application of corrections, and orchestration of multiple adaptive steps.

---

## 🚀 System Scope

This project implements:
- **FastAPI API:** Unified interface for workflow control, cluster monitoring, physical analysis, and agent recommendations.
- **Graphical Interface (Dashboards):** Three CSS-rich panels to monitor workflows, manage clusters, and run physics and geometry analyses.
- **Expert Agent (VASP Agent):** Engine based on heuristics and a JSON knowledge base to analyze outputs (`OUTCAR`, `OSZICAR`, `INCAR`) and detect convergence or failures (e.g., numerical error `zbrent`, electronic convergence issues, etc.).
- **History Persistence:** Local SQLite database saving logs, job metadata, configurations, and execution timelines.
- **Three Calculation Executors:**
  - `mock`: Staged local simulation without requiring a cluster.
  - `ssh_slurm`: Real SSH integration with SLURM submission, supporting `dry-run` mode to generate submit scripts and commands without triggering the server.
  - `mlff_training`: Active training orchestrator for machine learning force field potentials (Machine Learning Force Fields - MLFF).
- **Physical Analysis Tools:** Effective Coordination Number (ECN) analysis, binding energy calculations, and automatic diagnostics (band gap, neb path, mlff quality, etc.).

---

## 📂 Project Structure

```text
workflow-vasp/
├── backend/
│   ├── app/
│   │   ├── data/                 # SQLite (workflows.db), config.json, VASP error KB (Knowledge Base)
│   │   ├── services/             # Business logic (agent, analyzer, parser, templates, ECN, executors)
│   │   ├── static/               # Frontend Web Interface (HTML, CSS, JS)
│   │   ├── templates/            # Internal default VASP templates
│   │   ├── mlff_runs/            # Local execution directories for MLFF training
│   │   ├── mock_runs/            # Local execution directories for simulated jobs
│   │   ├── remote_runs/          # Local cache directories for remote executions (dry-run/real)
│   │   ├── main.py               # API HTTP routes
│   │   └── schemas.py            # Pydantic data models
│   ├── tests/                    # Agent automated test suite
│   └── requirements.txt          # Python dependencies
├── templates/                    # Custom user VASP templates in the root directory
└── README.md                     # General project documentation
```

---

## ⚙️ How to Run Locally

Ensure you have Python 3.10+ installed.

```bash
# 1. Navigate to the backend directory
cd backend

# 2. Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate      # On Windows
source .venv/bin/activate    # On Linux/macOS

# 3. Install dependencies
pip install -r requirements.txt

# 4. Start the FastAPI server with live-reload
uvicorn app.main:app --reload
```

After starting, the frontend dashboards will be accessible at the following routes:
- **General Workflow Dashboard:** [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
- **Physical Analysis Panel:** [http://127.0.0.1:8000/analysis](http://127.0.0.1:8000/analysis)
- **SSH/SLURM Cluster Management Panel:** [http://127.0.0.1:8000/cluster](http://127.0.0.1:8000/cluster)

The interactive API Swagger is available at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

---

## 🖥️ Frontend Dashboards (Web Routes)

The integrated web panels are served directly by FastAPI from the `static/` folder:

1. **Main Dashboard (`GET /`)**
   Complete visualization of created workflows. Allows the creation of new workflows (selecting executor, scenario, and objectives), real-time monitoring of the execution timeline, and manual or automatic application of agent suggestions.
   
2. **Analysis Panel (`GET /analysis`)**
   Executes and displays deep diagnostics on workflow results. Allows visualizing the ECN of atoms in a POSCAR structure and selecting multiple completed workflows to calculate the molecular binding energy.
   
3. **Cluster Management Panel (`GET /cluster`)**
   Allows viewing and editing locally saved SSH and SLURM configurations, registering temporary session passwords (which are not persisted in files for security), and viewing the real-time list of remote jobs running in the cluster queue (`squeue`).

---

## 🛠️ Executors and Working Modes

### 1. Simulated Executor (`mock`)
Allows developing and testing all API logic without requiring a real VASP calculation server or network connections. It reads predefined scenarios from `backend/app/mock_runs/` and generates simulated outputs.
* **Available Simulation Scenarios:**
  - `success`: The calculation converges directly in the first run.
  - `running`: Simulates a calculation that starts pending/running and converges after advancing the stage.
  - `zbrent_error`: Simulates a numerical failure from a breakdown in the `zbrent` minimization algorithm during the first stage, which is correctable by the agent modifying `INCAR` parameters, converging in the subsequent run.
  - `dos_ready`: Simulates a converged relaxation calculation, ready to start a subsequent Density of States (DOS) step.

### 2. SSH/SLURM Executor (`ssh_slurm`)
Provides integration for remote calculation submission on clusters using the SLURM scheduler.
* **Dry Run Mode (`dry_run = true`):** Does not open SSH connections. Prepares the submission script `submit_vasp.slurm` locally, generates the command plan in `REMOTE_PLAN.txt`, and saves command logs to `command_log.json`.
* **Real Mode (`dry_run = false`):** Uses SSH keys and configured session passwords to `scp` input files, submits calculations via `sbatch` on the cluster, and monitors progress.

### 3. MLFF Training Executor (`mlff_training`)
Specifically developed for training VASP Machine Learning Force Fields (MLFF).
* Enables specific `INCAR` keys (`ML_LMLFF = .TRUE.`, `ML_MODE = select/train/validate`).
* Simulates data sampling and active learning loops over temperature and physical force tolerance (`ML_CTIFOR`).
* Returns whether the trained potential is reliable and of high enough quality to be promoted for production benchmarking.

---

## 🔬 Physics and Chemistry Analysis Tools

The analysis panel connects to dedicated endpoints to extract structural and energetic data from calculations:

### Effective Coordination Number (ECN)
* **Route:** `GET /workflows/{workflow_id}/ecn`
* **Implementation:** [EcnService](file:///c:/Users/wand/Desktop/projetos_pessoais/workflow-vasp/backend/app/services/ecn_service.py)
* **Purpose:** Computes the ECN per atom based on a self-consistent approach over the atomic distance matrix. Returns minimum bond distances, weighted average bond lengths (rwabl), three-dimensional supercell coordinates, and the overall average ECN.

### Binding Energy Calculation
* **Route:** `POST /analysis/binding-energy`
* **Implementation:** [VaspAnalysisService](file:///c:/Users/wand/Desktop/projetos_pessoais/workflow-vasp/backend/app/services/vasp_analysis_service.py)
* **Purpose:** Allows selecting an adsorbate/surface calculation and subtracting the energies of the isolated component systems to find the final binding/adsorption energy:
  $$E_{\text{bind}} = E_{\text{target}} - \sum E_{\text{references}}$$

### Results Diagnostic Modules
The `GET /workflows/{workflow_id}/analysis` route runs detailed heuristics based on VASP output files:
* **Band Gap Check:** Analyzes energy eigenvalues (`OUTCAR`) and infers whether the material is a semiconductor, insulator, or metal, calculating the electronic band gap.
* **NEB Path Check:** Analyzes Nudged Elastic Band (NEB) reaction paths (intermediate images) to ensure coherent and collision-free geometric pathways.
* **MLFF Quality:** Verifies the convergence of force/energy RMSE in MLFF training outputs.
* **Convergence & Stability:** Identifies SCF energy oscillations or divergence and suggests changes to electronic density mixing.

---

## 🔁 Dynamic Recommendation and Intervention Flow

The agent not only detects problems but also allows interacting with them:

1. **Manual Inspection and Editing:**
   * Through the `GET /workflows/{workflow_id}/files-preview` endpoint, the user can preview active inputs.
   * Modifying `INCAR` parameters or `KPOINTS` grids can be rewritten directly via `POST /workflows/{workflow_id}/files`.
2. **Recommendation Preview:**
   * The `GET /workflows/{workflow_id}/recommendation-preview` route returns what adaptive action the agent advises based on physical analysis and calculation status.
3. **Chaining Steps:**
   * Running `POST /workflows/{workflow_id}/apply-recommendation` creates a new derived workflow using the latest structure artifacts (such as promoting `CONTCAR` to `POSCAR`) and applying the appropriate calculation recipes (e.g., migrating from a successful geometric relaxation to a Density of States (DOS) or Phonon calculation).

---

## 🔮 Suggested Next Steps

- **Asynchronous Queue Orchestration:** Implement background execution queues using Celery or RQ with Redis to remove synchronous processing of long SSH connections.
- **Multi-user Persistence:** Replace the local SQLite database (`workflows.db`) with a structured PostgreSQL image when scaling the system for collaborative laboratory use.
- **Semantic POSCAR Validator:** Prevent remote submissions if the POSCAR contains overlapping atoms or simulation box inconsistency.
- **Interactive Visualizations:** Add 3D crystal structure visualization (`POSCAR` / `CONTCAR`) in the frontend using JS/Three.js or similar libraries.
