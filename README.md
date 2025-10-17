# 🚀 LLM-Powered Automated Code Deployment

This project is a fully automated application that receives a development brief via an API, uses an AI model to generate code, and then automatically creates a GitHub repository, deploys the code, and enables GitHub Pages.

---

## ✨ Features

-   **API-Driven:** Receives project briefs via a simple JSON POST request.
-   **AI Code Generation:** Uses an LLM to generate complete, single-page web applications from a natural language brief.
-   **Automated GitHub Workflow:**
    -   Creates a new public repository on GitHub.
    -   Generates a professional `README.md` and `LICENSE` file.
    -   Commits and pushes all generated files.
    -   Enables GitHub Pages for instant deployment.
-   **Multi-Round Support:** Handles initial creation (Round 1) and subsequent updates/revisions (Round 2).
-   **Asynchronous Processing:** Uses background tasks to handle long-running processes like code generation and deployment, ensuring the API responds instantly.
-   **Reliable Notifications:** Reports success or failure to a specified evaluation URL with an exponential backoff retry mechanism.

---

## ⚙️ Technology Stack

-   **Backend:** Python 3
-   **Framework:** FastAPI
-   **GitHub Integration:** PyGithub
-   **LLM Integration:** OpenAI Client (compatible with services like AI Pipe)
-   **Server:** Uvicorn
-   **Deployment:** Configured for platforms like Render.

---

## 🛠️ Setup and Installation

Follow these steps to get the project running locally.

### 1. Clone the Repository

```bash
git clone <your-repository-url>
cd <repository-directory>
```

### 2. Create a Virtual Environment

It's recommended to use a virtual environment to manage dependencies.

```bash
python -m venv venv
source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
```

### 3. Install Dependencies

The project requires Python packages listed in `requirements.txt` and the `git` command-line tool.

```bash
pip install -r requirements.txt
```

For deployment on services like Render, a system dependency file (`apt.txt`) is included to ensure `git` is installed.

### 4. Configure Environment Variables

Create a file named `.env` in the root of the project and add the following variables. **Do not commit this file to version control.**

```env
# Your GitHub Personal Access Token (with 'repo' scope)
GITHUB_TOKEN="ghp_YourGitHubTokenHere"

# Your email and a secret for API authentication
ALLOWED_SECRET_FOR_TESTING="your-super-key"

# Credentials for the LLM service (e.g., AI Pipe)
AI_PIPE_TOKEN="your_ai_pipe_token"
AI_PIPE_URL="[https://aipipe.org/openrouter/v1](https://aipipe.org/openrouter/v1)"
```

---

## ▶️ Running the Application

To run the server locally, use the following command from the project's root directory:

```bash
uvicorn server:app --reload
```

The server will be available at `http://127.0.0.1:8000`.

---

## 📡 API Usage

Send a `POST` request to the `/api-endpoint`.

### Round 1: Create a New Application

**Request Body:**

```json
{
  "email": "student@example.com",
  "secret": "your-super-key",
  "task": "my-cool-app",
  "round": 1,
  "nonce": "unique-nonce-123",
  "brief": "Create a simple hello world page with Bootstrap styling.",
  "evaluation_url": "[https://webhook.site/your-unique-id](https://webhook.site/your-unique-id)",
  "attachments": []
}
```

### Round 2: Update an Existing Application

**Request Body:**

```json
{
  "email": "student@example.com",
  "secret": "your-secret-key",
  "task": "my-cool-app",
  "round": 2,
  "nonce": "unique-nonce-123",
  "repo_url": "[https://github.com/your-username/my-cool-app-unique-nonce-123](https://github.com/your-username/my-cool-app-unique-nonce-123)",
  "brief": "Add a blue button that says 'Click Me!'",
  "evaluation_url": "[https://webhook.site/your-unique-id](https://webhook.site/your-unique-id)"
}
```
