import streamlit as st
import pandas as pd
import numpy as np
from scipy import sparse
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
import joblib
import warnings
warnings.filterwarnings('ignore')

# Set random seed
SEED = 42

# Streamlit app title
st.title("Project Prediction App")
st.write("Enter project details to predict MasterItemNo and regression value.")

# Load models and mappings
@st.cache_resource
def load_models():
    classifier = joblib.load('lgb_classifier.pkl')
    regressor = joblib.load('lgb_regressor.pkl')
    label_encoder = joblib.load('label_encoder.pkl')
    det_mapping = joblib.load('deterministic_mapping.pkl')
    return classifier, regressor, label_encoder, det_mapping

classifier, regressor, label_encoder, det_mapping = load_models()

# Load training data to train preprocessor
@st.cache_resource
def load_preprocessor():
    train_c = pd.read_csv("clean_train_c.csv")
    train_r = pd.read_csv("clean_train_r.csv")
    # Combine training data for preprocessing
    categorical_cols = ['PROJECT_CITY', 'STATE', 'PROJECT_COUNTRY', 'CORE_MARKET', 'PROJECT_TYPE']
    numerical_cols = ['SIZE_BUILDINGSIZE', 'NUMFLOORS']
    # Create a preprocessor
    preprocessor = ColumnTransformer(
        transformers=[
            ('cat', TfidfVectorizer(max_features=1000, stop_words='english'), 'combined_text'),
            ('num', StandardScaler(), numerical_cols)
        ])
    # Create combined text feature
    train_c['combined_text'] = train_c[categorical_cols].astype(str).agg(' '.join, axis=1)
    train_r['combined_text'] = train_r[categorical_cols].astype(str).agg(' '.join, axis=1)
    # Fit preprocessor
    X_train = pd.concat([train_c, train_r])[categorical_cols + numerical_cols + ['combined_text']]
    preprocessor.fit(X_train)
    return preprocessor

preprocessor = load_preprocessor()

# User input
st.subheader("Enter Project Details")
project_city = st.text_input("Project City", placeholder="e.g., Visakhapatnam")
state = st.text_input("State", placeholder="e.g., Andhra Pradesh")
project_country = st.text_input("Project Country", placeholder="e.g., India")
core_market = st.selectbox("Core Market", options=["Enterprise", "Bio Innovation", "Misc Market", "Other"])
project_type = st.selectbox("Project Type", options=["Critical Ops", "R&D Laboratories", "Learning Hub", "Other"])
size_buildingsize = st.number_input("Building Size (sq ft)", min_value=0, value=10000)
num_floors = st.number_input("Number of Floors", min_value=0, value=0)

if st.button("Predict"):
    if project_city and state and project_country:
        # Prepare input data
        input_data = pd.DataFrame({
            'PROJECT_CITY': [project_city],
            'STATE': [state],
            'PROJECT_COUNTRY': [project_country],
            'CORE_MARKET': [core_market],
            'PROJECT_TYPE': [project_type],
            'SIZE_BUILDINGSIZE': [size_buildingsize],
            'NUMFLOORS': [num_floors]
        })
        input_data['combined_text'] = input_data[['PROJECT_CITY', 'STATE', 'PROJECT_COUNTRY', 'CORE_MARKET', 'PROJECT_TYPE']].astype(str).agg(' '.join, axis=1)

        # Check deterministic mapping (assuming it maps combined_text to MasterItemNo)
        combined_text = input_data['combined_text'].iloc[0]
        if combined_text in det_mapping.index:
            pred_master_item_no = det_mapping[combined_text]
            class_source = "Deterministic Mapping"
        else:
            # Preprocess input
            X_input = preprocessor.transform(input_data)
            # Predict with classifier
            pred_label = classifier.predict(X_input)[0]
            pred_master_item_no = label_encoder.inverse_transform([pred_label])[0]
            class_source = "CatBoost Classifier"

        # Regression prediction
        X_input_reg = preprocessor.transform(input_data)
        pred_reg = regressor.predict(X_input_reg)[0]

        # Display results
        st.subheader("Prediction Results")
        st.write(f"**Predicted MasterItemNo**: {pred_master_item_no} (Source: {class_source})")
        st.write(f"**Regression Output**: {pred_reg:.4f}")
    else:
        st.error("Please fill in all required fields (Project City, State, Project Country).")

# Instructions
st.markdown("""
### Instructions
1. Enter the project details in the fields above.
2. Click the 'Predict' button to see the predicted MasterItemNo and regression value.
3. The MasterItemNo is predicted using a deterministic mapping (if available) or a CatBoost classifier.
4. The regression value is predicted using a CatBoost regressor.
""")