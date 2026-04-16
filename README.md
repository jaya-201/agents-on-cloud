# 🤖 AI Agents on Cloud
###  Multi-Agent Orchestrator deployed on AWS Lambda

> A serverless multi-agent system where a **Manager**, **Writer**, and **Reviewer** agent collaborate to produce high-quality AI-generated content — powered by Google Gemini and deployed on AWS Lambda.

---

## 👥 Team Members

| Roll No | Name |
|---------|------|
| U23AI016 | Kavisha Vaja |
| U23AI026 | Aarchi Solanki |
| U23AI036 | Driti Rathod |
| U23AI043 | Jaya Bhati |

---

## 📌 Problem Statement

Standard LLM apps are linear: **Question → Answer**.

This project builds a **Multi-Agent Orchestrator** that solves complex, multi-step problems where one LLM isn't enough. The system can:

- **Decompose** — Break a vague prompt into a structured plan
- **Collaborate** — Pass information between specialized agents
- **Loop** — If the Reviewer finds issues, the system loops back to the Writer without losing context
- **Scale** — All of this runs on the cloud without a persistent server

---

## 🏗️ Architecture

```
User Request
     │
     ▼
┌─────────────┐
│   MANAGER   │  ← Decides phase: draft / review / revise / finish
│   (Router)  │
└──────┬──────┘
       │
   ┌───┴────────────────┐
   │                    │
   ▼                    ▼
┌────────┐        ┌──────────┐
│ WRITER │◄───────│ REVIEWER │
│        │──draft─►  Score   │
└────────┘        │  ≥7?     │
                  └────┬─────┘
                       │
              ┌────────┴────────┐
           Approve           Reject
              │                 │
              ▼                 ▼
           FINISH          Back to WRITER
                           (with feedback)
```

### Agents
| Agent | Role |
|-------|------|
| **Manager** | Routes the workflow — decides draft / review / revise / finish |
| **Writer** | Generates and revises content based on instructions |
| **Reviewer** | Scores content (1–10), approves if score ≥ 7, else rejects with feedback |

---

## 📁 Project Structure

```
agents-on-cloud/
├── agent/
│   ├── agent.py          # Core multi-agent orchestration loop
│   ├── prompts.py        # System prompts for all three agents
│   └── tools.py          # Utility functions (JSON parsing, validation)
├── lambda_handler.py     # AWS Lambda entry point
├── requirements.txt      # Python dependencies
└── README.md
```

---

## ☁️ Cloud Deployment

### Why Serverless?
- **No idle cost** — AWS Lambda charges only per invocation
- **Auto-scales** — handles any number of requests automatically
- **No server management** — AWS handles everything

### Tech Stack
| Component | Technology |
|-----------|------------|
| Cloud Platform | AWS Lambda |
| AI Model | Google Gemini 1.5 Flash |
| Language | Python 3.12 |
| Trigger | AWS API Gateway / Function URL |

---

## 🚀 How to Run Locally

### 1. Clone the repo
```bash
git clone https://github.com/jaya-201/agents-on-cloud.git
cd agents-on-cloud
```

### 2. Install dependencies
```bash
pip install google-generativeai
```

### 3. Set your Gemini API key
```bash
# Windows
set GEMINI_API_KEY=your-api-key-here

# Mac/Linux
export GEMINI_API_KEY=your-api-key-here
```

### 4. Test locally
```bash
python -c "
from lambda_handler import handler
import json
r = handler({'body': json.dumps({'prompt': 'Write a blog post about AI'})}, type('C', (), {'aws_request_id': 'test'})())
print(json.loads(r['body'])['final_content'][:500])
"
```

---

## 🌐 API Usage

### Endpoint
```
POST https://your-lambda-url.on.aws/
```

### Request
```json
{
  "prompt": "Write a technical blog post about Graph Neural Networks"
}
```

### Response
```json
{
  "final_content": "# Graph Neural Networks\n\n...",
  "approved": true,
  "iterations": 2,
  "review_summary": {
    "verdict": "approve",
    "score": 8,
    "strengths": ["Clear explanations", "Good examples"],
    "issues": [],
    "feedback": ""
  }
}
```

---

## 🔄 How the Loop Works

| Step | Agent | Action |
|------|-------|--------|
| 1 | Manager | Reads request → decides phase = `draft` |
| 2 | Writer | Generates initial content |
| 3 | Manager | Sees draft → decides phase = `review` |
| 4 | Reviewer | Scores draft (1–10) |
| 5a | Score ≥ 7 | Manager finishes → returns result ✅ |
| 5b | Score < 7 | Manager decides `revise` → Writer gets feedback |
| 6 | Writer | Addresses every issue → new draft |
| 7 | Repeat | Until approved or max 5 iterations |

---

## 📦 Deployment to AWS

```bash
# Install Linux-compatible packages
pip install google-generativeai -t package --platform manylinux2014_x86_64 --only-binary=:all: --python-version 3.12

# Copy code files
xcopy agent package\agent\ /E /I /Y
copy lambda_handler.py package\

# Create zip
cd package
powershell Compress-Archive -Path * -DestinationPath ..\deployment.zip -Force
cd ..
```

Then upload `deployment.zip` to AWS Lambda and set `GEMINI_API_KEY` in environment variables.

---

## 📄 License
This project was built as a college assignment for the AI Agents on Cloud topic.
