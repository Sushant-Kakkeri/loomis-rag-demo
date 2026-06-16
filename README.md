# Loomis Armored US — Policy AI Assistant
### On-Premise RAG Pipeline | LangChain + ChromaDB + LangSmith

A production-grade AI assistant that answers employee questions from internal policy documents. Built specifically to demonstrate on-premise AI architecture for regulated enterprises — no data leaves the network.

---

## What It Does

Employees ask questions in plain English. The system searches internal policy documents, retrieves the most relevant sections, and generates a grounded answer with the exact source cited. Every answer goes through a safety gate before reaching the employee.

```
Employee: "Can I access the vault alone on weekends?"
     ↓
System searches vault_policy.txt using semantic similarity
     ↓
Retrieves: "Vault access requires two authorized personnel at all times. No exceptions."
     ↓
Generates grounded answer with source citation
     ↓
Safety gate checks for unsafe phrases before returning
     ↓
Employee sees: answer + source document + page number
```

---

## Architecture

```
Web UI (Streamlit)
        ↓
FastAPI / LangChain Chain
        ↓
sentence-transformers (CPU)    ← embeds queries locally, no API call
        ↓
ChromaDB (on-prem)             ← semantic search over policy chunks
        ↓
Llama 3.1 via Ollama           ← on-prem LLM (swap for OpenAI in dev)
        ↓
Safety Gate + Audit Log
```

**On-prem swap:** Change one environment variable to switch between OpenAI (development) and Ollama/vLLM (production). Same code, same pipeline.

---

## Tech Stack

| Component | Tool | Why |
|---|---|---|
| LLM (cloud/dev) | OpenAI GPT-4o-mini | Fast, cheap for development |
| LLM (on-prem/prod) | Llama 3.1 8B via Ollama | Zero data leaves network |
| Embeddings | sentence-transformers all-MiniLM-L6-v2 | Runs on CPU, fully local |
| Vector store | ChromaDB | On-prem, open source, persistent |
| Orchestration | LangChain LCEL | Composable chains, streaming |
| Observability | LangSmith | Tracing, eval datasets, dashboards |
| UI | Streamlit | Fast to build, clean interface |
| Safety | Custom safety gate | Blocks unsafe answers before delivery |

---

## Project Structure

```
loomis-rag/
├── .env                    # API keys and config (never commit this)
├── .env.template           # Template — copy to .env and fill in
├── requirements.txt        # Python dependencies
│
├── ingest.py              # Load → chunk → embed → store in ChromaDB
├── retriever.py           # ChromaDB semantic search
├── chain.py               # LangChain RAG chain + safety gate
├── app.py                 # Streamlit UI
│
└── policies/              # Policy documents (PDF or TXT)
    ├── vault_policy.txt
    ├── hr_handbook.txt
    └── route_safety.txt
```

---

## Setup

### 1. Prerequisites

```bash
Python 3.11 recommended (3.14 has Pydantic compatibility warnings)
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
pip install langchain-text-splitters
pip install -U langchain-huggingface
```

### 3. Configure environment

```bash
# Copy the template
cp .env.template .env

# Edit .env and fill in your values
```

Your `.env` file:

```bash
# LangSmith — set to false if you don't have an account
LANGCHAIN_TRACING_V2=false
LANGCHAIN_API_KEY=your_langsmith_key_here
LANGCHAIN_PROJECT=loomis-rag-demo

# OpenAI — for development
OPENAI_API_KEY=sk-proj-your-key-here

# Model config
# Development (cloud):
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini

# Production on-prem (swap these two lines):
# LLM_BASE_URL=http://localhost:11434/v1
# LLM_MODEL=llama3.1:8b

# Paths
EMBEDDING_MODEL=all-MiniLM-L6-v2
CHROMA_PATH=./loomis_vectordb
DOCS_PATH=./policies
```

### 4. Add your policy documents

Place `.txt` or `.pdf` files in the `policies/` folder. Name them so the category is detectable:

```
vault_policy.txt     → tagged as vault_access
hr_handbook.txt      → tagged as hr_policy
route_safety.txt     → tagged as route_operations
anything_else.txt    → tagged as general
```

### 5. Index your documents

```bash
python ingest.py
```

Output:
```
Loaded: vault_policy.txt (vault_access)
Loaded: hr_handbook.txt (hr_policy)
Loaded: route_safety.txt (route_operations)
Chunked into 24 chunks
Vector store built: 24 chunks indexed
```

Only run this once — or when documents change. Smart re-indexing skips unchanged files.

### 6. Test retrieval

```bash
python retriever.py
```

Verify the right chunks come back for test queries before running the full chain.

### 7. Test the chain

```bash
python chain.py
```

Runs 4 test questions and shows answers, sources, and safety gate results.

### 8. Launch the UI

