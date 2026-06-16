"""
chain.py — LangChain RAG chain with safety gate.
Core of the application — orchestrates retrieval, generation, and safety checks.
Called by app.py for every employee query.
"""

import os

# Streamlit Cloud secrets support
try:
    import streamlit as st
    for key, value in st.secrets.items():
        os.environ[key] = str(value)
except:
    pass

from dotenv import load_dotenv
load_dotenv()

import re
from langchain_core.prompts        import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables      import RunnablePassthrough
from langchain_openai              import ChatOpenAI

from retriever import get_retriever, format_docs

# ── Config ────────────────────────────────────────────────────────────────────
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
LLM_MODEL    = os.getenv("LLM_MODEL",    "gpt-4o-mini")
OPENAI_KEY   = os.getenv("OPENAI_API_KEY", "ollama")


# ── LLM ──────────────────────────────────────────────────────────────────────

def get_llm():
    """
    Returns LLM client.
    Cloud:   LLM_BASE_URL=https://api.openai.com/v1  (development)
    On-prem: LLM_BASE_URL=http://localhost:11434/v1   (production / Loomis)
    Same code — swap the env var. Application doesn't know or care.
    """
    return ChatOpenAI(
        base_url    = LLM_BASE_URL,
        api_key     = OPENAI_KEY,
        model       = LLM_MODEL,
        temperature = 0,        # deterministic — same question, same answer
        streaming   = True      # tokens stream to UI in real time
    )


# ── System prompt ─────────────────────────────────────────────────────────────

LOOMIS_SYSTEM_PROMPT = """You are a policy assistant for Loomis Armored US employees.

RULES:
1. Answer ONLY from the context provided below. Never use outside knowledge.
2. For security or safety questions — quote the exact policy rule verbatim first, then explain.
3. Never soften, add exceptions to, or interpret rules beyond what is written.
   If the source says "no exceptions" — there are NO exceptions.
4. If the answer is not in the context, respond exactly:
   "I don't have that information in our policy documents. Please contact your supervisor or HR directly."
5. Never say "I think", "probably", "might be", "may", or "depending on".
6. Never suggest that senior staff, authorized personnel, or any group has special exceptions
   unless the policy explicitly states this.
7. Keep answers concise — under 150 words unless the question requires more detail.

CONTEXT:
{context}"""

LOOMIS_PROMPT = ChatPromptTemplate.from_messages([
    ("system", LOOMIS_SYSTEM_PROMPT),
    ("human",  "{question}")
])


# ── Safety gate ───────────────────────────────────────────────────────────────

# Phrases that indicate a potentially dangerous answer
UNSAFE_PHRASES = [
    "alone", "by yourself", "single person", "just one person",
    "without a partner", "solo", "on your own",
    "skip form", "don't need the form", "form is optional",
    "exceptions apply", "senior staff may", "depending on authorization",
    "authorized personnel can", "you may access"
]

def check_safety(answer: str) -> bool:
    """
    Returns True if answer is safe to return to employee.
    Returns False if answer contains unsafe phrases that could
    lead an employee to violate a security procedure.
    """
    answer_lower = answer.lower()
    for phrase in UNSAFE_PHRASES:
        if phrase in answer_lower:
            return False
    return True


def verify_quote_in_context(answer: str, context: str) -> bool:
    """
    Verify that any quoted text in the answer exists in the context.
    Catches hallucinated source quotes.
    Returns True if all quotes are verified (or no quotes present).
    """
    quotes = re.findall(r'"([^"]{20,})"', answer)
    for quote in quotes:
        if quote.lower() not in context.lower():
            return False
    return True


# ── Main RAG pipeline ─────────────────────────────────────────────────────────

def run_rag(question: str, category_filter: str = None) -> dict:
    """
    Full RAG pipeline — question in, grounded answer out.

    Args:
        question:        Employee's question in plain English
        category_filter: Optional — restrict search to one document category
                         "vault_access" | "hr_policy" | "route_operations"

    Returns:
        dict with keys:
            answer          — text to show the employee
            sources         — list of source document names
            chunks_found    — number of relevant chunks retrieved
            is_safe         — did the safety gate pass?
            quote_verified  — are source quotes verified in context?
            context         — full context block (for debugging/LangSmith)
            model           — which model generated this answer
    """
    # Step 1: Retrieve relevant chunks from ChromaDB
    retriever = get_retriever(
        category_filter = category_filter,
        top_k           = 5
    )
    docs    = retriever.invoke(question)
    context = format_docs(docs)

    # Step 2: No relevant chunks found
    if not docs or context == "No relevant policy information found.":
        return {
            "answer":         "I don't have that information in our policy documents. "
                              "Please contact your supervisor or HR directly.",
            "sources":        [],
            "chunks_found":   0,
            "is_safe":        True,
            "quote_verified": True,
            "context":        "",
            "model":          LLM_MODEL,
        }

    # Step 3: Build and run the LangChain chain
    llm   = get_llm()
    chain = LOOMIS_PROMPT | llm | StrOutputParser()

    answer = chain.invoke({
        "context":  context,
        "question": question
    })

    # Step 4: Safety checks
    is_safe        = check_safety(answer)
    quote_verified = verify_quote_in_context(answer, context)

    # Step 5: Block unsafe answers before they reach the employee
    if not is_safe:
        answer = (
            "This question involves a security or safety policy. "
            "Please verify the exact procedure with your supervisor "
            "or the Regional Security Director before taking any action."
        )

    # Step 6: Build source list for audit trail
    sources = list(set(
        doc.metadata.get("source", "unknown")
        for doc in docs
    ))

    return {
        "answer":         answer,
        "sources":        sources,
        "chunks_found":   len(docs),
        "is_safe":        is_safe,
        "quote_verified": quote_verified,
        "context":        context,
        "model":          LLM_MODEL,
    }


def stream_rag(question: str, category_filter: str = None):
    """
    Streaming version of the RAG pipeline.
    Yields tokens as they are generated — used by Streamlit for real-time display.

    Note: Safety gate runs separately in app.py via run_rag() after streaming completes.
    """
    retriever = get_retriever(
        category_filter = category_filter,
        top_k           = 5
    )
    docs    = retriever.invoke(question)
    context = format_docs(docs)

    if not docs or context == "No relevant policy information found.":
        yield "I don't have that information in our policy documents. Please contact your supervisor or HR directly."
        return

    llm   = get_llm()
    chain = LOOMIS_PROMPT | llm | StrOutputParser()

    for chunk in chain.stream({
        "context":  context,
        "question": question
    }):
        yield chunk


# ── Quick test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    test_questions = [
        "Can I access the vault alone on weekends?",
        "How many vacation days do I get per year?",
        "What happens if visibility is low on a route?",
        "What is the CEO's home address?",
    ]

    for q in test_questions:
        print(f"\n{'=' * 60}")
        print(f"Q: {q}")
        print(f"{'=' * 60}")
        result = run_rag(q)
        print(f"A: {result['answer']}")
        print(f"Sources:        {result['sources']}")
        print(f"Chunks found:   {result['chunks_found']}")
        print(f"Safe:           {result['is_safe']}")
        print(f"Quote verified: {result['quote_verified']}")
        print(f"Model:          {result['model']}")
