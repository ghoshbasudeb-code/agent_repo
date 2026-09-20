# rag_engine/retriever.py
from langchain_community.vectorstores import Qdrant
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

# Chunking Configuration
text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)

def ingest_and_retrieve(documents: list[str], user_query: str):
    # 1. Chunk Documents
    chunks = text_splitter.create_documents(documents)
    
    # 2. Compute Embeddings using an Encoder Model
    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
    
    # 3. Store in Vector DB (In-memory example)
    vector_store = Qdrant.from_documents(
        chunks, 
        embeddings, 
        location=":memory:", 
        collection_name="enterprise_knowledge"
    )
    
    # 4. Perform Similarity Search
    retriever = vector_store.as_retriever(search_kwargs={"k": 3})
    results = retriever.invoke(user_query)
    return [doc.page_content for doc in results]