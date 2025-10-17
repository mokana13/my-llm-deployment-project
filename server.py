import os
import traceback
import tempfile
import subprocess
import base64
import time
import requests
import hashlib

from fastapi import FastAPI, Request, HTTPException
from github import Github, GithubException
from dotenv import load_dotenv
from openai import OpenAI

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

def handle_attachments(tmpdir, attachments):
    """Save attachments to the temporary directory."""
    attachment_files = []
    for attach in attachments or []:
        try:
            path = os.path.join(tmpdir, attach["name"])
            data_uri = attach["url"]
            if "base64," in data_uri:
                data = data_uri.split("base64,")[1]
                with open(path, "wb") as f:
                    f.write(base64.b64decode(data))
                attachment_files.append(attach["name"])
        except Exception as e:
            print(f"Error handling attachment {attach.get('name')}: {e}")
    return attachment_files

def generate_readme_content(task, brief, checks=None, attachment_files=None):
    """Generates comprehensive README.md content."""
    readme = f"""# {task}

## Summary
This project was automatically generated to fulfill the following requirement:

{brief}

## Setup
1. Clone this repository:
   ```bash
   git clone https://github.com/<username>/{task}.git
   cd {task}
   ```
2. Open `index.html` in a web browser, or deploy via GitHub Pages

## Usage
- Open the deployed GitHub Pages URL or open `index.html` locally
- The application will automatically load and execute according to the brief requirements
"""

    if attachment_files:
        readme += f"\n## Included Files\n"
        for fname in attachment_files:
            readme += f"- `{fname}`\n"

    if checks:
        readme += f"\n## Evaluation Criteria\nThis application is evaluated against the following checks:\n"
        for check in checks:
            readme += f"- {check}\n"

    readme += f"""
## Code Explanation
The application is built as a single-page HTML file (`index.html`) that includes:
- **HTML Structure**: Semantic markup with proper accessibility attributes
- **CSS Styling**: Utilizes Bootstrap 5 for responsive design
- **JavaScript Logic**: Handles the core functionality as specified in the brief
- All dependencies are loaded from CDNs for easy deployment

The code was generated using AI assistance based on the project brief and automatically deployed to GitHub.

## License
MIT License - See LICENSE file for details
"""
    return readme

def generate_license_content(github_user_login):
    """Generates MIT LICENSE content."""
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

def generate_code_with_llm(brief, attachments, round_num, existing_code=None):
    """Generates or modifies code using the AI Pipe."""
    if not client:
        raise HTTPException(status_code=500, detail="AI Pipe client not configured.")
    
    # Build context about attachments
    attachment_context = ""
    if attachments:
        attachment_context = "\n\nAvailable files:\n"
        for attach in attachments:
            attachment_context += f"- {attach['name']}\n"
    
    if round_num == 1:
        system_prompt = """You are an expert web developer. Create a complete, production-ready single HTML file.

Requirements:
- All HTML, CSS, and JavaScript in ONE file
- Use Bootstrap 5 from CDN for styling
- Include proper error handling
- Make it functional and user-friendly
- Use semantic HTML with accessibility attributes
- Add comments explaining key functionality
- Respond ONLY with raw HTML code (no markdown, no explanations)"""
        
        user_prompt = f'BRIEF: {brief}{attachment_context}\n\nCreate a complete HTML file that fulfills this brief.'
    else:
        system_prompt = """You are an expert web developer. Update the existing HTML file based on new requirements.

Requirements:
- Preserve existing functionality
- Add the new features seamlessly
- Maintain code quality and style
- Keep all code in the single HTML file
- Respond ONLY with the complete updated HTML code (no markdown, no explanations)"""
        
        user_prompt = f'BRIEF: {brief}{attachment_context}\n\nEXISTING CODE:\n{existing_code}\n\nUpdate this code to meet the new requirements.'
    
    try:
        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        )
        clean_code = completion.choices[0].message.content.strip()
        # Remove markdown code blocks if present
        clean_code = clean_code.replace("```html", "").replace("```", "").strip()
        return clean_code
    except Exception as e:
        print(f"AI Pipe call failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate code: {str(e)}")