```bash
streamlit run app.py
```

Opens at `http://localhost:8501`

---

## Switching to On-Prem (Ollama)

Install Ollama: https://ollama.com

```bash
# Pull the model
ollama pull llama3.1:8b

# Start Ollama (runs on port 11434 by default)
ollama serve
```

Then in `.env` change two lines:

```bash
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL=llama3.1:8b
```

Restart the app. Same code, same pipeline, zero data leaves your machine.

---

## How It Works — The 7-Step Pipeline

```
Step 1  LOAD        pypdf reads policy PDFs from the policies/ folder

Step 2  CHUNK       RecursiveCharacterTextSplitter splits into 1,000
                    character chunks with 150 character overlap
                    Sentence-aware — never cuts mid-rule

Step 3  EMBED       sentence-transformers all-MiniLM-L6-v2 converts
                    each chunk to a 384-dimensional vector
                    Runs on CPU — no GPU needed

Step 4  STORE       ChromaDB stores text + vector + metadata
                    Metadata: source, category, section, page, chunk_idx

Step 5  QUERY       Employee question embedded with same model
                    CRITICAL: must use identical model as Step 3

Step 6  RETRIEVE    ChromaDB finds top 5 chunks by cosine similarity
                    Filters chunks below 0.3 similarity threshold

Step 7  GENERATE    LangChain chain: prompt | llm | parser
                    System prompt enforces grounding rules
                    Safety gate checks answer before returning
```

---

## Safety Features

Every answer passes through a safety gate before reaching the employee:

```python
UNSAFE_PHRASES = [
    "alone", "by yourself", "single person",
    "skip form", "form is optional",
    "exceptions apply", "senior staff may"
]
```

If any unsafe phrase is detected — the answer is blocked and the employee is told to contact their supervisor.

Source quote verification: any quoted text in the answer is checked against the retrieved context. Hallucinated quotes are caught before delivery.

---

## Evaluation

Before going live, build a golden test suite:

```python
eval_cases = [
    {
        "question": "How many people are required for vault access?",
        "must_contain": ["two", "2"],
        "must_not_contain": ["alone", "one person"],
        "criticality": "safety"   # must pass 100%
    },
    {
        "question": "How many vacation days do employees get?",
        "must_contain": ["10"],
        "criticality": "operational"   # target 94%
    }
]
```

Safety cases: **100% threshold** — non-negotiable.
Overall accuracy: **94% target**, **90% hard floor**.

---

## Demo Script (60 seconds)

Open the Streamlit app. Ask these questions in order:

```
1. "How many people are required for vault access?"
   → Shows: vault policy retrieved, exact rule quoted, safety passed ✅

2. "How many vacation days do I get per year?"
   → Shows: HR handbook retrieved, correct answer, different source ✅

3. "Can I access the vault alone on weekends?"
   → Shows: safety gate BLOCKS this answer, escalation message ✅

4. "What is the CEO's home address?"
   → Shows: not in context, system refuses to guess ✅
```

Point out: source document, section, safety gate result on every answer.

---

## Why On-Prem for Loomis

| Concern | Cloud AI | On-Prem AI |
|---|---|---|
| Data sovereignty | ❌ Data sent to OpenAI | ✅ Never leaves network |
| SOX / PCI-DSS | ❌ Requires agreements | ✅ Built-in compliance |
| Cost at scale | ❌ $463,500/year (5,000 users) | ✅ ~$13,200/year ongoing |
| Break-even | — | ✅ Under 2 months |
| Model control | ❌ OpenAI controls updates | ✅ You control everything |

---

## Cost Summary

```
Pilot hardware (20-50 users):      $8,000 – $15,000  one-time
Full deployment (5,000 users):     $35,000 – $75,000  one-time
Software licensing:                $0  (100% open source)
Ongoing operational:               ~$1,100/month
Cloud API alternative:             $38,625/month
Break-even vs cloud:               < 2 months
3-year savings vs cloud:           $1.3 million
```

---

## Built By

**Sushant Kakkeri**
Senior Enterprise Software Engineer → AI Engineer
15+ years enterprise systems | 6 production AI projects

- GitHub: github.com/Sushant-Kakkeri
- Stack Platform (live): https://d1fgnt115znksx.cloudfront.net/App.html

---

## Related Projects

| Project | Description | Live |
|---|---|---|
| Stock Intelligence Platform | 80 stocks, 15-min scans, AI analysis, Telegram alerts | ✅ AWS |
| MCP Research Assistant | Autonomous agent, 7 tools, GPT-4o | ✅ Streamlit Cloud |
| RAG + MCP Demo | RAG pipeline with LangSmith tracing | ✅ Streamlit Cloud |
| Pega MCP Court Assistant | MCP server wrapping enterprise Pega AgentX API | 🚧 In Progress |
