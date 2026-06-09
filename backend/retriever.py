import os
from pathlib import Path
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

KNOWLEDGE_DIR = Path.home() / ".ai-copilot-knowledge"
CHROMA_DB_DIR = "db/chroma"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
TOP_K_RESULTS = 3


def _getEmbeddings() -> HuggingFaceEmbeddings:
    # Lazy-initialised to avoid loading the model at import time during tests.
    return HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)


def _getVectorStore() -> Chroma:
    """Returns the persistent Chroma vector store, creating the directory if needed."""
    os.makedirs(CHROMA_DB_DIR, exist_ok=True)
    return Chroma(persist_directory=CHROMA_DB_DIR, embedding_function=_getEmbeddings())


def getRelevantContext(query: str) -> str:
    """
    Performs a similarity search against the local knowledge base.
    Returns a concatenated string of the top matching chunks,
    or an empty string if the store is empty or no results are found.
    """
    try:
        vectorStore = _getVectorStore()
        results = vectorStore.similarity_search(query, k=TOP_K_RESULTS)
        if not results:
            return ""
        return "\n\n".join(doc.page_content for doc in results)
    except Exception:
        # If the DB does not exist yet or is empty, degrade gracefully.
        return ""


def ingestDocuments() -> None:
    """
    Reads .txt and .md files from ~/.ai-copilot-knowledge/, splits them into
    chunks, and persists them to the local Chroma vector store.
    """
    if not KNOWLEDGE_DIR.exists():
        print(f"Knowledge directory not found: {KNOWLEDGE_DIR}")
        return

    # Python's glob does not support bash-style brace expansion — use one loader per extension.
    documents = []
    for pattern in ("**/*.txt", "**/*.md"):
        loader = DirectoryLoader(
            str(KNOWLEDGE_DIR),
            glob=pattern,
            loader_cls=TextLoader,
            loader_kwargs={"encoding": "utf-8"},
            silent_errors=True,
        )
        documents.extend(loader.load())

    if not documents:
        print("No .txt or .md documents found in knowledge directory.")
        return

    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    chunks = splitter.split_documents(documents)

    vectorStore = _getVectorStore()
    vectorStore.add_documents(chunks)
    print(f"Ingested {len(chunks)} chunks from {len(documents)} document(s) into {CHROMA_DB_DIR}.")
