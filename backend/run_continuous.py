import urllib.request
import urllib.error
import json
import sys
import subprocess
import time
import sqlite3
from pathlib import Path

API_URL = "http://127.0.0.1:8000"

def get_latest_converged_leaf():
    db_path = Path(__file__).resolve().parent / "app" / "data" / "workflows.db"
    if not db_path.exists():
        return None
    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute("""
            SELECT workflow_id 
            FROM workflows 
            WHERE job_status = 'converged' 
              AND workflow_id NOT IN (SELECT parent_id FROM workflow_chains)
            ORDER BY updated_at DESC
            LIMIT 1
        """)
        row = c.fetchone()
        conn.close()
        if row:
            return row[0]
    except Exception as e:
        print(f"Error querying database: {e}")
    return None

def post_apply_recommendation(workflow_id):
    url = f"{API_URL}/workflows/{workflow_id}/apply-recommendation"
    req = urllib.request.Request(url, data=b'')
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode('utf-8'))
    except Exception as e:
        print(f"Error applying recommendation: {e}")
        return None

def get_recommendation_preview(workflow_id):
    url = f"{API_URL}/workflows/{workflow_id}/recommendation-preview"
    try:
        with urllib.request.urlopen(url) as response:
            return json.loads(response.read().decode('utf-8'))
    except Exception as e:
        print(f"Error fetching recommendation preview: {e}")
        return None

def main():
    print(f"=== Starting Continuous Execution Step ===")
    
    # Check if parent ID is provided as argument, otherwise find latest converged leaf
    if len(sys.argv) > 1:
        parent_id = sys.argv[1]
        print(f"Using parent workflow ID from command line arguments: {parent_id}")
    else:
        parent_id = get_latest_converged_leaf()
        if parent_id:
            print(f"Automatically identified latest converged leaf workflow: {parent_id}")
        else:
            # Fallback to the last hardcoded ID if database query returns nothing
            parent_id = "14c2d96b-89a2-4653-9bdd-2da1ee02c0db"
            print(f"No converged leaf workflow found in database. Using fallback parent ID: {parent_id}")
            
    print(f"Applying recommendation for parent workflow: {parent_id}")
    
    # 1. Apply recommendation to create a new workflow
    child_wf = post_apply_recommendation(parent_id)
    if not child_wf:
        print("Failed to apply recommendation. Make sure the FastAPI backend is running.")
        sys.exit(1)
        
    child_id = child_wf.get("workflow_id")
    project_name = child_wf.get("project_name")
    goal = child_wf.get("goal")
    print(f"\nCreated Child Workflow:")
    print(f"  ID: {child_id}")
    print(f"  Project Name: {project_name}")
    print(f"  Goal: {goal}")
    print(f"  Job Status: {child_wf.get('job_status')}")
    print(f"  Agent Status: {child_wf.get('agent_status')}")
    
    # 2. Run auto_advance.py on the new workflow ID
    print(f"\nStarting auto_advance.py on workflow {child_id}...")
    
    # We call the python interpreter in the virtual environment to run auto_advance.py
    # Since we are in the backend directory or root, let's execute auto_advance.py
    cmd = [sys.executable, "app/auto_advance.py", child_id]
    
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    
    # Print stdout in real-time
    for line in process.stdout:
        print(line, end="")
        
    process.wait()
    if process.returncode != 0:
        print(f"\nAuto-advance failed with exit code {process.returncode}")
        sys.exit(process.returncode)
        
    print("\nWorkflow execution finished successfully!")
    
    # 3. Fetch recommendation for the next step (planning)
    print("\nFetching recommendation for the next planning step...")
    next_preview = get_recommendation_preview(child_id)
    if next_preview:
        print("\n=== PLANNED NEXT STEP ===")
        print(f"Recommended Step: {next_preview.get('recommended_step')}")
        print(f"Calculation Type: {next_preview.get('calculation_type')}")
        print(f"Goal: {next_preview.get('goal')}")
        print(f"Summary: {next_preview.get('summary')}")
        print("=========================")
    else:
        print("Could not retrieve next planning step.")

if __name__ == "__main__":
    main()
