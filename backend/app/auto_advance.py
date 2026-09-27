#!/usr/bin/env python3
import sys
import time
import urllib.request
import urllib.error
import json
import sqlite3
from pathlib import Path

API_URL = "http://127.0.0.1:8000"

def get_workflow(workflow_id):
    try:
        url = f"{API_URL}/workflows/{workflow_id}"
        with urllib.request.urlopen(url) as response:
            return json.loads(response.read().decode('utf-8'))
    except Exception as e:
        print(f"Error fetching workflow: {e}")
        return None

def advance_workflow(workflow_id):
    try:
        url = f"{API_URL}/workflows/{workflow_id}/advance"
        req = urllib.request.Request(url, data=b'')
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode('utf-8'))
    except Exception as e:
        print(f"Error advancing workflow: {e}")
        return None

def get_history_count(workflow_id):
    db_path = Path(__file__).resolve().parent / "data" / "workflows.db"
    if not db_path.exists():
        return 0
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM workflow_history WHERE workflow_id = ?", (workflow_id,))
        count = cursor.fetchone()[0]
        conn.close()
        return count
    except Exception as e:
        print(f"Database error: {e}")
        return 0

def main():
    workflow_id = sys.argv[1] if len(sys.argv) > 1 else "f38abc28-5693-48d1-a20e-e71aa723a840"
    print(f"=== Auto-Advancing Workflow: {workflow_id} ===")

    while True:
        wf = get_workflow(workflow_id)
        if not wf:
            print("Workflow not found. Exiting.")
            sys.exit(1)

        job_status = wf.get("job_status")
        agent_status = wf.get("agent_status")
        current_stage = wf.get("current_stage")
        stage_name = wf.get("execution_metadata", {}).get("current_stage_name")
        workflow_stages = wf.get("execution_metadata", {}).get("workflow_stages", [])

        print(f"\nCurrent State:")
        print(f"  Stage: {current_stage} ({stage_name}) of {workflow_stages}")
        print(f"  Job Status: {job_status}")
        print(f"  Agent Status: {agent_status}")

        if job_status == "failed" or agent_status == "failed":
            print("Workflow failed. Exiting.")
            sys.exit(1)

        if job_status == "converged":
            # Check if this was the last stage
            if current_stage >= len(workflow_stages) - 1 or stage_name == workflow_stages[-1]:
                print("\n==============================================")
                print("SUCCESS: Workflow fully executed and converged!")
                print("==============================================")
                sys.exit(0)
            else:
                print(f"Stage converged. Advancing to next stage...")
        else:
            print(f"Workflow is in status '{job_status}'. Waiting for convergence or next action...")

        # Record history count before triggering advance
        initial_history_count = get_history_count(workflow_id)

        # Trigger advance
        print("Calling /advance endpoint...")
        advance_res = advance_workflow(workflow_id)
        if not advance_res:
            print("Failed to advance. Retrying in 5 seconds...")
            time.sleep(5)
            continue

        # Poll database / API until the background step completes
        print("Waiting for background task to complete...")
        time.sleep(3) # Give it a head start

        polls = 0
        while True:
            wf_current = get_workflow(workflow_id)
            current_history_count = get_history_count(workflow_id)
            
            # If history count increased, it means the background thread finished!
            if current_history_count > initial_history_count:
                print(f"Background advance completed (history count increased from {initial_history_count} to {current_history_count}).")
                break

            current_job_status = wf_current.get("job_status") if wf_current else "unknown"
            current_agent_status = wf_current.get("agent_status") if wf_current else "unknown"
            
            # Check for failures immediately
            if current_job_status == "failed" or current_agent_status == "failed":
                print("Error: Workflow failed during execution step.")
                sys.exit(1)

            polls += 1
            if polls % 5 == 0:
                print(f"  ...still running (status: job={current_job_status}, agent={current_agent_status})")
            time.sleep(1)

        # Sleep briefly before starting next loop iteration
        time.sleep(1)

if __name__ == "__main__":
    main()
