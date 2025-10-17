import os
import tempfile
import shutil
import subprocess
import requests
    from fastapi import FastAPI, Request, HTTPException
from github import Github
    from dotenv import load_dotenv
import base64
import time

load_dotenv()

app = FastAPI()

#Allowed student email + secret
ALLOWED = { "student@example.com": os.getenv("ALLOWED_SECRET_FOR_TESTING") }

# Helper function to write attachments to temp folder
def handle_attachments(tmpdir, attachments):
for attach in attachments or[]:
path = os.path.join(tmpdir, attach["name"])
data = attach["url"].split(",")[1]  # skip data: image /...; base64,
        with open(path, "wb") as f:
f.write(base64.b64decode(data))

# Helper function to generate README.md
def generate_readme(task, brief):
return f"""# {task}

## Summary
{ brief }

## Setup
1. Clone the repo
2. Open index.html in a browser or deploy via GitHub Pages

## Usage
Open the page and interact with features according to the brief

## License
MIT License
"""

# Helper function to generate index.html
def generate_index_html(task, brief, attachments):
html = f"""
    < !DOCTYPE html >
        <html lang="en">
            <head>
                <meta charset="UTF-8">
                    <title>{task}</title>
                    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css">
                    </head>
                    <body class="p-4">
                        <div class="container">
                            <h1>{task}</h1>
                            <p>{brief}</p>
                            """
                            for attach in attachments or []:
                            if attach["name"].endswith((".png", ".jpg", ".jpeg", ".gif")):
                            html += f'<img src="{attach[" name"]}" class="img-fluid mb-3"/>\n'
                            elif attach["name"].endswith((".csv", ".json")):
                            html += f'<p>Attachment available: {attach["name"]}</p>\n'
                            elif attach["name"].endswith(".md"):
                            html += f'<div id="markdown-output"></div>\n'
                            html += f'<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>\n'
                            html += f'<script>\n'
                                html += f'fetch("{attach["name"]}").then(r => r.text()).then(md => {{ document.getElementById("markdown-output").innerHTML = marked.parse(md); }});\n'
                                html += f'</script>\n'

                            html += """
                        </div>
                    </body>
                </html>
                """
                return html

                @app.post("/api-endpoint")
                async def handle_request(request: Request):
                data = await request.json()
                email = data.get("email")
                secret = data.get("secret")
                brief = data.get("brief")
                task = data.get("task")
                evaluation_url = data.get("evaluation_url")
                nonce = data.get("nonce")
                attachments = data.get("attachments")
                round_num = data.get("round", 1)

                # Verify secret
                if ALLOWED.get(email) != secret:
                raise HTTPException(status_code=403, detail="Secret mismatch")

                tmpdir = tempfile.mkdtemp()
                try:
                # Write attachments
                handle_attachments(tmpdir, attachments)

                # Create basic files
                with open(os.path.join(tmpdir, "index.html"), "w") as f:
                f.write(generate_index_html(task, brief, attachments))
                with open(os.path.join(tmpdir, "README.md"), "w") as f:
                f.write(generate_readme(task, brief))
                with open(os.path.join(tmpdir, "LICENSE"), "w") as f:
                f.write("MIT License\n\n(c) 2025")

                # GitHub setup
                token = os.getenv("GITHUB_TOKEN")
                gh = Github(token)
                user = gh.get_user()
                repo_name = f"{task}-{nonce}".replace(' ', '-').lower()

                # Round 2: check if repo exists
                try:
                repo = gh.get_repo(f"{user.login}/{repo_name}")
                except:
                if round_num == 1:
                repo = user.create_repo(repo_name, private=False)
                else:
                raise HTTPException(status_code=400, detail="Repo does not exist for round 2")

                # Git commands
                subprocess.run(["git", "init"], cwd=tmpdir)
                subprocess.run(["git", "add", "."], cwd=tmpdir)
                subprocess.run(["git", "commit", "-m", f"update round {round_num}"], cwd=tmpdir)
                subprocess.run(["git", "branch", "-M", "main"], cwd=tmpdir)
                subprocess.run(
                ["git", "remote", "add", "origin", f"https://{token}@github.com/{user.login}/{repo_name}.git"],
                cwd=tmpdir
                )
                subprocess.run(["git", "push", "-u", "origin", "main", "--force"], cwd=tmpdir)

                pages_url = f"https://{user.login}.github.io/{repo_name}/"

                # Notify evaluation URL with retry
                payload = {
                    "email": email,
                "task": task,
                "round": round_num,
                "nonce": nonce,
                "repo_url": repo.html_url,
                "commit_sha": repo.get_commits()[0].sha,
                "pages_url": pages_url
        }

                delay = 1
                for _ in range(5):
                try:
                resp = requests.post(evaluation_url, json=payload, timeout=10)
                if resp.status_code == 200:
                break
                except:
                pass
                time.sleep(delay)
                delay *= 2

                return {"message": f"Round {round_num} app deployed", "repo_url": repo.html_url, "pages_url": pages_url}

                finally:
                # Safe cleanup even on Windows
                for root, dirs, files in os.walk(tmpdir, topdown=False):
                for name in files:
                try:
                os.chmod(os.path.join(root, name), 0o777)
                except:
                pass
                for name in dirs:
                try:
                os.chmod(os.path.join(root, name), 0o777)
                except:
                pass
                shutil.rmtree(tmpdir, ignore_errors=True)