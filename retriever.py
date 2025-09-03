# retriever.py
import chromadb
from sentence_transformers import SentenceTransformer

client = chromadb.PersistentClient(path="./chroma_db")
collection = client.get_collection(name="products")
embedding_model = SentenceTransformer('all-MiniLM-L6-v2')

def retrieve(query, top_k=5):
    """
    Retrieve top-k relevant chunks based on cosine similarity.
    """
    query_embedding = embedding_model.encode(query).tolist()
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        include=["documents", "metadatas", "distances"]
    )
    return results