# server.py (Final Multi-Repo Version with all fixes)
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
    # Using the OpenRouter model name from your course docs
    MODEL_NAME = "google/gemini-2.0-flash-lite-001"
except Exception as e:
    print(f"Error configuring AI Pipe client: {e}")
    client = None

ALLOWED = {"student@example.com": os.getenv("ALLOWED_SECRET_FOR_TESTING")}
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

# --- HELPER FUNCTIONS ---

def generate_readme_content(task, brief):
    """Generates the content for the README.md file."""
    return f"""# LLM Code Deployment Project: {task}

This project was automatically generated and deployed in response to the following brief:

> *"{brief}"*

It is a fully automated application that receives a development brief via an API, uses an AI model to generate code, and then automatically deploys it to a new GitHub repository and enables GitHub Pages.
"""

def generate_license_content(github_user_login):
    """Generates the content for the MIT LICENSE file."""
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
    """Generates or modifies code using the AI Pipe."""
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
    """Posts data with exponential backoff retry logic."""
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
    # Use a temporary directory that is cleaned up automatically
    with tempfile.TemporaryDirectory() as tmpdir:
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
            
            if round_num == 1:
                repo_name = f"{task}-{nonce}".replace(" ", "-").lower()
                full_repo_name = f"{user.login}/{repo_name}"
                
                try:
                    gh.get_repo(full_repo_name)
                    raise HTTPException(status_code=409, detail=f"Repository '{full_repo_name}' already exists.")
                except GithubException as e:
                    if e.status != 404: raise e
                    pass # 404 is good, we can proceed

                html_content = generate_code_with_llm(brief, round_num)
                
                readme_content = generate_readme_content(task, brief)
                license_content = generate_license_content(user.login)

                with open(os.path.join(tmpdir, "index.html"), "w", encoding="utf-8") as f: f.write(html_content)
                with open(os.path.join(tmpdir, "README.md"), "w", encoding="utf-8") as f: f.write(readme_content)
                with open(os.path.join(tmpdir, "LICENSE"), "w", encoding="utf-8") as f: f.write(license_content)
                
                print(f"Creating new repo: {full_repo_name}")
                repo = user.create_repo(repo_name, private=False)
                
                subprocess.run(["git", "init"], cwd=tmpdir, check=True)
                subprocess.run(["git", "add", "."], cwd=tmpdir, check=True)
                subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=tmpdir, check=True)
                subprocess.run(["git", "branch", "-M", "main"], cwd=tmpdir, check=True)
                remote_url = f"https://{GITHUB_TOKEN}@github.com/{full_repo_name}.git"
                subprocess.run(["git", "remote", "add", "origin", remote_url], cwd=tmpdir, check=True)
                subprocess.run(["git", "push", "-u", "origin", "main"], cwd=tmpdir, check=True)

                # FINAL FIX: Use a direct API call with `requests` to enable GitHub Pages.
                # This is the most reliable method and avoids PyGithub version issues.
                try:
                    print("Enabling GitHub Pages via direct API call...")
                    pages_api_url = f"https://api.github.com/repos/{full_repo_name}/pages"
                    headers = {
                        "Authorization": f"token {GITHUB_TOKEN}",
                        "Accept": "application/vnd.github.v3+json"
                    }
                    source_payload = {
                        "source": {"branch": "main", "path": "/"}
                    }
                    response = requests.post(pages_api_url, headers=headers, json=source_payload)

                    if response.status_code == 201: # 201 Created is success
                        print("GitHub Pages enabled successfully.")
                    elif response.status_code == 409: # 409 Conflict means already enabled
                        print("GitHub Pages was already enabled.")
                    else:
                        print(f"Could not enable GitHub Pages. Status: {response.status_code}, Response: {response.json()}")
                    
                    time.sleep(5) # Give GitHub a moment to process

                except Exception as e:
                    print(f"An unexpected error occurred while enabling GitHub Pages: {e}")
                
                commit_sha = repo.get_branch("main").commit.sha
                final_repo_url = repo.html_url
                pages_url = f"https://{user.login}.github.io/{repo_name}/"
            
            else: # Round 2
                repo_url_from_request = data.get("repo_url")
                if not repo_url_from_request:
                    raise HTTPException(status_code=400, detail="repo_url is required for round 2")
                
                print(f"Cloning existing repo: {repo_url_from_request}")
                remote_url = repo_url_from_request.replace("https://", f"https://{GITHUB_TOKEN}@")
                subprocess.run(["git", "clone", remote_url, tmpdir], check=True)
                
                try:
                    with open(os.path.join(tmpdir, "index.html"), "r", encoding="utf-8") as f: existing_html = f.read()
                except FileNotFoundError: existing_html = ""

                new_html_content = generate_code_with_llm(brief, round_num, existing_code=existing_html)
                
                with open(os.path.join(tmpdir, "index.html"), "w", encoding="utf-8") as f: f.write(new_html_content)
                with open(os.path.join(tmpdir, "README.md"), "a", encoding="utf-8") as f: f.write(f"\n\n---\n\n### Round 2 Update\n\n> *\"{brief}\"*")

                subprocess.run(["git", "add", "."], cwd=tmpdir, check=True)
                subprocess.run(["git", "commit", "-m", f"Update for round {round_num}"], cwd=tmpdir, check=True)
                subprocess.run(["git", "push"], cwd=tmpdir, check=True)
                
                full_repo_name = "/".join(repo_url_from_request.split("/")[-2:])
                repo = gh.get_repo(full_repo_name)
                commit_sha = repo.get_branch("main").commit.sha
                final_repo_url = repo.html_url
                repo_name_only = repo_url_from_request.split("/")[-1]
                pages_url = f"https://{user.login}.github.io/{repo_name_only}/"

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

