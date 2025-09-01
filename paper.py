import arxiv
import requests
import os
from urllib.parse import quote

# Define keywords from the provided list
keywords = [
    'AI-assisted annotation', 'aerial imagery', 'object detection', 'time reduction',
    'YOLOv12', 'SAM 2', 'CVAT', 'semantic segmentation', 'active learning'
]

# Combine keywords into a search query
search_query = ' OR '.join([f'"{keyword}"' for keyword in keywords])

# Directory to save papers
output_dir = 'downloaded_papers'
os.makedirs(output_dir, exist_ok=True)

# Search arXiv
client = arxiv.Client()
search = arxiv.Search(
    query=search_query,
    max_results=50,  # Adjust as needed
    sort_by=arxiv.SortCriterion.SubmittedDate,
    sort_order=arxiv.SortOrder.Descending
)

# Download papers
downloaded = 0
for result in client.results(search):
    try:
        # Extract metadata
        title = result.title
        pdf_url = result.pdf_url
        file_name = f"{output_dir}/{title.replace(' ', '_').replace('/', '_')}.pdf"

        # Download PDF
        response = requests.get(pdf_url)
        if response.status_code == 200:
            with open(file_name, 'wb') as f:
                f.write(response.content)
            print(f"Downloaded: {title}")
            downloaded += 1
        else:
            print(f"Failed to download: {title}")
    except Exception as e:
        print(f"Error processing {title}: {e}")

print(f"Total papers downloaded: {downloaded}")