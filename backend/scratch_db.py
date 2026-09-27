import sqlite3

db_path = r"c:\Users\wand\Desktop\projetos_pessoais\workflow-vasp\backend\app\data\workflows.db"
conn = sqlite3.connect(db_path)
c = conn.cursor()

for table in ['workflow_chains', 'workflow_history', 'workflow_results', 'workflow_metadata']:
    c.execute(f"PRAGMA table_info({table})")
    cols = c.fetchall()
    print(f"{table} columns:")
    for col in cols:
        print(f"  {col[1]} ({col[2]})")

print("-" * 50)
c.execute("SELECT * FROM workflows ORDER BY updated_at DESC LIMIT 10")
db_cols = [d[0] for d in c.description]
rows = c.fetchall()
for r in rows:
    row_dict = dict(zip(db_cols, r))
    print(f"ID: {row_dict.get('workflow_id')}")
    print(f"  Project: {row_dict.get('project_name')}")
    print(f"  Goal: {row_dict.get('goal')}")
    print(f"  Executor: {row_dict.get('executor')}")
    print(f"  Status: Job={row_dict.get('job_status')}, Agent={row_dict.get('agent_status')}")
    print(f"  Stage: {row_dict.get('current_stage')}")
    print(f"  Updated At: {row_dict.get('updated_at')}")
    print("-" * 50)

conn.close()
