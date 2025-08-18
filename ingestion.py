from pubmed import PubMedRetriever
import chromadb
from chromadb.utils import embedding_functions
from dotenv import load_dotenv
import os

from groq import Groq


load_dotenv()

# --- Setup ---
groq_client = Groq(api_key=os.environ["GROQ_API_KEY"])
chroma_client = chromadb.PersistentClient(path="./chroma_db")
ef = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name='sentence-transformers/all-MiniLM-L6-v2'
)
COLLECTION_NAME = "pubmed_articles"


# --- Chunk splitter ---
def chunk_text(text, chunk_size=150, overlap=30):
    """
    Split text into overlapping chunks.
    """
    words = text.split()
    chunks = []
    start = 0
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunks.append(" ".join(words[start:end]))
        if end == len(words):
            break
        start += chunk_size - overlap
    return chunks


# --- Ingestion function ---
def ingest_data(topics):
    # Create or load collection
    if COLLECTION_NAME not in [c.name for c in chroma_client.list_collections()]:
        collection = chroma_client.create_collection(
            name=COLLECTION_NAME,
            embedding_function=ef
        )
    else:
        collection = chroma_client.get_collection(
            name=COLLECTION_NAME,
            embedding_function=ef
        )

    # Load all existing metadata + IDs once
    # Correct
    existing = collection.get(include=["metadatas"])  
    existing_ids = set(existing["ids"]) if existing and "ids" in existing else set()
    existing_topics = {meta["topic"] for meta in existing["metadatas"] if "topic" in meta}
    existing_pmids = {eid.split("_")[0] for eid in existing_ids}

    for topic in topics:
        print(f"\nChecking topic: {topic}")

        # Skip if topic already exists
        if topic in existing_topics:
            print(f"Topic '{topic}' already ingested, skipping PubMed fetch.")
            continue

        print(f"Fetching new data from PubMed for topic: {topic}")

        # Fetch from PubMed
        pmids = PubMedRetriever.search_pubmed_articles(topic, max_results=5)

        # Skip already-ingested PMIDs
        new_pmids = [pmid for pmid in pmids if pmid not in existing_pmids]
        if not new_pmids:
            print(f"All PubMed articles for '{topic}' already exist, skipping.")
            continue

        articles = PubMedRetriever.fetch_pubmed_abstracts(new_pmids)

        for article in articles:
            # Flatten abstract (dict → string)
            if isinstance(article["abstract"], dict):
                article["abstract"] = " ".join([f"{k}: {v}" for k, v in article["abstract"].items()])

            abstract_text = article["title"] + " " + article["abstract"]

            # Split into chunks
            chunks = chunk_text(abstract_text, chunk_size=150, overlap=30)

            # Create unique IDs with pmid+chunk
            chunk_ids = [f"{article['pmid']}_{i}" for i in range(len(chunks))]

            # Add only if ID not already present
            new_chunk_ids = [cid for cid in chunk_ids if cid not in existing_ids]
            new_chunks = [chunks[i] for i, cid in enumerate(chunk_ids) if cid not in existing_ids]
            new_metadatas = [{
                "title": article["title"],
                "journal": article["journal"],
                "authors": article["authors"],
                "publication_date": article["publication_date"],
                "topic": topic,
                "chunk_index": i
            } for i, cid in enumerate(chunk_ids) if cid not in existing_ids]

            if new_chunk_ids:
                collection.add(
                    ids=new_chunk_ids,
                    documents=new_chunks,
                    metadatas=new_metadatas
                )
                print(f"Added {len(new_chunk_ids)} chunks for article {article['pmid']}")
            else:
                print(f"Article {article['pmid']} already ingested, skipping.")
        existing_pmids.update(new_pmids)


# --- Query function ---
def get_relevant_qa(query, n_results=3):
    collection = chroma_client.get_collection(
        name=COLLECTION_NAME,
        embedding_function=ef
    )
    result = collection.query(
        query_texts=[query],
        n_results=n_results
    )
    print(result)
    return result


# --- LLM Answer Generation ---
def generate_answer(query, context):
    prompt = f"""
    You are an expert medical researcher. Your task is to answer the user's question based on the provided context.
    - Keep the answer concise (1-2 sentences maximum).
    - Avoid repeating the context verbatim.
    - If the answer is not found in the context, reply "I don't know".

    CONTEXT: {context}

    QUESTION: {query}
    """
    completion = groq_client.chat.completions.create(
        model=os.environ["GROQ_MODEL"],
        messages=[{"role": "user", "content": prompt}]
    )
    return completion.choices[0].message.content


# --- Chain ---
def chain(query):
    result = get_relevant_qa(query)
    context = " ".join([doc for docs in result["documents"] for doc in docs])  # join top chunks
    print("\nContext Provided to LLM:\n", context[:500], "...")  # preview first 500 chars
    answer = generate_answer(query, context)
    return answer


# --- Main ---
if __name__ == "__main__":
    topics = [
        "intermittent fasting diabetes",
        "hypertension lifestyle",
        "cardiovascular exercise"
    ]
    ingest_data(topics)

    query = "Is intermittent fasting useful for diabetes?"
    print("\nQuery:", query)
    answer = chain(query)
    print("\nAnswer:", answer)
