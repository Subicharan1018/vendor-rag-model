import json
import os
import re
from typing import List, Dict, Any
import pandas as pd
from sentence_transformers import SentenceTransformer
import faiss
import numpy as np
import ollama
from datetime import datetime

class IndiaMART_RAG:
    def __init__(self, json_dir: str = "json", embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"):
        self.json_dir = r"/home/subi/Documents/rag/vendor-rag-model/json"
        self.embedding_model_name = embedding_model
        self.embedding_model = SentenceTransformer(embedding_model)
        self.index = None
        self.documents = []
        self.metadata = []
        
    def load_and_process_json_files(self):
        """Load all JSON files from the directory and process them"""
        print("Loading JSON files...")
        
        # Get all JSON files in the directory
        json_files = [f for f in os.listdir(self.json_dir) if f.endswith('.json')]
        
        for json_file in json_files:
            file_path = os.path.join(self.json_dir, json_file)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                    # Handle both single objects and arrays of objects
                    if isinstance(data, list):
                        for item in data:
                            self._process_item(item)
                    else:
                        self._process_item(data)
                        
            except Exception as e:
                print(f"Error loading {json_file}: {str(e)}")
                
        print(f"Loaded {len(self.documents)} documents")
    
    def _process_item(self, item: Dict[str, Any]):
        """Process a single item from JSON and add to documents"""
        # Create a text representation for embedding
        text_parts = []
        
        # Add title
        title = item.get('title', '')
        if title:
            text_parts.append(f"Title: {title}")
        
        # Add details
        details = item.get('details', {})
        if details and isinstance(details, dict):
            for key, value in details.items():
                if value:  # Only add non-empty values
                    text_parts.append(f"{key}: {value}")
        
        # Add description
        description = item.get('description', '')
        if description:
            text_parts.append(f"Description: {description}")
        
        # Add seller info
        seller_info = item.get('seller_info', {})
        if seller_info and isinstance(seller_info, dict):
            for key, value in seller_info.items():
                if key != 'error' and value != 'Seller information not available' and value:
                    text_parts.append(f"Seller {key}: {value}")
        
        # Add company info
        company_info = item.get('company_info', {})
        if company_info and isinstance(company_info, dict):
            for key, value in company_info.items():
                if value:  # Only add non-empty values
                    text_parts.append(f"Company {key}: {value}")
        
        # Combine all text parts
        text = " ".join(text_parts)
        
        # Only add if we have meaningful text
        if text.strip():
            # Store the document and metadata
            self.documents.append(text)
            self.metadata.append({
                'url': item.get('url', ''),
                'title': item.get('title', ''),
                'description': item.get('description', ''),
                'details': item.get('details', {}),
                'seller_info': item.get('seller_info', {}),
                'company_info': item.get('company_info', {}),
                'reviews': item.get('reviews', [])
            })
    
    def build_faiss_index(self):
        """Build FAISS index from documents"""
        if not self.documents:
            print("No documents to index!")
            return
            
        print("Building FAISS index...")
        
        # Generate embeddings
        embeddings = self.embedding_model.encode(self.documents, show_progress_bar=True)
        
        # Create FAISS index
        dimension = embeddings.shape[1]
        self.index = faiss.IndexFlatL2(dimension)
        self.index.add(np.array(embeddings).astype('float32'))
        
        print("FAISS index built successfully")
    
    def search(self, query: str, k: int = 5) -> List[Dict[str, Any]]:
        """Search for similar documents to the query"""
        if self.index is None or len(self.documents) == 0:
            raise ValueError("Index not built or no documents loaded")
        
        # Limit k to the number of available documents
        k = min(k, len(self.documents))
        
        # Generate query embedding
        query_embedding = self.embedding_model.encode([query])
        
        # Search in FAISS index
        distances, indices = self.index.search(np.array(query_embedding).astype('float32'), k)
        
        # Return results with metadata
        results = []
        for i, idx in enumerate(indices[0]):
            if idx < len(self.metadata):
                results.append({
                    'document': self.documents[idx],
                    'metadata': self.metadata[idx],
                    'distance': float(distances[0][i])  # Convert to Python float
                })
        
        return results
    
    def filter_by_criteria(self, results: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
        """Apply additional filtering based on query criteria"""
        filtered_results = []
        
        for result in results:
            metadata = result['metadata']
            company_info = metadata.get('company_info', {})
            details = metadata.get('details', {})
            
            # Check for location filters
            if "in " in query.lower() or "navi mumbai" in query.lower():
                location_match = re.search(r'in\s+([\w\s]+)$', query.lower())
                location = "navi mumbai" if "navi mumbai" in query.lower() else None
                if location_match and not location:
                    location = location_match.group(1).strip()
                
                if location:
                    address = str(company_info.get('full_address', '')).lower() + " " + str(metadata.get('seller_info', {}).get('full_address', '')).lower()
                    if location not in address:
                        continue
            
            # Check for GST after 2017
            if "gst after 2017" in query.lower():
                gst_date = company_info.get('gst_registration_date', '')
                if gst_date:
                    try:
                        date_obj = datetime.strptime(gst_date, '%d-%m-%Y')
                        if date_obj.year <= 2017:
                            continue
                    except ValueError:
                        continue
                else:
                    continue
            
            # Check for high ratings
            if "high rating" in query.lower() or "rating" in query.lower():
                reviews = metadata.get('reviews', [])
                overall_rating = None
                for review in reviews:
                    if review.get('type') == 'overall_rating':
                        try:
                            overall_rating = float(review.get('value', 0))
                            break
                        except (ValueError, TypeError):
                            pass
                
                if overall_rating is None or overall_rating < 4.0:
                    continue
            
            # Check for availability
            if "available in stock" in query.lower() or "in stock" in query.lower():
                availability = str(details.get('availability', '')).lower()
                if 'in stock' not in availability:
                    continue
            
            # Check for fire retardant
            if "fire retardant" in query.lower() or "fireproof" in query.lower():
                details_text = str(details).lower() + " " + str(metadata.get('description', '')).lower()
                if 'fire retardant' not in details_text and 'fireproof' not in details_text:
                    continue
            
            filtered_results.append(result)
        
        return filtered_results
    
    def extract_project_requirements(self, query: str) -> Dict[str, Any]:
        """Extract project requirements from the query"""
        requirements = {
            "power_capacity": None,
            "built_up_area": None,
            "project_volume": None,
            "location": None,
            "materials": {}
        }
        
        # Extract power capacity
        power_match = re.search(r'(\d+)\s*Mega?Watt', query, re.IGNORECASE)
        if power_match:
            requirements["power_capacity"] = float(power_match.group(1))
        
        # Extract built up area
        area_match = re.search(r'(\d+)\s*Lacs?\s*SquareFoot', query, re.IGNORECASE)
        if area_match:
            requirements["built_up_area"] = float(area_match.group(1)) * 100000  # Convert lacs to actual number
        
        # Extract project volume
        volume_match = re.search(r'(\d+)\s*Cr\s*(in\s*Rupees)?', query, re.IGNORECASE)
        if volume_match:
            requirements["project_volume"] = float(volume_match.group(1)) * 10000000  # Convert Cr to rupees
        
        # Extract location
        location_match = re.search(r'in\s+([\w\s]+)$', query, re.IGNORECASE)
        if location_match:
            requirements["location"] = location_match.group(1).strip()
        
        # Check for Navi Mumbai specifically
        if "navi mumbai" in query.lower():
            requirements["location"] = "Navi Mumbai"
        
        return requirements
    
    def estimate_material_requirements(self, requirements: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Estimate material requirements based on project specifications"""
        materials = []
        
        # Calculate based on standard construction norms
        if requirements.get("built_up_area"):
            area = requirements["built_up_area"]
            
            # Cement estimation (0.4 bags per square foot)
            cement_bags = area * 0.4
            cement_cubic_meters = cement_bags / 30  # Approximately 30 bags per cubic meter
            materials.append({
                "Material/Equipment": "Cement",
                "Quantity": f"{cement_cubic_meters:.0f} Cubic Meters",
                "Unit Cost (Rupees)": f"{cement_cubic_meters * 6000:.2f} Lakhs",
                "Notes": "Based on standard construction norms (0.4 bags per square foot)"
            })
            
            # Brick estimation (8 bricks per square foot)
            bricks = area * 8
            materials.append({
                "Material/Equipment": "Bricks",
                "Quantity": f"{bricks:.0f} Units",
                "Unit Cost (Rupees)": f"{bricks * 0.08:.2f} Lakhs",
                "Notes": "Based on standard construction norms (8 bricks per square foot)"
            })
        
        if requirements.get("power_capacity"):
            power = requirements["power_capacity"]
            
            # Medium Voltage Switchgear estimation
            switchgear_lineups = max(5, power / 2.5)  # Approximately 1 lineup per 2.5 MW
            materials.append({
                "Material/Equipment": "Medium Voltage Switchgear",
                "Quantity": f"{switchgear_lineups:.0f} LineUps",
                "Unit Cost (Rupees)": f"{switchgear_lineups * 0.2:.2f} Crores",
                "Notes": f"Based on power capacity of {power} MW"
            })
            
            # Transformers estimation
            transformer_units = max(3, power / 5)  # Approximately 1 transformer per 5 MW
            transformer_capacity = power / transformer_units  # Average capacity per transformer
            materials.append({
                "Material/Equipment": "Transformers",
                "Quantity": f"{transformer_units:.0f} Units ({transformer_capacity:.1f}MVA)",
                "Unit Cost (Rupees)": f"{transformer_units * 6.67:.2f} Crores",
                "Notes": f"Based on power capacity of {power} MW"
            })
            
            # Chillers/CRAHs/CRACs estimation
            cooling_units = max(10, power * 2)  # Approximately 2 units per MW
            materials.append({
                "Material/Equipment": "Chillers / CRAHs / CRACs",
                "Quantity": f"{cooling_units:.0f} Units",
                "Unit Cost (Rupees)": f"{cooling_units * 0.3:.2f} Crores",
                "Notes": f"Based on power capacity of {power} MW"
            })
        
        return materials
    
    def generate_response(self, query: str, context: List[Dict[str, Any]], 
                         requirements: Dict[str, Any] = None, 
                         material_estimates: List[Dict[str, Any]] = None) -> str:
        """Generate response using Ollama"""
        # Prepare context text
        context_text = ""
        for i, result in enumerate(context):
            context_text += f"Document {i+1}:\n"
            context_text += f"Title: {result['metadata']['title']}\n"
            context_text += f"URL: {result['metadata']['url']}\n"
            context_text += f"Details: {json.dumps(result['metadata']['details'], indent=2)}\n"
            context_text += f"Seller Info: {json.dumps(result['metadata']['seller_info'], indent=2)}\n"
            context_text += f"Company Info: {json.dumps(result['metadata']['company_info'], indent=2)}\n\n"
        
        # Add material estimates to context if available
        if material_estimates:
            context_text += "Material Estimates:\n"
            for material in material_estimates:
                context_text += f"{material['Material/Equipment']}: {material['Quantity']} at {material['Unit Cost (Rupees)']}\n"
        
        # Create prompt
        prompt = f"""
You are a product and vendor assistant for construction procurement.
Answer the query based on the provided context from the IndiaMART product database.

Context:
{context_text}

Query: {query}

Instructions:
- Only use information from the context. Do not invent details.
- If listing products, include the product name, key details (brand, availability, location), and vendor name.
- If the query asks for vendors, show company name, address, GST status, and rating if available.
- Provide URLs for all products/vendors mentioned.
- If the query involves filtering (e.g., fireproof, GST after 2017, rating > 4), apply it based on context.
- If the query includes project specifications (e.g., power capacity, area, budget), provide material estimates in a table format.
- Answer should be factual, concise, and helpful.

Answer:
"""
        
        # Generate response using Ollama
        try:
            response = ollama.chat(model='llama3:latest', messages=[
                {
                    'role': 'user',
                    'content': prompt,
                },
            ])
            return response['message']['content']
        except Exception as e:
            return f"Error generating response: {str(e)}"
    
    def format_material_table(self, materials: List[Dict[str, Any]]) -> str:
        """Format material estimates as a table"""
        if not materials:
            return ""
        
        # Create table header
        table = "| Material/Equipment | Quantity | Unit Cost (Rupees) |\n"
        table += "|-------------------|----------|-------------------|\n"
        
        # Add rows
        for material in materials:
            table += f"| {material['Material/Equipment']} | {material['Quantity']} | {material['Unit Cost (Rupees)']} |\n"
        
        return table
    
    def query(self, query: str, k: int = 10, apply_filters: bool = True) -> Dict[str, Any]:
        """Main query function"""
        # Extract project requirements if present
        requirements = self.extract_project_requirements(query)
        material_estimates = []
        
        # If project requirements are detected, generate material estimates
        if any([requirements["power_capacity"], requirements["built_up_area"], requirements["project_volume"]]):
            material_estimates = self.estimate_material_requirements(requirements)
        
        # Search for relevant documents
        search_results = self.search(query, k=k)
        
        # Apply additional filters if requested
        if apply_filters:
            filtered_results = self.filter_by_criteria(search_results, query)
        else:
            filtered_results = search_results
        
        # Generate response
        response = self.generate_response(query, filtered_results, requirements, material_estimates)
        
        # Extract sources
        sources = [result['metadata']['url'] for result in filtered_results if result['metadata']['url']]
        
        # Format the final response with material table if available
        final_response = response
        
        if material_estimates:
            table = self.format_material_table(material_estimates)
            final_response = f"{response}\n\nMaterial Estimates:\n{table}"
        
        return {
            'answer': final_response,
            'sources': sources,
            'num_results': len(filtered_results),
            'material_estimates': material_estimates
        }

# Example usage
if __name__ == "__main__":
    # Initialize RAG system
    rag = IndiaMART_RAG()
    
    # Load data and build index
    rag.load_and_process_json_files()
    rag.build_faiss_index()
    
    # Example queries including project specifications
    queries = [
        "25 MegaWatt, 2 Lacs SquareFoot Built Up Area, Project Volume of 1875 Cr in Rupees, Build in Navi Mumbai Area",
        "Which vendor supplies Medium Voltage Switchgear in Maharashtra?",
        "Show me insulation materials that are fire retardant and available in stock.",
        "Find cement suppliers in Navi Mumbai with high ratings",
        "Find suppliers with GST after 2017"
    ]
    
    for query in queries:
        print(f"\nQuery: {query}")
        result = rag.query(query)
        print(f"Answer: {result['answer']}")
        print(f"Sources: {result['sources'][:3]}")  # Show first 3 sources only
        print("-" * 80)