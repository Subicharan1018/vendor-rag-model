# RAG Core Engine

<cite>
**Referenced Files in This Document**   
- [rag.py](file://rag.py)
- [retriever.py](file://retriever.py)
- [details.py](file://details.py)
</cite>

## Table of Contents
1. [Introduction](#introduction)
2. [Core Architecture](#core-architecture)
3. [Query Processing Pipeline](#query-processing-pipeline)
4. [Project Requirements Extraction](#project-requirements-extraction)
5. [Material Estimation Integration](#material-estimation-integration)
6. [Context Filtering and Relevance](#context-filtering-and-relevance)
7. [Response Generation and Prompt Engineering](#response-generation-and-prompt-engineering)
8. [Source Attribution and Output Formatting](#source-attribution-and-output-formatting)
9. [Conclusion](#conclusion)

## Introduction

The IndiaMART_RAG class implements a sophisticated Retrieval-Augmented Generation (RAG) engine specifically designed for construction procurement queries. This system orchestrates a complete pipeline from input parsing to final response generation, combining semantic search, context-aware filtering, project specification analysis, and LLM-powered response synthesis. The engine processes natural language queries about construction materials and vendors, extracting key requirements, retrieving relevant product information from a knowledge base, applying intelligent filters, and generating comprehensive, context-aware responses with proper source attribution.

**Section sources**
- [rag.py](file://rag.py#L11-L409)

## Core Architecture

The RAG engine follows a modular architecture with distinct components for data loading, indexing, retrieval, filtering, and response generation. The system is initialized with a JSON directory containing product data and uses the SentenceTransformer model for embedding generation. The FAISS vector index enables efficient similarity search across the product catalog.

```mermaid
classDiagram
class IndiaMART_RAG {
+str json_dir
+str embedding_model_name
+SentenceTransformer embedding_model
+IndexFlatL2 index
+List[str] documents
+List[Dict] metadata
+__init__(json_dir : str, embedding_model : str)
+load_and_process_json_files() void
+build_faiss_index() void
+search(query : str, k : int) List[Dict]
+filter_by_criteria(results : List[Dict], query : str) List[Dict]
+extract_project_requirements(query : str) Dict[str, Any]
+estimate_material_requirements(requirements : Dict) List[Dict]
+generate_response(query : str, context : List[Dict], requirements : Dict, material_estimates : List[Dict]) str
+format_material_table(materials : List[Dict]) str
+query(query : str, k : int, apply_filters : bool) Dict[str, Any]
}
class SentenceTransformer {
+encode(text : str) ndarray
}
class IndexFlatL2 {
+add(embeddings : ndarray) void
+search(query_embedding : ndarray, k : int) Tuple[distances, indices]
}
IndiaMART_RAG --> SentenceTransformer : "uses for embeddings"
IndiaMART_RAG --> IndexFlatL2 : "uses for vector search"
```

**Diagram sources**
- [rag.py](file://rag.py#L11-L409)

**Section sources**
- [rag.py](file://rag.py#L11-L409)

## Query Processing Pipeline

The query method serves as the central orchestrator of the RAG pipeline, coordinating multiple stages of processing to transform a natural language query into a comprehensive response. The workflow begins with project requirements extraction, followed by document retrieval, context filtering, response generation, and final output formatting.

```mermaid
flowchart TD
A["User Query"] --> B["extract_project_requirements"]
B --> C{"Project Requirements Detected?"}
C --> |Yes| D["estimate_material_requirements"]
C --> |No| E["Skip material estimation"]
D --> F["search documents"]
E --> F
F --> G["filter_by_criteria"]
G --> H["generate_response"]
H --> I["format_material_table"]
I --> J["Return final response with sources"]
style A fill:#f9f,stroke:#333
style J fill:#bbf,stroke:#333
```

**Diagram sources**
- [rag.py](file://rag.py#L372-L409)

**Section sources**
- [rag.py](file://rag.py#L372-L409)

## Project Requirements Extraction

The system employs pattern-based extraction to identify key project specifications from user queries. The extract_project_requirements method scans for numerical values associated with power capacity (in Megawatts), built-up area (in Lacs Square Feet), and project volume (in Crores Rupees). It also extracts location information, with special handling for "Navi Mumbai" as a common query parameter. This structured extraction enables the system to understand the scale and context of construction projects, which informs subsequent material estimation and vendor recommendations.

```mermaid
flowchart TD
A["Input Query"] --> B["Search for power capacity pattern"]
B --> C{"Found Megawatt value?"}
C --> |Yes| D["Extract power capacity in MW"]
C --> |No| E["Set power capacity to None"]
A --> F["Search for built-up area pattern"]
F --> G{"Found Lacs Square Feet value?"}
G --> |Yes| H["Convert to square feet"]
G --> |No| I["Set built-up area to None"]
A --> J["Search for project volume pattern"]
J --> K{"Found Crores value?"}
K --> |Yes| L["Convert to rupees"]
K --> |No| M["Set project volume to None"]
A --> N["Search for location pattern"]
N --> O{"Found location?"}
O --> |Yes| P["Extract location"]
O --> |No| Q["Set location to None"]
D --> R["Store in requirements dict"]
H --> R
L --> R
P --> R
R --> S["Return requirements"]
style A fill:#f9f,stroke:#333
style S fill:#bbf,stroke:#333
```

**Diagram sources**
- [rag.py](file://rag.py#L207-L241)

**Section sources**
- [rag.py](file://rag.py#L207-L241)

## Material Estimation Integration

When project requirements are detected, the system generates material estimates using industry-standard construction norms. The estimate_material_requirements method calculates quantities and costs for key construction materials based on the extracted project specifications. For building projects, it estimates cement and brick requirements based on built-up area. For power projects, it estimates switchgear, transformers, and cooling systems based on power capacity. The estimates include both quantities and cost projections, providing valuable guidance for procurement planning.

```mermaid
flowchart TD
A["Project Requirements"] --> B{"Has built-up area?"}
B --> |Yes| C["Calculate cement: 0.4 bags/sq ft"]
C --> D["Convert to cubic meters"]
D --> E["Estimate cost at ₹6,000/m³"]
B --> |Yes| F["Calculate bricks: 8 bricks/sq ft"]
F --> G["Estimate cost at ₹0.08/brick"]
A --> H{"Has power capacity?"}
H --> |Yes| I["Calculate MV Switchgear: 1 per 2.5 MW"]
I --> J["Estimate cost at ₹0.2 Cr/lineup"]
H --> |Yes| K["Calculate Transformers: 1 per 5 MW"]
K --> L["Estimate cost at ₹6.67 Cr/unit"]
H --> |Yes| M["Calculate Cooling Units: 2 per MW"]
M --> N["Estimate cost at ₹0.3 Cr/unit"]
E --> O["Format as table"]
G --> O
J --> O
L --> O
N --> O
O --> P["Return material estimates"]
style A fill:#f9f,stroke:#333
style P fill:#bbf,stroke:#333
```

**Diagram sources**
- [rag.py](file://rag.py#L243-L301)

**Section sources**
- [rag.py](file://rag.py#L243-L301)

## Context Filtering and Relevance

The filter_by_criteria method applies intelligent post-retrieval filtering to ensure response relevance. It examines search results against query-specific criteria such as location, GST registration date, vendor ratings, product availability, and material properties like fire retardancy. The filtering logic combines text pattern matching with structured data analysis, allowing the system to honor complex user requirements. For example, when a user requests "vendors with GST after 2017 in Navi Mumbai with high ratings," the system validates each candidate vendor's GST registration date, location, and rating before including them in the response.

```mermaid
sequenceDiagram
participant Query as "User Query"
participant Filter as "filter_by_criteria"
participant Result as "Search Result"
participant Metadata as "Metadata"
Query->>Filter : Apply filters based on query
loop For each search result
Filter->>Result : Check location requirement
alt Location specified
Result->>Metadata : Extract address
Metadata->>Result : Match against query location
Result->>Filter : Continue if no match
end
Filter->>Result : Check GST after 2017
alt GST requirement
Result->>Metadata : Extract GST date
Metadata->>Result : Parse and validate year
Result->>Filter : Continue if <= 2017
end
Filter->>Result : Check high rating
alt Rating requirement
Result->>Metadata : Extract overall rating
Metadata->>Result : Validate ≥ 4.0
Result->>Filter : Continue if below threshold
end
Filter->>Result : Check availability
alt Stock requirement
Result->>Metadata : Extract availability
Metadata->>Result : Match "in stock"
Result->>Filter : Continue if not in stock
end
Filter->>Result : Check fire retardant
alt Fire safety requirement
Result->>Metadata : Search details/description
Metadata->>Result : Match "fire retardant" or "fireproof"
Result->>Filter : Continue if no match
end
Filter->>Filter : Add to filtered_results
end
Filter->>Query : Return filtered results
```

**Diagram sources**
- [rag.py](file://rag.py#L142-L205)

**Section sources**
- [rag.py](file://rag.py#L142-L205)

## Response Generation and Prompt Engineering

The generate_response method orchestrates context-aware response generation using the Ollama LLM. It constructs a comprehensive prompt that includes retrieved product information, vendor details, and material estimates when applicable. The prompt engineering strategy emphasizes factual accuracy, source attribution, and structured output. The system instructs the LLM to only use information from the provided context, include URLs for all mentioned products, and format material estimates as tables. This careful prompt design ensures consistent, reliable, and actionable responses that meet the needs of construction procurement professionals.

```mermaid
flowchart TD
A["Query and Context"] --> B["Prepare context text"]
B --> C["Include document titles"]
C --> D["Include URLs"]
D --> E["Include details"]
E --> F["Include seller info"]
F --> G["Include company info"]
G --> H["Include reviews"]
H --> I{"Has material estimates?"}
I --> |Yes| J["Add material estimates to context"]
I --> |No| K["Skip material estimates"]
J --> L["Create structured prompt"]
K --> L
L --> M["Include role definition"]
M --> N["Include context"]
N --> O["Include query"]
O --> P["Include response instructions"]
P --> Q["Generate response via Ollama"]
Q --> R["Return generated text"]
style A fill:#f9f,stroke:#333
style R fill:#bbf,stroke:#333
```

**Diagram sources**
- [rag.py](file://rag.py#L303-L355)

**Section sources**
- [rag.py](file://rag.py#L303-L355)

## Source Attribution and Output Formatting

The system maintains transparency through comprehensive source attribution. All retrieved documents contribute their URLs to the sources list, which is included in the final response. When material estimates are generated, they are formatted as Markdown tables with clear headers for Material/Equipment, Quantity, and Unit Cost. The final output combines the LLM-generated response with the material estimation table (when applicable) and the list of source URLs, providing a complete and verifiable answer. This approach ensures users can validate information and explore original product listings for further details.

**Section sources**
- [rag.py](file://rag.py#L372-L409)

## Conclusion

The IndiaMART_RAG engine demonstrates a sophisticated implementation of RAG principles for construction procurement. By integrating semantic search, structured data extraction, intelligent filtering, and LLM-powered response generation, the system provides comprehensive, context-aware answers to complex procurement queries. Its ability to extract project specifications, generate material estimates, and apply multi-criteria filtering makes it particularly valuable for construction professionals who need accurate, actionable information. The transparent source attribution and structured output formatting further enhance the system's reliability and usability in professional settings.