import json
import os
import re
from typing import List, Dict, Any
import pandas as pd
from sentence_transformers import SentenceTransformer
import faiss
import numpy as np
import requests
from datetime import datetime
import joblib
import warnings
import traceback
from scipy import sparse
import streamlit as st
from dotenv import load_dotenv
import time
import matplotlib.pyplot as plt
from dateutil.relativedelta import relativedelta
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.impute import SimpleImputer
warnings.filterwarnings('ignore')

# Load environment variables
load_dotenv()

# Load MATERIAL_CATALOG from data.json
if os.path.exists('data.json'):
    with open('data.json', 'r') as f:
        MATERIAL_CATALOG = json.load(f)
else:
    st.error("data.json not found. Using default catalog.")
    MATERIAL_CATALOG = {}  # Add default if needed

def extract_facility_type(query: str) -> str:
    query_lower = query.lower()
    for facility in MATERIAL_CATALOG:
        if facility.lower().replace(' ', '') in query_lower:
            return facility
    return "Workspace"

def get_catalog_materials(facility_type: str, category: str = None) -> List[str]:
    catalog = MATERIAL_CATALOG.get(facility_type, MATERIAL_CATALOG.get("Workspace", {}))
    if category:
        return catalog.get(category, [])
    return [mat for cats in catalog.values() for mat in cats]

