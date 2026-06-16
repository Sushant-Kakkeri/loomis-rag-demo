"""
chain.py — LangChain RAG chain with LangSmith tracing.
This is the core of the application.
"""

import os
from dotenv import load_dotenv
from langchain_core.prompts        import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables      import RunnablePassthrough
from langchain_openai              import ChatOpenAI
from langsmith                     import traceable
from pydantic                      import BaseModel
from typing                        import Literal

from retriever import get_retriever, format_docs

load_dotenv()

LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
LLM_MODEL    = os.getenv("LLM_MODEL",    "gpt-4o-mini")


# ── LLM ──────────────────────────────────────────────────────────────
def get_llm():
    """
    Returns LLM client.
    Cloud:   LLM_BASE_URL=https://api.openai.com/v1
    On-prem: LLM_BASE_URL=http://localhost:11434/v1
    Same code — swap the env var.
    """
    return ChatOpenAI(
        base_url    = LLM_BASE_URL,
        api_key     = os.getenv("OPENAI_API_KEY", "ollama"),
        model       = LLM_MODEL,
        temperature = 0,
        streaming   = True
    )


# ── Prompt ───────────────────────────────────────────────────────────
LOOMIS_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """You are a policy assistant for Loomis Armored US employees.

RULES:
1. Answer ONLY from the context provided below. Never use outside knowledge.
2. For security or safety questions — quote the exact policy rule verbatim first.
3. Never soften, add exceptions to, or interpret rules beyond what is written.
4. If the answer is not in the context respond exactly:
   "I don't have that information in our policy documents. 
    Please contact your supervisor or HR directly."
5. Never say "I think", "probably", or "might be".
6. Keep answers concise — under 150 words unless the question requires more.

CONTEXT:
{context}"""
    ),
    (
        "human",
        "{question}"
    )
])


# ── Safety gate ───────────────────────────────────────────────────────
UNSAFE_PHRASES = [
    "alone", "by yourself", "single person", "just one person",
    "without a partner", "solo", "on your own",
    "skip form", "don't need the form", "form is optional",
    "exceptions apply", "senior staff may", "depending on authorization"
]

@traceable(name="safety-gate")
def check_safety(answer: str) -> bool:
    """
    Returns True if answer is safe to return to employee.
    Returns False if answer contains unsafe phrases.
    """
    answer_lower = answer.lower()
    for phrase in UNSAFE_PHRASES:
        if phrase in answer_lower:
            return False
    return True


@traceable(name="verify-source-quote")
def verify_quote_in_context(answer: str, context: str) -> bool:
    """
    Check if key phrases in the answer exist in the retrieved context.
    Catches hallucinated quotes.
    """
    # Extract quoted text if present
    import re
    quotes = re.findall(r'"([^"]*)"', answer)

    for quote in quotes:
        if len(quote) > 20:  # only check substantial quotes
            if quote.lower() not in context.lower():
                return False

    return True


# ── Main RAG chain ────────────────────────────────────────────────────
@traceable(name="loomis-rag-pipeline")
def run_rag(question: str, category_filter: str = None) -> dict:
    """
    Full RAG pipeline with LangSmith tracing.
    Returns answer + metadata for the UI.
    """
    # Step 1: Retrieve relevant chunks
    retriever = get_retriever(category_filter=category_filter)
    docs      = retriever.invoke(question)
    context   = format_docs(docs)

    # Step 2: Build and run the chain
    llm   = get_llm()
    chain = LOOMIS_PROMPT | llm | StrOutputParser()

    answer = chain.invoke({
        "context":  context,
        "question": question
    })

    # Step 3: Safety checks
    is_safe         = check_safety(answer)
    quote_verified  = verify_quote_in_context(answer, context)

    # Step 4: Block unsafe answers
    if not is_safe:
        answer = (
            "This question involves a security policy. "
            "Please verify the exact rule with your supervisor "
            "or the Regional Security Director."
        )

    # Return answer + audit metadata
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
    Streaming version — yields tokens as they're generated.
    Used by Streamlit for real-time display.
    """
    retriever = get_retriever(category_filter=category_filter)
    docs      = retriever.invoke(question)
    context   = format_docs(docs)

    llm   = get_llm()
    chain = LOOMIS_PROMPT | llm | StrOutputParser()

    # Stream tokens
    for chunk in chain.stream({
        "context":  context,
        "question": question
    }):
        yield chunk


if __name__ == "__main__":
    # Quick test
    test_questions = [
        "Can I access the vault alone on weekends?",
        "How many vacation days do I get per year?",
        "What happens if visibility is low on a route?",
        "What is the CEO's home address?",   # should refuse
    ]

    for q in test_questions:
        print(f"\n{'='*60}")
        print(f"Q: {q}")
        print(f"{'='*60}")
        result = run_rag(q)
        print(f"A: {result['answer']}")
        print(f"Sources: {result['sources']}")
        print(f"Safe: {result['is_safe']}")
        print(f"Quote verified: {result['quote_verified']}")