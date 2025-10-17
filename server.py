# server.py (Single-Repo Version)
import os
import traceback
import tempfile
import shutil
import subprocess
import base64
import time
import requests

from fastapi import FastAPI, Request, HTTPException
from github import Github, GithubException
from dotenv import load_dotenv
from openai import OpenAI

# --- SETUP ---
load_dotenv()
app = FastAPI()

try:
    client = OpenAI(
        api_key=os.getenv("AI_PIPE_TOKEN"),
        base_url=os.getenv("AI_PIPE_URL")
    )
    MODEL_NAME = "google/gemini-2.0-flash-lite-001"
except Exception as e:
    print(f"Error configuring AI Pipe client: {e}")
    client = None

ALLOWED = {"student@example.com": os.getenv("ALLOWED_SECRET_FOR_TESTING")}
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

# --- IMPORTANT CONFIGURATION ---
# This MUST match the name of the GitHub repository where this code lives.
# For example: "my-llm-deployment-project"
REPO_NAME_CONFIG = "my-llm-deployment-project"


# --- HELPER FUNCTIONS ---
def generate_readme_content(task, brief, pages_url):
    return f"""# LLM Generated Project: {task}

This application was automatically generated and deployed in response to the following brief:

> *"{brief}"*

**Live Demo URL:** [{pages_url}]({pages_url})
"""

def generate_license_content(github_user_login):
    # Fixed: Now contains the full MIT License text.
    return f"""MIT License

Copyright (c) 2025 {github_user_login}

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

def generate_code_with_llm(brief, round_num, existing_code=None):
    if not client: raise HTTPException(status_code=500, detail="AI Pipe client not configured.")
    if round_num == 1:
        system_prompt = "You are an expert web developer. Your task is to create a single, complete HTML file based on a user's brief. The file must contain all necessary HTML, CSS, and JavaScript. Do not add any explanations or comments outside of the code. Respond ONLY with the raw HTML code."
        user_prompt = f'BRIEF: "{brief}"'
    else:
        system_prompt = "You are an expert web developer. Your task is to update an existing HTML file based on a new brief. The user will provide the original code and the new requirements. Respond ONLY with the full, updated raw HTML code. Do not add any explanations."
        user_prompt = f'BRIEF: "{brief}"\n\nORIGINAL CODE:\n---\n{existing_code}'
    try:
        completion = client.chat.completions.create(model=MODEL_NAME, messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}])
        clean_code = completion.choices[0].message.content.strip().replace("```html", "").replace("```", "").strip()
        return clean_code
    except Exception as e:
        print(f"AI Pipe call failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate code using AI Pipe.")

def post_with_retry(url, payload, max_attempts=5):
    delay = 1
    for _ in range(max_attempts):
        try:
            r = requests.post(url, json=payload, timeout=10)
            if r.status_code == 200:
                print("Successfully posted to evaluation URL.")
                return True
        except requests.RequestException as e:
            print(f"Request to evaluation URL failed: {e}")
        time.sleep(delay)
        delay *= 2
    return False

# --- MAIN API ENDPOINT ---
@app.post("/api-endpoint")
async def handle_request(request: Request):
    data = await request.json()
    try:
        email = data.get("email")
        secret = data.get("secret")
        if ALLOWED.get(email) != secret:
            raise HTTPException(status_code=403, detail="Secret mismatch")
        
        brief = data.get("brief")
        task = data.get("task")
        evaluation_url = data.get("evaluation_url")
        nonce = data.get("nonce")
        round_num = data.get("round", 1)
        
        gh = Github(GITHUB_TOKEN)
        user = gh.get_user()
        
        full_repo_name = f"{user.login}/{REPO_NAME_CONFIG}"
        repo = gh.get_repo(full_repo_name)

        project_root = os.getcwd()
        app_folder_name = f"{task}-{nonce}".replace(" ", "-").lower()
        app_path = os.path.join(project_root, "apps", app_folder_name)
        
        os.makedirs(os.path.join(project_root, "apps"), exist_ok=True)

        if round_num == 1:
            if os.path.exists(app_path):
                raise HTTPException(status_code=409, detail=f"App '{app_folder_name}' already exists.")
            os.makedirs(app_path)
            
            html_content = generate_code_with_llm(brief, round_num)
            pages_url = f"https://{user.login}.github.io/{REPO_NAME_CONFIG}/apps/{app_folder_name}/"
            readme_content = generate_readme_content(task, brief, pages_url)
            license_content = generate_license_content(user.login)

            with open(os.path.join(app_path, "index.html"), "w", encoding="utf-8") as f: f.write(html_content)
            with open(os.path.join(app_path, "README.md"), "w", encoding="utf-8") as f: f.write(readme_content)
            with open(os.path.join(app_path, "LICENSE"), "w", encoding="utf-8") as f: f.write(license_content)
            
            commit_message = f"feat: Create new app '{app_folder_name}'"
        
        else: # Round 2
            if not os.path.exists(app_path):
                raise HTTPException(status_code=404, detail=f"App '{app_folder_name}' not found for update.")
            
            try:
                with open(os.path.join(app_path, "index.html"), "r", encoding="utf-8") as f: existing_html = f.read()
            except FileNotFoundError: existing_html = ""

            new_html_content = generate_code_with_llm(brief, round_num, existing_code=existing_html)
            with open(os.path.join(app_path, "index.html"), "w", encoding="utf-8") as f: f.write(new_html_content)
            with open(os.path.join(app_path, "README.md"), "a", encoding="utf-8") as f: f.write(f"\n\n---\n\n### Round 2 Update\n\n> *\"{brief}\"*")
            
            commit_message = f"feat: Update app '{app_folder_name}' for Round 2"

        subprocess.run(["git", "config", "--global", "user.email", "action@github.com"], check=True)
        subprocess.run(["git", "config", "--global", "user.name", "GitHub Action"], check=True)
        subprocess.run(["git", "pull", "origin", "main"], check=True)
        subprocess.run(["git", "add", "."], check=True)
        subprocess.run(["git", "commit", "-m", commit_message], check=True)
        subprocess.run(["git", "push", "origin", "main"], check=True)
        
        commit_sha = repo.get_branch("main").commit.sha
        pages_url = f"https://{user.login}.github.io/{REPO_NAME_CONFIG}/apps/{app_folder_name}/"
        final_repo_url = repo.html_url

        payload = {
            "email": email, "task": task, "round": round_num, "nonce": nonce,
            "repo_url": final_repo_url, "commit_sha": commit_sha, "pages_url": pages_url
        }
        success = post_with_retry(evaluation_url, payload)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to POST to evaluation URL.")

        return {"message": "Success", "repo_url": final_repo_url, "pages_url": pages_url}

    except Exception as e:
        traceback.print_exc()
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")