def verify_pages_active(pages_url, max_attempts=30, delay=10):
    """Verify that GitHub Pages is active and returning 200 OK."""
    print(f"Verifying Pages URL: {pages_url}")
    for attempt in range(max_attempts):
        try:
            response = requests.get(pages_url, timeout=10)
            if response.status_code == 200:
                print(f"✓ Pages active after {attempt + 1} attempts")
                return True
        except requests.RequestException as e:
            print(f"Attempt {attempt + 1}: Pages not ready yet ({e})")
        time.sleep(delay)
    return False

def post_with_retry(url, payload, max_attempts=5):
    """Posts data with exponential backoff retry logic."""
    delay = 1
    for attempt in range(max_attempts):
        try:
            r = requests.post(url, json=payload, timeout=10)
            if r.status_code == 200:
                print(f"✓ Successfully posted to evaluation URL (attempt {attempt + 1})")
                return True
            else:
                print(f"Evaluation URL returned {r.status_code}: {r.text}")
        except requests.RequestException as e:
            print(f"Attempt {attempt + 1} failed: {e}")
        
        if attempt < max_attempts - 1:
            time.sleep(delay)
            delay *= 2
    return False

@app.post("/api-endpoint")
async def handle_request(request: Request):
    start_time = time.time()
    data = await request.json()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            # Extract and verify credentials
            email = data.get("email")
            secret = data.get("secret")
            if ALLOWED.get(email) != secret:
                raise HTTPException(status_code=403, detail="Secret mismatch")
            
            # Extract request data
            brief = data.get("brief")
            task = data.get("task")
            evaluation_url = data.get("evaluation_url")
            nonce = data.get("nonce")
            round_num = data.get("round", 1)
            attachments = data.get("attachments", [])
            checks = data.get("checks", [])
            
            gh = Github(GITHUB_TOKEN)
            user = gh.get_user()
            
            if round_num == 1:
                # Round 1: Create new repository
                repo_name = f"{task}-{nonce}".replace(" ", "-").lower()
                full_repo_name = f"{user.login}/{repo_name}"
                
                # Check if repo already exists
                try:
                    gh.get_repo(full_repo_name)
                    raise HTTPException(status_code=409, detail=f"Repository '{full_repo_name}' already exists")
                except GithubException as e:
                    if e.status != 404:
                        raise e
                
                # Handle attachments
                attachment_files = handle_attachments(tmpdir, attachments)
                
                # Generate code
                html_content = generate_code_with_llm(brief, attachments, round_num)
                
                # Generate files
                readme_content = generate_readme_content(task, brief, checks, attachment_files)
                license_content = generate_license_content(user.login)
                
                # Write files
                with open(os.path.join(tmpdir, "index.html"), "w", encoding="utf-8") as f:
                    f.write(html_content)
                with open(os.path.join(tmpdir, "README.md"), "w", encoding="utf-8") as f:
                    f.write(readme_content)
                with open(os.path.join(tmpdir, "LICENSE"), "w", encoding="utf-8") as f:
                    f.write(license_content)
                
                # Create repository
                print(f"Creating repository: {full_repo_name}")
                repo = user.create_repo(repo_name, private=False)
                
                # Git operations
                subprocess.run(["git", "init"], cwd=tmpdir, check=True, capture_output=True)
                subprocess.run(["git", "config", "user.email", "bot@example.com"], cwd=tmpdir, check=True, capture_output=True)
                subprocess.run(["git", "config", "user.name", "LLM Deployment Bot"], cwd=tmpdir, check=True, capture_output=True)
                subprocess.run(["git", "add", "."], cwd=tmpdir, check=True, capture_output=True)
                subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=tmpdir, check=True, capture_output=True)
                subprocess.run(["git", "branch", "-M", "main"], cwd=tmpdir, check=True, capture_output=True)
                
                remote_url = f"https://{GITHUB_TOKEN}@github.com/{full_repo_name}.git"
                subprocess.run(["git", "remote", "add", "origin", remote_url], cwd=tmpdir, check=True, capture_output=True)
                subprocess.run(["git", "push", "-u", "origin", "main"], cwd=tmpdir, check=True, capture_output=True)
                
                # Enable GitHub Pages
                print("Enabling GitHub Pages...")
                pages_api_url = f"https://api.github.com/repos/{full_repo_name}/pages"
                headers = {
                    "Authorization": f"token {GITHUB_TOKEN}",
                    "Accept": "application/vnd.github.v3+json"
                }
                pages_response = requests.post(
                    pages_api_url,
                    headers=headers,
                    json={"source": {"branch": "main", "path": "/"}}
                )
                
                if pages_response.status_code in [201, 409]:
                    print("✓ GitHub Pages enabled")
                else:
                    print(f"⚠ Pages enablement status: {pages_response.status_code}")
                
                commit_sha = repo.get_branch("main").commit.sha
                final_repo_url = repo.html_url
                pages_url = f"https://{user.login}.github.io/{repo_name}/"
                
                # Verify Pages is active (with timeout consideration)
                elapsed = time.time() - start_time
                if elapsed < 540:  # Leave 60 seconds for evaluation post
                    verify_pages_active(pages_url, max_attempts=20, delay=5)
                
            else:
                # Round 2: Update existing repository
                prev_repo_url = data.get("repo_url")
                if not prev_repo_url:
                    raise HTTPException(status_code=400, detail="repo_url required for round 2")
                
                # Extract repo name from URL
                repo_name = prev_repo_url.rstrip('/').split('/')[-1]
                full_repo_name = f"{user.login}/{repo_name}"
                
                # Verify repo exists
                try:
                    repo = gh.get_repo(full_repo_name)
                except GithubException:
                    raise HTTPException(status_code=404, detail=f"Repository {full_repo_name} not found")
                
                # Clone existing repo
                print(f"Cloning repository: {full_repo_name}")
                clone_url = f"https://{GITHUB_TOKEN}@github.com/{full_repo_name}.git"
                subprocess.run(["git", "clone", clone_url, tmpdir], check=True, capture_output=True)
                
                # Handle new attachments
                attachment_files = handle_attachments(tmpdir, attachments)
                
                # Read existing code
                try:
                    with open(os.path.join(tmpdir, "index.html"), "r", encoding="utf-8") as f:
                        existing_html = f.read()
                except FileNotFoundError:
                    existing_html = ""
                
                # Generate updated code
                new_html_content = generate_code_with_llm(brief, attachments, round_num, existing_code=existing_html)
                
                # Update files
                with open(os.path.join(tmpdir, "index.html"), "w", encoding="utf-8") as f:
                    f.write(new_html_content)
                
                # Append to README
                with open(os.path.join(tmpdir, "README.md"), "a", encoding="utf-8") as f:
                    f.write(f"\n\n---\n\n## Round {round_num} Update\n\n**Brief**: {brief}\n\n")
                    if checks:
                        f.write("**New Evaluation Criteria**:\n")
                        for check in checks:
                            f.write(f"- {check}\n")
                
                # Git operations
                subprocess.run(["git", "config", "user.email", "bot@example.com"], cwd=tmpdir, check=True, capture_output=True)
                subprocess.run(["git", "config", "user.name", "LLM Deployment Bot"], cwd=tmpdir, check=True, capture_output=True)
                subprocess.run(["git", "add", "."], cwd=tmpdir, check=True, capture_output=True)
                subprocess.run(["git", "commit", "-m", f"Round {round_num} update"], cwd=tmpdir, check=True, capture_output=True)
                subprocess.run(["git", "push"], cwd=tmpdir, check=True, capture_output=True)
                
                commit_sha = repo.get_branch("main").commit.sha
                final_repo_url = repo.html_url
                pages_url = f"https://{user.login}.github.io/{repo_name}/"
            
            # Check 10-minute constraint
            elapsed = time.time() - start_time
            if elapsed > 600:
                print(f"⚠ Warning: Processing took {elapsed:.0f}s (>10 minutes)")
            
            # Notify evaluation URL
            payload = {
                "email": email,
                "task": task,
                "round": round_num,
                "nonce": nonce,
                "repo_url": final_repo_url,
                "commit_sha": commit_sha,
                "pages_url": pages_url
            }
            
            success = post_with_retry(evaluation_url, payload)
            if not success:
                raise HTTPException(status_code=500, detail="Failed to notify evaluation URL")
            
            return {
                "message": "Success",
                "repo_url": final_repo_url,
                "pages_url": pages_url,
                "commit_sha": commit_sha,
                "elapsed_seconds": int(time.time() - start_time)
            }
        
        except Exception as e:
            traceback.print_exc()
            if isinstance(e, HTTPException):
                raise e
            raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")

@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring."""
    return {"status": "healthy", "timestamp": time.time()}