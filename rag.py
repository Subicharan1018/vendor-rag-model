# rag.py
import requests
from retriever import retrieve

def query_ollama(prompt, model="llama3:latest"):
    """
    Query Ollama's API with the given prompt and model.
    """
    url = "http://localhost:11434/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.7,
            "max_tokens": 300  # Adjusted to match original generation kwargs
        }
    }
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        return response.json().get("response", "")
    except requests.RequestException as e:
        print(f"Ollama API error: {e}")
        return "Error generating response from Ollama."

def rag(query, top_k=5, model="llama3:latest"):
    """
    RAG pipeline: Retrieve context and generate answer using Ollama.
    Supports queries like attribute-based, location-based, review-based, supplier info.
    Output: Answer text + list of source URLs.
    """
    results = retrieve(query, top_k)
    documents = results.get('documents', [[]])[0]
    metadatas = results.get('metadatas', [[]])[0]

    if not documents:
        return "No relevant products found.\n\nSources:\nNone"

    context = "\n\n".join(documents)
    sources = list(set([meta.get('url', '') for meta in metadatas if meta.get('url')]))

    prompt = f"""
You are a product and vendor assistant for construction procurement.
Answer the query based on the provided context from the IndiaMART product database.

Context:
{context}

Query: {query}

Instructions:
- Only use information from the context. Do not invent details.
- If listing products, include the product name, key details (brand, availability, location), and vendor name.
- If the query asks for vendors, show company name, address, GST status, and rating if available.
- Provide URLs for all products/vendors mentioned.
- If the query involves filtering (e.g., fireproof, GST after 2017, rating > 4), apply it based on context.
- Answer should be factual, concise, and helpful.

Answer:
"""

    # Generate response using Ollama
    answer = query_ollama(prompt, model).strip()

    output = f"{answer}\n\nSources:\n" + "\n".join(sources)
    return output

# Example usage
if __name__ == "__main__":
    example_query = "Find fireproof insulation products."
    print(rag(example_query))