class IndiaMART_RAG:
    def __init__(self, json_file: str = "filtered_products.json", embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"):
        self.json_file = json_file
        self.embedding_model_name = embedding_model
        self.embedding_model = SentenceTransformer(embedding_model)
        self.index = None
        self.documents = []
        self.metadata = []
        self.groq_api_key = os.getenv("GROQ_API_KEY")
        if not self.groq_api_key:
            raise ValueError("Groq API key missing. Set GROQ_API_KEY in .env file. Get a key from https://console.groq.com/keys")

    def _call_groq_api(self, prompt: str, max_tokens: int = 4096) -> str:
        time.sleep(2)
        
        if len(prompt) > 6000:
            if "Context:" in prompt:
                context_start = prompt.find("Context:")
                query_start = prompt.find("Query:")
                if query_start > 0:
                    base_prompt = prompt[query_start:]
                    context_part = prompt[context_start:query_start]
                    if len(context_part) > 3000:
                        context_part = context_part[:3000] + "\n... (context truncated)"
                    prompt = "Context:\n" + context_part + "\n" + base_prompt
            else:
                prompt = prompt[:6000] + "\n... (truncated to fit token limit)"
            st.warning(f"Prompt truncated to ~1500 tokens to avoid context length issues.")

        try:
            headers = {
                "Authorization": f"Bearer {self.groq_api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
                "temperature": 0.7
            }
            response = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=60)
            response.raise_for_status()
            data = response.json()
            if 'choices' in data and len(data['choices']) > 0:
                return data['choices'][0]['message']['content']
            else:
                st.error("Invalid API response format.")
                return "Error: Invalid API response."
        except requests.exceptions.HTTPError as e:
            error_msg = f"API HTTP Error: {str(e)} - {e.response.text}"
            if e.response.status_code == 400:
                error_msg += f" - Possible context length issue. Prompt length: {len(prompt)} chars."
                return self._call_groq_api(prompt[:4000], max_tokens=2048)
            elif e.response.status_code == 401:
                error_msg += " - Invalid API key."
            elif e.response.status_code == 429:
                error_msg += " - Rate limit exceeded. Retrying after delay..."
                time.sleep(15)
                return self._call_groq_api(prompt, max_tokens)
            st.error(error_msg)
            return f"Error: {error_msg}"
        except Exception as e:
            st.error(f"General Error: {str(e)}")
            return f"Error: {str(e)}"

    def generate_response(self, query: str, context: List[Dict[str, Any]], requirements: Dict[str, Any] = None, material_estimates: List[Dict[str, Any]] = None, catalog_materials: List[str] = None) -> str:
        context_text = ""
        for i, result in enumerate(context[:3]):
            metadata = result['metadata']
            doc_str = f"Title: {metadata.get('title', 'N/A')}\n"
            if metadata.get('url'):
                doc_str += f"URL: {metadata['url']}\n"
            
            price = metadata.get('price', '')
            price_unit = metadata.get('price_unit', '')
            if price:
                doc_str += f"Price: {price} {price_unit}\n"
            
            details = metadata.get('details', {})
            if details and isinstance(details, dict):
                important_keys = ['usage/application', 'brand', 'availability', 'location', 'vendor', 'company', 'model', 'capacity', 'warranty']
                for key in important_keys:
                    if key in details and details[key]:
                        value = str(details[key]).strip()
                        if value and value != '-':
                            doc_str += f"{key.replace('/', ' ').title()}: {value}\n"
            
            company_info = metadata.get('company_info', {})
            if company_info.get('gst'):
                doc_str += f"GST: {company_info['gst']}\n"
            if metadata.get('reviews'):
                for review in metadata['reviews']:
                    if review.get('type') == 'overall_rating':
                        doc_str += f"Rating: {review.get('value', 'N/A')}\n"
                        break
            
            context_text += f"Document {i+1}:\n{doc_str[:500]}\n\n"

        if material_estimates:
            materials_text = "Materials:\n" + "\n".join([f"- {m['Material/Equipment']} ({m['Quantity']})" for m in material_estimates[:3]])
            context_text += materials_text + "\n\n"

        if catalog_materials:
            catalog_text = "Catalog Materials:\n" + "\n".join([f"- {mat}" for mat in catalog_materials[:5]])
            context_text += catalog_text + "\n\n"

        prompt = f"""
Assistant for construction procurement. Use ONLY context from IndiaMART JSON database (real product details) and Catalog Materials.
Context:
{context_text}
Query: {query}
Instructions:
- Prioritize real JSON data (titles, prices, details, sellers, companies, ratings).
- Use Catalog Materials to suggest specific materials (e.g., for Cement, use 'Reinforced Concrete (Foundation, Slabs)') and match to JSON products.
- Be comprehensive but concise. Include prices, availability, GST, ratings where available.
- Output in structured format:
Products (list 2-3 most relevant, using catalog for specificity):
1. Name: [name from title or catalog]
   Brand/Model: [brand/model from details]
   Price: [price from JSON]
   Availability: [from details]
   Location: [from seller/company address]
   Vendor: [from seller_info/company_info]
   URL: [url]
   Catalog Match: [specific catalog material if applicable]

Vendors (list 2-3):
1. Company Name: [from company_info]
   Address: [full_address from seller/company]
   GST: [gst from company_info] (mention if after 2017)
   Rating: [overall_rating from reviews]
   Contact: [if available]

- If info missing, say "Not specified in JSON context".
- No fabrication—stick to real JSON data and catalog.
Answer:
"""
        return self._call_groq_api(prompt, max_tokens=2048)

    def load_and_process_json_files(self):
        st.write(f"Loading JSON file: {self.json_file}...")
       
        if not os.path.exists(self.json_file):
            raise FileNotFoundError(f"{self.json_file} not found in {os.getcwd()}. Ensure it's in the current directory.")
       
        try:
            with open(self.json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
               
            if isinstance(data, list):
                for item in data:
                    self._process_item(item)
            else:
                self._process_item(data)
               
            st.write(f"Loaded {len(self.documents)} documents from {self.json_file}")
        except json.JSONDecodeError as e:
            st.error(f"JSON decode error in {self.json_file}: {str(e)}")
        except Exception as e:
            st.error(f"Error loading {self.json_file}: {str(e)}")
   
    def _process_item(self, item: Dict[str, Any]):
        text_parts = []
       
        title = item.get('title', '')
        if title:
            text_parts.append(f"Title: {title}")
       
        price = item.get('price', '')
        price_unit = item.get('price_unit', '')
        if price:
            text_parts.append(f"Price: {price} {price_unit}")
       
        details = item.get('details', {})
        if details and isinstance(details, dict):
            for key, value in details.items():
                if value and str(value).strip() != '-':
                    text_parts.append(f"{key}: {value}")
       
        description = item.get('description', '')
        if description:
            text_parts.append(f"Description: {description}")
       
        seller_info = item.get('seller_info', {})
        if seller_info and isinstance(seller_info, dict):
            for key, value in seller_info.items():
                if key != 'error' and value and value != 'Seller information not available':
                    text_parts.append(f"Seller {key}: {value}")
       
        company_info = item.get('company_info', {})
        if company_info and isinstance(company_info, dict):
            for key, value in company_info.items():
                if value:
                    text_parts.append(f"Company {key}: {value}")
       
        reviews = item.get('reviews', [])
        if reviews:
            for review in reviews:
                if review.get('type') == 'overall_rating':
                    text_parts.append(f"Overall Rating: {review.get('value', '')}")
                    break
       
        text = " ".join(text_parts)
       
        if text.strip():
            self.documents.append(text)
            self.metadata.append({
                'url': item.get('url', ''),
                'title': title,
                'price': price,
                'price_unit': price_unit,
                'description': description,
                'details': details,
                'seller_info': seller_info,
                'company_info': company_info,
                'reviews': reviews
            })
   
    def build_faiss_index(self):
        if not self.documents:
            st.error("No documents to index! Check filtered_products.json.")
            return
           
        st.write("Building FAISS index...")
       
        embeddings = self.embedding_model.encode(self.documents, show_progress_bar=True)
       
        dimension = embeddings.shape[1]
        self.index = faiss.IndexFlatL2(dimension)
        self.index.add(np.array(embeddings).astype('float32'))
       
        st.write("FAISS index built successfully")
   
    def search(self, query: str, k: int = 5) -> List[Dict[str, Any]]:
        if self.index is None or len(self.documents) == 0:
            raise ValueError("Index not built or no documents loaded")
       
        k = min(k, len(self.documents))
       
        query_embedding = self.embedding_model.encode([query])
       
        distances, indices = self.index.search(np.array(query_embedding).astype('float32'), k)
       
        results = []
        for i, idx in enumerate(indices[0]):
            if idx < len(self.metadata):
                results.append({
                    'document': self.documents[idx],
                    'metadata': self.metadata[idx],
                    'distance': float(distances[0][i])
                })
       
        return results
   
    def filter_by_criteria(self, results: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
        filtered_results = []
       
        for result in results:
            metadata = result['metadata']
            company_info = metadata.get('company_info', {})
            seller_info = metadata.get('seller_info', {})
            details = metadata.get('details', {})
           
            if "in " in query.lower() or "navi mumbai" in query.lower():
                location_match = re.search(r'in\s+([\w\s]+)$', query.lower())
                location = "navi mumbai" if "navi mumbai" in query.lower() else None
                if location_match and not location:
                    location = location_match.group(1).strip()
               
                if location:
                    address = (str(company_info.get('full_address', '')) + " " + 
                               str(seller_info.get('full_address', '')) + " " + 
                               str(details.get('location', ''))).lower()
                    if location.lower() not in address:
                        continue
           
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
           
            if "high rating" in query.lower() or "rating" in query.lower():
                reviews = metadata.get('reviews', [])
                overall_rating = None
                for review in reviews:
                    if review.get('type') == 'overall_rating':
                        try:
                            overall_rating = float(str(review.get('value', 0)).strip())
                            break
                        except (ValueError, TypeError):
                            pass
               
                if overall_rating is None or overall_rating < 4.0:
                    continue
           
            if "available in stock" in query.lower() or "in stock" in query.lower():
                availability = str(details.get('availability', '')).lower()
                if 'in stock' not in availability:
                    continue
           
            if "fire retardant" in query.lower() or "fireproof" in query.lower():
                details_text = str(details).lower() + " " + str(metadata.get('description', '')).lower()
                if 'fire retardant' not in details_text and 'fireproof' not in details_text:
                    continue
           
            filtered_results.append(result)
       
        return filtered_results
   
    def extract_project_requirements(self, query: str) -> Dict[str, Any]:
        requirements = {
            "power_capacity": None,
            "built_up_area": None,
            "project_volume": None,
            "location": None,
            "facility_type": extract_facility_type(query),
            "materials": {}
        }
       
        power_match = re.search(r'(\d+)\s*Mega?Watt', query, re.IGNORECASE)
        if power_match:
            requirements["power_capacity"] = float(power_match.group(1))
       
        area_match = re.search(r'(\d+)\s*Lacs?\s*SquareFoot', query, re.IGNORECASE)
        if area_match:
            requirements["built_up_area"] = float(area_match.group(1)) * 100000
       
        volume_match = re.search(r'(\d+)\s*Cr\s*(in\s*Rupees)?', query, re.IGNORECASE)
        if volume_match:
            requirements["project_volume"] = float(volume_match.group(1)) * 10000000
       
        location_match = re.search(r'in\s+([\w\s]+)$', query, re.IGNORECASE)
        if location_match:
            requirements["location"] = location_match.group(1).strip()
       
        if "navi mumbai" in query.lower():
            requirements["location"] = "Navi Mumbai"
       
        return requirements
   
    def estimate_material_requirements(self, requirements: Dict[str, Any]) -> List[Dict[str, Any]]:
        materials = []
        facility_type = requirements.get("facility_type", "Workspace")
        catalog = MATERIAL_CATALOG.get(facility_type, MATERIAL_CATALOG.get("Workspace", {}))
        
        if requirements.get("built_up_area"):
            area = requirements["built_up_area"]
            
            # Use catalog for Cement
            cement_specific = next((mat for cat in catalog.values() for mat in cat if 'concrete' in mat.lower()), "Reinforced Concrete (Foundation, Slabs)")
            cement_bags = area * 0.4
            cement_cubic_meters = cement_bags / 30
            materials.append({
                "Material/Equipment": f"Cement - {cement_specific}",
                "Quantity": f"{cement_cubic_meters:.0f} Cubic Meters",
                "Unit Cost (Rupees)": f"{(cement_cubic_meters * 6000 / 100000):.2f} Crores",
                "Notes": "Based on standard construction norms (0.4 bags per square foot)",
                "catalog_source": cement_specific
            })
            
            # Use catalog for Bricks
            bricks_specific = next((mat for cat in catalog.values() for mat in cat if 'masonry' in mat.lower() or 'cladding' in mat.lower()), "Concrete Masonry Unit (CMU)")
            bricks = area * 8
            materials.append({
                "Material/Equipment": f"Bricks - {bricks_specific}",
                "Quantity": f"{bricks:.0f} Units",
                "Unit Cost (Rupees)": f"{(bricks * 0.08 / 100000):.2f} Crores",
                "Notes": "Based on standard construction norms (8 bricks per square foot)",
                "catalog_source": bricks_specific
            })
        
        if requirements.get("power_capacity"):
            power = requirements["power_capacity"]
            
            # Use catalog for Switchgear
            switchgear_specific = next((mat for cat in catalog.values() for mat in cat if 'electrical' in mat.lower() or 'power' in mat.lower()), "Electrical Infrastructure")
            switchgear_lineups = max(5, power / 2.5)
            materials.append({
                "Material/Equipment": f"Medium Voltage Switchgear - {switchgear_specific}",
                "Quantity": f"{switchgear_lineups:.0f} LineUps",
                "Unit Cost (Rupees)": f"{switchgear_lineups * 0.2:.2f} Crores",
                "Notes": f"Based on power capacity of {power} MW",
                "catalog_source": switchgear_specific
            })
            
            # Use catalog for Transformers
            transformer_specific = next((mat for cat in catalog.values() for mat in cat if 'power' in mat.lower() or 'emergency' in mat.lower()), "Emergency Power Systems")
            transformer_units = max(3, power / 5)
            transformer_capacity = power / transformer_units
            materials.append({
                "Material/Equipment": f"Transformers - {transformer_specific}",
                "Quantity": f"{transformer_units:.0f} Units ({transformer_capacity:.1f}MVA)",
                "Unit Cost (Rupees)": f"{transformer_units * 6.67:.2f} Crores",
                "Notes": f"Based on power capacity of {power} MW",
                "catalog_source": transformer_specific
            })
            
            # Use catalog for Chillers
            chiller_specific = next((mat for cat in catalog.values() for mat in cat if 'hvac' in mat.lower() or 'cooling' in mat.lower()), "HVAC Systems")
            cooling_units = max(10, power * 2)
            materials.append({
                "Material/Equipment": f"Chillers / CRAHs / CRACs - {chiller_specific}",
                "Quantity": f"{cooling_units:.0f} Units",
                "Unit Cost (Rupees)": f"{cooling_units * 0.3:.2f} Crores",
                "Notes": f"Based on power capacity of {power} MW",
                "catalog_source": chiller_specific
            })
        
        return materials
   
    def format_material_table(self, materials: List[Dict[str, Any]]) -> str:
        if not materials:
            return ""
        
        table = "| Material/Equipment | Quantity | Unit | Cost (Rupees) | Product Details | Catalog Source |\n"
        table += "|---|---|---|---|---|---|\n"
        
        for material in materials:
            quantity_str = material['Quantity']
            parts = quantity_str.split(' ', 1)
            if len(parts) == 2:
                quantity = parts[0]
                unit = parts[1]
            else:
                quantity = quantity_str
                unit = "-"
            
            cost = material.get('Unit Cost (Rupees)', material.get('Cost (Rupees)', 'N/A'))
            product_details = material.get('product_details', 'No matching product found')
            catalog_source = material.get('catalog_source', 'N/A')
            
            table += f"| {material['Material/Equipment']} | {quantity} | {unit} | {cost} | {product_details} | {catalog_source} |\n"
        
        return table

    def query(self, query: str, k: int = 10, apply_filters: bool = True) -> Dict[str, Any]:
        requirements = self.extract_project_requirements(query)
        material_estimates = []
       
        if any([requirements["power_capacity"], requirements["built_up_area"], requirements["project_volume"]]):
            material_estimates = self.estimate_material_requirements(requirements)
       
        search_results = self.search(query, k=k)
       
        if apply_filters:
            filtered_results = self.filter_by_criteria(search_results, query)
        else:
            filtered_results = search_results

        facility_type = requirements.get("facility_type", "Workspace")
        catalog_materials = get_catalog_materials(facility_type)
       
        response = self.generate_response(query, filtered_results, requirements, material_estimates, catalog_materials)
       
        sources = [result['metadata']['url'] for result in filtered_results if result['metadata']['url']]
       
        final_response = response
        if material_estimates:
            table = self.format_material_table(material_estimates)
            final_response += f"\n\n{table}"
       
        return {
            'answer': final_response,
            'sources': sources,
            'num_results': len(filtered_results),
            'material_estimates': material_estimates,
            'requirements': requirements
        }

def generate_missing_ml_files():
    """Generate missing ML files from clean_train_full.csv if not present"""
    if os.path.exists('tfidf_vectorizer.pkl') and os.path.exists('numeric_imputer.pkl') and os.path.exists('date_imputer.pkl') and os.path.exists('categorical_mapping.pkl'):
        return
    
    try:
        st.info("Generating missing ML files from clean_train_full.csv...")
        df = pd.read_csv('clean_train_full.csv')
        
        # TF-IDF matching ipynb
        df['ItemDescription_clean'] = df['ItemDescription'].fillna('').astype(str).str.lower().str.replace(r'[^a-zA-Z0-9\s]', '', regex=True)
        tfidf = TfidfVectorizer(max_features=30000, ngram_range=(1,2), min_df=2, stop_words='english', dtype=np.float32)
        tfidf.fit(df['ItemDescription_clean'])
        joblib.dump(tfidf, 'tfidf_vectorizer.pkl')
        
        # Numeric imputer
        numeric_cols = ['ExtendedQuantity', 'UnitPrice', 'ExtendedPrice', 'invoiceTotal']
        df_numeric = df[numeric_cols].fillna(0)
        num_imputer = SimpleImputer(strategy='mean')
        num_imputer.fit(df_numeric)
        joblib.dump(num_imputer, 'numeric_imputer.pkl')
        
        # Date imputer (dummy)
        date_features = ['construction_duration_days', 'invoice_year', 'invoice_month', 'invoice_day', 'invoice_dayofweek', 'invoice_quarter']
        date_df = pd.DataFrame(np.random.rand(1, len(date_features)), columns=date_features)
        date_imputer = SimpleImputer(strategy='mean')
        date_imputer.fit(date_df)
        joblib.dump(date_imputer, 'date_imputer.pkl')
        
        # Categorical mapping
        cat_cols = ['PROJECT_CITY', 'STATE', 'PROJECT_COUNTRY', 'CORE_MARKET', 'PROJECT_TYPE', 'UOM']
        categorical_mapping = {}
        for col in cat_cols:
            if col in df.columns:
                top_cats = df[col].fillna('missing').value_counts().head(10).index.tolist()
                categorical_mapping[col] = top_cats
        joblib.dump(categorical_mapping, 'categorical_mapping.pkl')
        
        # Date and numeric feature names
        joblib.dump(date_features, 'date_feature_names.pkl')
        joblib.dump(numeric_cols, 'numeric_feature_names.pkl')
        
        st.success("ML files generated!")
    except Exception as e:
        st.error(f"Failed to generate ML files: {str(e)}. Using fallback for ML.")

def check_files():
    files = [
        'deterministic_mapping.pkl', 'lgb_regressor.pkl', 'lgb_classifier.pkl',
        'label_encoder.pkl', 'tfidf_vectorizer.pkl', 'numeric_imputer.pkl',
        'date_imputer.pkl', 'categorical_mapping.pkl', 'date_feature_names.pkl',
        'numeric_feature_names.pkl'
    ]
   
    available = []
    missing = []
   
    for file in files:
        if os.path.exists(file):
            available.append(file)
        else:
            missing.append(file)
   
    return available, missing

def clean_numeric_value(value, clip_negative=True, replace_zero_epsilon=False):
    if isinstance(value, str):
        value = (value.replace(',', '')
                  .replace('$','')
                  .replace(' ','')
                  .replace(' ', ''))
        try:
            value = float(value)
        except:
            value = np.nan
   
    if clip_negative and value is not None and value < 0:
        value = 0
    if replace_zero_epsilon and value is not None and value <= 0:
        value = 0.01
   
    return value

def clean_text_value(text):
    if pd.isna(text) or text is None:
        return "missing"
   
    text = str(text).strip().lower()
    text = text.replace('\n', ' ').replace('\r', ' ')
    text = ''.join([c if c.isalnum() or c.isspace() else ' ' for c in text])
    text = ' '.join(text.split())
   
    return text

def prepare_date_features(input_data, date_feature_names):
    date_features = {}
   
    if 'CONSTRUCTION_START_DATE' in input_data and 'SUBSTANTIAL_COMPLETION_DATE' in input_data:
        try:
            start_str = input_data.get('CONSTRUCTION_START_DATE', '')
            end_str = input_data.get('SUBSTANTIAL_COMPLETION_DATE', '')
            if start_str and end_str:
                start_date = pd.to_datetime(start_str, errors='coerce')
                end_date = pd.to_datetime(end_str, errors='coerce')
                if not pd.isna(start_date) and not pd.isna(end_date):
                    duration = (end_date - start_date).days
                    date_features['construction_duration_days'] = duration
        except:
            pass
   
    if 'invoiceDate' in input_data:
        try:
            invoice_str = input_data.get('invoiceDate', '')
            if invoice_str:
                invoice_date = pd.to_datetime(invoice_str, errors='coerce')
                if not pd.isna(invoice_date):
                    date_features['invoice_year'] = invoice_date.year
                    date_features['invoice_month'] = invoice_date.month
                    date_features['invoice_day'] = invoice_date.day
                    date_features['invoice_dayofweek'] = invoice_date.dayofweek
                    date_features['invoice_quarter'] = invoice_date.quarter
        except:
            pass
   
    date_df = pd.DataFrame(columns=date_feature_names)
   
    for feature in date_feature_names:
        if feature in date_features:
            date_df.at[0, feature] = date_features[feature]
        else:
            date_df.at[0, feature] = np.nan
   
    return date_df

def prepare_features(input_data, tfidf_vectorizer, numeric_imputer, date_imputer, categorical_mapping, date_feature_names):
    cleaned_desc = clean_text_value(input_data.get('ItemDescription', ''))
    X_text = tfidf_vectorizer.transform([cleaned_desc])
   
    numeric_features = ['ExtendedQuantity', 'UnitPrice', 'ExtendedPrice', 'invoiceTotal']
    numeric_values = []
   
    for feat in numeric_features:
        value = input_data.get(feat, 0)
        cleaned_value = clean_numeric_value(value, replace_zero_epsilon=(feat in ['UnitPrice', 'ExtendedPrice']))
        if cleaned_value is None or np.isnan(cleaned_value):
            cleaned_value = 0
        numeric_values.append(cleaned_value)
   
    numeric_values = [np.log1p(x) if x >= 0 else 0 for x in numeric_values]
    X_numeric = numeric_imputer.transform([numeric_values])
   
    date_df = prepare_date_features(input_data, date_feature_names)
    X_date = date_imputer.transform(date_df)
   
    cat_cols = ['PROJECT_CITY', 'STATE', 'PROJECT_COUNTRY', 'CORE_MARKET', 'PROJECT_TYPE', 'UOM']
    cat_features = []
   
    for c in cat_cols:
        value = str(input_data.get(c, 'missing')).lower().strip()
        if c in categorical_mapping:
            top_categories = categorical_mapping[c]
            if value in top_categories:
                cat_features.extend([1 if value == cat else 0 for cat in top_categories])
                cat_features.append(0)
            else:
                cat_features.extend([0] * len(top_categories))
                cat_features.append(1)
        else:
            cat_features.extend([0] * 5)
            cat_features.append(1)
   
    X_categorical = np.array([cat_features])
   
    X_combined = sparse.hstack([
        X_text,
        sparse.csr_matrix(X_numeric),
        sparse.csr_matrix(X_date),
        sparse.csr_matrix(X_categorical)
    ]).tocsr()
   
    return X_combined

def run_ml_prediction(input_data: Dict[str, Any]) -> Dict[str, Any]:
    try:
        available_files, missing_files = check_files()
       
        if 'tfidf_vectorizer.pkl' not in available_files:
            return {'error': 'TFIDF vectorizer missing - run generate_missing_ml_files()'}
       
        tfidf_vectorizer = joblib.load('tfidf_vectorizer.pkl')
        numeric_imputer = joblib.load('numeric_imputer.pkl') if 'numeric_imputer.pkl' in available_files else None
        date_imputer = joblib.load('date_imputer.pkl') if 'date_imputer.pkl' in available_files else None
        categorical_mapping = joblib.load('categorical_mapping.pkl') if 'categorical_mapping.pkl' in available_files else {}
       
        det_items = joblib.load('deterministic_mapping.pkl') if 'deterministic_mapping.pkl' in available_files else pd.Series()
       
        date_feature_names = joblib.load('date_feature_names.pkl') if 'date_feature_names.pkl' in available_files else [
            'construction_duration_days', 'invoice_year', 'invoice_month',
            'invoice_day', 'invoice_dayofweek', 'invoice_quarter'
        ]
       
        regression_available = 'lgb_regressor.pkl' in available_files
        if regression_available:
            lgb_regressor = joblib.load('lgb_regressor.pkl')
       
        classification_available = all(f in available_files for f in ['lgb_classifier.pkl', 'label_encoder.pkl'])
        if classification_available:
            lgb_classifier = joblib.load('lgb_classifier.pkl')
            label_encoder = joblib.load('label_encoder.pkl')
       
        if not numeric_imputer or not date_imputer:
            return {'error': 'Missing numeric_imputer.pkl or date_imputer.pkl'}
        
        X_features = prepare_features(input_data, tfidf_vectorizer, numeric_imputer,
                                      date_imputer, categorical_mapping, date_feature_names)
       
        cleaned_desc = clean_text_value(input_data.get('ItemDescription', ''))
       
        if cleaned_desc in det_items.index:
            master_item_no = det_items[cleaned_desc]
            prediction_method = "deterministic"
        elif classification_available:
            X_dense = X_features.toarray()
            # Fix feature mismatch by padding if necessary
            expected_features = getattr(lgb_classifier, 'n_features_in_', 0)
            if X_dense.shape[1] < expected_features:
                padding = np.zeros((X_dense.shape[0], expected_features - X_dense.shape[1]))
                X_dense = np.hstack((X_dense, padding))
            elif X_dense.shape[1] > expected_features:
                X_dense = X_dense[:, :expected_features]
            pred_encoded = lgb_classifier.predict(X_dense)
            pred_processed = label_encoder.inverse_transform(pred_encoded)
            master_item_no = pred_processed[0]
            prediction_method = "classification_model"
        else:
            master_item_no = "unknown"
            prediction_method = "no_model"
       
        if regression_available:
            X_dense = X_features.toarray()
            # Fix feature mismatch for regressor
            expected_features_reg = getattr(lgb_regressor, 'n_features_in_', 0)
            if X_dense.shape[1] < expected_features_reg:
                padding = np.zeros((X_dense.shape[0], expected_features_reg - X_dense.shape[1]))
                X_dense = np.hstack((X_dense, padding))
            elif X_dense.shape[1] > expected_features_reg:
                X_dense = X_dense[:, :expected_features_reg]
            qty_shipped = lgb_regressor.predict(X_dense)[0]
            qty_shipped = max(1, int(qty_shipped))
        else:
            extended_qty = clean_numeric_value(input_data.get('ExtendedQuantity', 1))
            qty_shipped = max(1, int(extended_qty)) if extended_qty else 1
       
        return {
            'master_item_no': master_item_no,
            'qty_shipped': qty_shipped,
            'prediction_method': prediction_method
        }
       
    except Exception as e:
        return {'error': str(e)}

def generate_ml_input_from_rag(rag: IndiaMART_RAG, query: str, material: str, estimated_qty: float, catalog_source: str = None) -> tuple[Dict[str, Any], Dict[str, Any]]:
    requirements = rag.extract_project_requirements(query)
    location = requirements.get("location", "Navi Mumbai")
    state = "Maharashtra" if "navi mumbai" in location.lower() else "Maharashtra"
    
    # Refine search with catalog
    search_query = f"{material} {catalog_source or ''} suppliers {location}" if catalog_source else f"{material} suppliers {location}"
    search_results = rag.search(search_query, k=1)
    
    if not search_results:
        search_query = f"{material} {catalog_source or ''} suppliers"
        search_results = rag.search(search_query, k=1)
    
    real_product_data = {
        "ItemDescription": f"{material} - {catalog_source or 'for construction project'}",
        "UnitPrice": 1000.0,
        "price_unit": "Units",
        "product_details": f"Catalog: {catalog_source or 'No catalog match'} - No matching product found"
    }
    
    if search_results:
        metadata = search_results[0]['metadata']
        title = metadata.get('title', material)
        description = metadata.get('description', '')
        price = metadata.get('price', '')
        price_unit = metadata.get('price_unit', 'Units')
        details = metadata.get('details', {})
        
        real_desc = f"{title} - {description[:200]}... Details: {', '.join([f'{k}:{v}' for k, v in list(details.items())[:3]])} (Catalog: {catalog_source or 'N/A'})"
        
        try:
            real_price = float(price) if price else 1000.0
        except (ValueError, TypeError):
            real_price = 1000.0
        
        real_product_data = {
            "ItemDescription": real_desc,
            "UnitPrice": real_price,
            "ExtendedPrice": real_price * estimated_qty,
            "price_unit": price_unit,
            "product_details": f"{title} (Price: {price} {price_unit}, Catalog: {catalog_source or 'N/A'}, URL: {metadata.get('url', 'N/A')})"
        }
    
    input_data = {
        "ItemDescription": real_product_data["ItemDescription"],
        "ExtendedQuantity": estimated_qty,
        "UnitPrice": real_product_data["UnitPrice"],
        "ExtendedPrice": real_product_data["ExtendedPrice"],
        "invoiceTotal": real_product_data["ExtendedPrice"] * 10,
        "CONSTRUCTION_START_DATE": "2026-01-01",
        "SUBSTANTIAL_COMPLETION_DATE": "2026-12-31",
        "invoiceDate": "2025-09-14",
        "PROJECT_CITY": location,
        "STATE": state,
        "PROJECT_COUNTRY": "India",
        "CORE_MARKET": "Construction",
        "PROJECT_TYPE": "Commercial",
        "UOM": real_product_data["price_unit"]
    }
    
    st.info(f"✅ Real ML input for {material}: {real_product_data['product_details']}")
    return input_data, real_product_data

def generate_timeline(materials: List[Dict], query: str, groq_api_key: str) -> str:
    material_list = "\n".join([f"- {m['Material/Equipment']}: {m['Quantity']}" for m in materials[:3]])
    prompt = f"""
Date: October 05, 2025
Project: {query[:200]}
Materials (with catalog specifics):
{material_list}

Generate a COMPLETE procurement timeline in this exact structured Markdown format. IMPORTANT: Generate the ENTIRE timeline without truncation. Use industry-standard lead times for catalog materials.

Output of Procurement Timeline:

1. Electrical Equipment
| Item | Lead Time | Order By | Delivery Window | Notes |
|------|-----------|----------|-----------------|-------|
| Transformers | 50 weeks | Feb 1, 2026 | Dec 2026 | Potential delays |
| Switchgear | 40 weeks | Mar 1, 2026 | Nov 2026 | Custom fabrication |
| Cables | 20 weeks | May 1, 2026 | Sep 2026 | Bulk order |

2. Mechanical Equipment  
| Item | Lead Time | Order By | Delivery Window | Notes |
|------|-----------|----------|-----------------|-------|
| Cement | In-stock | Immediate | Immediate | Standard material |
| Bricks | 4 weeks | Oct 1, 2025 | Oct 2025 | Local supplier |
| Chillers | 30 weeks | Apr 1, 2026 | Nov 2026 | Custom size |

3. Critical Path Schedule
| Phase | Duration | Start Date | End Date | Key Milestones |
|-------|----------|------------|----------|----------------|
| Design | 8 weeks | Jan 2026 | Mar 2026 | Finalize specs |
| Procurement | 45 weeks | Mar 2026 | Dec 2026 | All materials |
| Installation | 20 weeks | Jan 2027 | Jun 2027 | Commissioning |

Ensure ALL tables are complete and continue generating until the entire timeline is covered.
"""
    try:
        headers = {
            "Authorization": f"Bearer {groq_api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 4096,
            "temperature": 0.3
        }
        response = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        data = response.json()
        if 'choices' in data and len(data['choices']) > 0:
            content = data['choices'][0]['message']['content']
            if "..." in content or "truncated" in content:
                st.warning("Timeline may be incomplete. Consider regenerating.")
            return content
        st.error("Invalid API response for timeline.")
        return "Error: Invalid API response."
    except Exception as e:
        st.error(f"Timeline generation error: {str(e)}")
        return f"Error: {str(e)}"

def generate_schedule(materials: List[Dict], query: str, groq_api_key: str) -> str:
    material_list = "\n".join([f"- {m['Material/Equipment']}: {m['Quantity']}" for m in materials[:3]])
    prompt = f"""
Date: October 05, 2025
Project: {query[:200]}
Materials (with catalog specifics):
{material_list}

Generate a COMPLETE construction schedule in this exact structured Markdown format. IMPORTANT: Generate the ENTIRE schedule without truncation. Include all major phases.

Output of Integrated with Construction Project Schedule:

WBS Level 2: 1. Design & Engineering
| ID | Task | Duration | Start | Finish | Notes |
|----|------|----------|-------|--------|-------|
| 1.1 | Conceptual Design | 30 days | 01-Jan-2026 | 30-Jan-2026 | 30% Design |
| 1.2 | Detailed Design | 45 days | 01-Feb-2026 | 17-Mar-2026 | 100% Design |
| 1.3 | Permits Approval | 60 days | 01-Mar-2026 | 30-Apr-2026 | Regulatory |

WBS Level 2: 2. Site Preparation
| ID | Task | Duration | Start | Finish | Notes |
|----|------|----------|-------|--------|-------|
| 2.1 | Land Clearing | 15 days | 01-May-2026 | 15-May-2026 | Earthwork |
| 2.2 | Foundation Work | 45 days | 16-May-2026 | 30-Jun-2026 | Excavation |

WBS Level 2: 3. Structural Work
| ID | Task | Duration | Start | Finish | Notes |
|----|------|----------|-------|--------|-------|
| 3.1 | Steel Erection | 60 days | 01-Jul-2026 | 29-Aug-2026 | Framework |
| 3.2 | Concrete Work | 75 days | 01-Aug-2026 | 14-Oct-2026 | Slabs & walls |

WBS Level 2: 4. Mechanical & Electrical
| ID | Task | Duration | Start | Finish | Notes |
|----|------|----------|-------|--------|-------|
| 4.1 | Transformer Installation | 15 days | 01-Dec-2026 | 15-Dec-2026 | HV equipment |
| 4.2 | Switchgear Installation | 20 days | 16-Dec-2026 | 04-Jan-2027 | MV equipment |
| 4.3 | Cable Laying | 30 days | 05-Jan-2027 | 03-Feb-2027 | Power distribution |

WBS Level 2: 5. Finishing & Commissioning
| ID | Task | Duration | Start | Finish | Notes |
|----|------|----------|-------|--------|-------|
| 5.1 | Interior Work | 90 days | 01-Mar-2027 | 29-May-2027 | Final touches |
| 5.2 | Testing | 30 days | 01-Jun-2027 | 30-Jun-2027 | Systems check |
| 5.3 | Handover | 15 days | 01-Jul-2027 | 15-Jul-2027 | Project completion |

Ensure ALL WBS levels are complete and continue generating until the entire project schedule is covered.
"""
    try:
        headers = {
            "Authorization": f"Bearer {groq_api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 4096,
            "temperature": 0.3
        }
        response = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        data = response.json()
        if 'choices' in data and len(data['choices']) > 0:
            content = data['choices'][0]['message']['content']
            if "..." in content or "truncated" in content:
                st.warning("Schedule may be incomplete. Consider regenerating.")
            return content
        st.error("Invalid API response for schedule.")
        return "Error: Invalid API response."
    except Exception as e:
        st.error(f"Schedule generation error: {str(e)}")
        return f"Error: {str(e)}"

def generate_complete_plan_in_chunks(materials: List[Dict], query: str, groq_api_key: str) -> Dict[str, str]:
    with st.spinner("Generating detailed timeline..."):
        timeline = generate_timeline(materials, query, groq_api_key)
        time.sleep(2)
    
    with st.spinner("Generating comprehensive schedule..."):
        schedule = generate_schedule(materials, query, groq_api_key)
        time.sleep(2)
    
    return {
        'timeline': timeline,
        'schedule': schedule
    }

def extract_vendor_details(answer: str) -> str:
    vendor_match = re.search(r'Vendors:\s*1\.\s*Company Name: (.*?)(?:\s*Address: (.*?)(?:\s*GST: (.*?)(?:\s*Rating: (.*?)(?:\s*Price: (.*))?)?)?)?', answer, re.DOTALL | re.IGNORECASE)
    if vendor_match:
        company = vendor_match.group(1).strip()
        address = vendor_match.group(2).strip() if vendor_match.group(2) else "N/A"
        gst = vendor_match.group(3).strip() if vendor_match.group(3) else "N/A"
        rating = vendor_match.group(4).strip() if vendor_match.group(4) else "N/A"
        price_info = vendor_match.group(5).strip() if vendor_match.group(5) else "N/A"
        return f"Company: {company}, Address: {address}, GST: {gst}, Rating: {rating}, Price Info: {price_info}"
    return "Unknown Vendor"

def plot_gantt_chart(schedule_text: str):
    tasks = []
    lines = schedule_text.split('\n')
    current_section = ""
    for line in lines:
        if line.startswith('WBS Level 2:'):
            current_section = line
        elif line.startswith('| ID |') or line.startswith('|----|'):
            continue
        elif line.startswith('|') and '|' in line:
            parts = [p.strip() for p in line.split('|')[1:-1]]
            if len(parts) >= 5:
                task = parts[1]
                duration = parts[2]
                start = parts[3]
                finish = parts[4]
                tasks.append({'Section': current_section, 'Task': task, 'Start': start, 'Finish': finish, 'Duration': duration})
    
    start_dates = []
    durations = []
    task_names = []
    for task in tasks:
        try:
            start_date = datetime.strptime(task['Start'], '%d-%b-%Y')
            finish_date = datetime.strptime(task['Finish'], '%d-%b-%Y')
            duration_days = (finish_date - start_date).days
            start_dates.append(start_date)
            durations.append(duration_days)
            task_names.append(task['Task'])
        except:
            pass
    
    if not task_names:
        return None
    
    fig, ax = plt.subplots(figsize=(10, len(task_names) * 0.5))
    ax.barh(task_names, durations, left=start_dates, height=0.4, color='orange', label='Procurement')
    for i in range(len(durations)):
        install_start = start_dates[i] + relativedelta(days=durations[i])
        ax.barh(task_names[i], 30, left=install_start, height=0.4, color='blue', label='Installation' if i == 0 else "")
    
    ax.set_xlabel('Timeline')
    ax.set_title('Overlapping Gantt: Procurement vs Installation (All Equipment)')
    ax.legend()
    plt.gca().invert_yaxis()
    return fig

def main():
    st.set_page_config(
        page_title="Construction Procurement Assistant",
        page_icon="🏗️",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    st.title("Construction Procurement Assistant")
    st.write("Enter project details to get material estimates, vendor information, and schedules.")
    
    # Generate missing ML files if needed
    generate_missing_ml_files()
    
    if 'rag' not in st.session_state:
        try:
            with st.spinner("Initializing AI Assistant from filtered_products.json..."):
                st.session_state.rag = IndiaMART_RAG(json_file="filtered_products.json")
                st.session_state.rag.load_and_process_json_files()
                st.session_state.rag.build_faiss_index()
                st.success("AI Assistant initialized successfully from filtered_products.json!")
        except Exception as e:
            st.error(f"Initialization error: {str(e)}")
            st.error(f"Check if filtered_products.json exists in {os.getcwd()} and matches the structure (list of dicts with url, title, price, etc.).")
            return
    
    query = st.text_area("Enter Project Details",
                         placeholder="e.g., 25 MegaWatt, 2 Lacs SquareFoot Built Up Area, Project Volume of 1875 Cr in Rupees, Build in Navi Mumbai Area (add 'Health Center' for specific materials)",
                         height=100)
    
    if st.button("Generate Complete Procurement Plan"):
        if not query:
            st.error("Please enter project details.")
            return
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        try:
            status_text.text("Processing query and searching vendors...")
            progress_bar.progress(20)
            
            result = st.session_state.rag.query(query)
            
            status_text.text("Generating material estimates...")
            progress_bar.progress(40)
            
            st.subheader("Query Results")
            st.write(f"**Answer:**\n{result['answer']}")
            
            if result['sources']:
                with st.expander("Sources"):
                    for source in result['sources'][:3]:
                        st.write(f"- {source}")
            
            material_estimates = result.get('material_estimates', [])
            if material_estimates:
                status_text.text("Running ML predictions with real JSON data...")
                progress_bar.progress(60)
                
                st.subheader("Material Estimates with ML Predictions (Real Data from JSON + Catalog)")
                updated_materials = []
                for mat in material_estimates[:5]:  # Increased to 5 for Transformers and Chillers
                    quantity_str = mat['Quantity']
                    estimated_qty_match = re.search(r'(\d+)', quantity_str)
                    estimated_qty = int(estimated_qty_match.group(1)) if estimated_qty_match else 100
                    
                    catalog_source = mat.get('catalog_source', None)
                    
                    ml_input, real_product_data = generate_ml_input_from_rag(st.session_state.rag, query, mat['Material/Equipment'], estimated_qty, catalog_source)
                    ml_input['ExtendedQuantity'] = estimated_qty
                    ml_input['ExtendedPrice'] = ml_input['UnitPrice'] * estimated_qty
                    
                    prediction = run_ml_prediction(ml_input)
                    if 'error' not in prediction:
                        qty_shipped = prediction['qty_shipped']
                        parts = mat['Quantity'].split(' ', 1)
                        if len(parts) == 2:
                            parts[0] = str(qty_shipped)
                            mat['Quantity'] = ' '.join(parts)
                        
                        mat['product_details'] = real_product_data.get('product_details', 'No matching product found')
                        
                        st.write(f"✅ {mat['Material/Equipment']}: ML optimized quantity: {mat['Quantity']} (Master Item: {prediction['master_item_no']}, Method: {prediction['prediction_method']}, Catalog: {catalog_source})")
                        updated_materials.append(mat)
                    else:
                        st.error(f"❌ {mat['Material/Equipment']}: ML Error - {prediction['error']}")
                        mat['product_details'] = real_product_data.get('product_details', 'No matching product found')
                        updated_materials.append(mat)
                
                result['material_estimates'] = updated_materials
                
                st.markdown("### Material Estimates (with Real JSON Sources + Catalog)")
                st.markdown(st.session_state.rag.format_material_table(updated_materials))
                
                status_text.text("Identifying vendors...")
                progress_bar.progress(70)
                
                st.subheader("Vendor Identification (with Real Prices from JSON)")
                vendor_table = "| Material/Equipment | Quantity | Vendor/Manufacturers | Price (from JSON) | Catalog Source |\n|--------------------|----------|----------------------|-------------------|----------------|\n"
                for mat in updated_materials[:5]:
                    vendor_query = f"Find suppliers for {mat['Material/Equipment']} in {result['requirements']['location'] or 'Navi Mumbai'} with high ratings GST after 2017 available in stock"
                    try:
                        vendor_result = st.session_state.rag.query(vendor_query, k=3, apply_filters=True)
                        vendor = extract_vendor_details(vendor_result['answer'])
                        price_info = mat.get('product_details', '').split('(Price: ')[1].split(',')[0] if '(Price: ' in mat.get('product_details', '') else "N/A"
                        catalog_source = mat.get('catalog_source', 'N/A')
                    except Exception as e:
                        vendor = f"Error: {str(e)}"
                        price_info = "N/A"
                        catalog_source = mat.get('catalog_source', 'N/A')
                    vendor_table += f"| {mat['Material/Equipment']} | {mat['Quantity']} | {vendor} | {price_info} | {catalog_source} |\n"
                st.markdown(vendor_table)
                
                status_text.text("Generating complete project plan...")
                progress_bar.progress(80)
                
                complete_plan = generate_complete_plan_in_chunks(updated_materials, query, st.session_state.rag.groq_api_key)
                
                st.subheader("Procurement Timeline")
                st.markdown(complete_plan['timeline'])
                
                st.subheader("Integrated Project Schedule")
                st.markdown(complete_plan['schedule'])
                
                status_text.text("Creating visualization...")
                progress_bar.progress(95)
                
                st.subheader("Project Gantt Chart")
                fig = plot_gantt_chart(complete_plan['schedule'])
                if fig:
                    st.pyplot(fig)
                else:
                    st.info("Gantt chart visualization requires schedule data in specific format.")
                
                progress_bar.progress(100)
                status_text.text("Complete!")
                st.success("✅ Procurement plan generated successfully with real JSON data + Catalog!")
                
        except Exception as e:
            st.error(f"Error processing query: {str(e)}")
            st.error(f"Detailed error: {traceback.format_exc()}")

if __name__ == "__main__":
    main()