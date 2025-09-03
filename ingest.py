# ingest.py (updated)
import json
import glob
from sentence_transformers import SentenceTransformer
from transformers import AutoTokenizer
import chromadb

def chunk_text(text, tokenizer, max_tokens=400, overlap=50):
    """
    Chunk text into segments of max_tokens with overlap.
    Adjusted max_tokens to 400 for safety with model limits.
    """
    tokens = tokenizer.encode(text, add_special_tokens=False)
    chunks = []
    for i in range(0, len(tokens), max_tokens - overlap):
        chunk_tokens = tokens[i:i + max_tokens]
        chunk = tokenizer.decode(chunk_tokens)
        chunks.append(chunk)
    return chunks

# Initialize models and DB
embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
tokenizer = AutoTokenizer.from_pretrained('sentence-transformers/all-MiniLM-L6-v2')
client = chromadb.PersistentClient(path="./chroma_db")
collection = client.get_or_create_collection(name="products")

# Load all JSON files
json_files = glob.glob("json/*.json")

for file_idx, file_path in enumerate(json_files):
    with open(file_path, 'r') as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            print(f"Skipping invalid JSON: {file_path}")
            continue

    # Handle case where data is a list of objects
    if isinstance(data, list):
        items = data
    else:
        items = [data]  # Wrap single object in a list for consistent processing

    for item_idx, item in enumerate(items):
        # Flatten fields into a single text
        text = ""
        if 'title' in item:
            text += item['title'] + "\n"
        if 'description' in item:
            text += item['description'] + "\n"

        details = item.get('details', {})
        for key, value in details.items():
            text += f"{key}: {value}\n"

        company_info = item.get('company_info', {})
        if company_info:
            text += "\nCompany Info: " + " ".join([f"{k}: {v}" for k, v in company_info.items()]) + "\n"

        seller_info = item.get('seller_info', {})
        if seller_info:
            text += "Seller Info: " + " ".join([f"{k}: {v}" for k, v in seller_info.items()]) + "\n"

        reviews = item.get('reviews', [])
        if reviews:
            text += "Reviews:\n"
            for review in reviews[:5]:  # Top 5 reviews
                rating = review.get('rating', 'N/A')
                comment = review.get('comment', '')
                text += f"Rating: {rating} Comment: {comment}\n"

        # Chunk the text if necessary
        chunks = chunk_text(text, tokenizer)

        # Prepare metadata (category assumed in details if present)
        metadata = {
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "category": details.get("category", "")
        }

        # Embed and store each chunk
        for chunk_idx, chunk in enumerate(chunks):
            if not chunk.strip():
                continue
            embedding = embedding_model.encode(chunk).tolist()
            doc_id = f"{file_path.split('/')[-1]}_{item_idx}_{chunk_idx}"
            collection.add(
                ids=[doc_id],
                embeddings=[embedding],
                documents=[chunk],
                metadatas=[metadata]
            )

print("Ingestion complete.")