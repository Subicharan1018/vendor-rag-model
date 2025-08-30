from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import csv
import time
import re
import pandas as pd

def setup_driver():
    """Set up and return a Chrome WebDriver instance"""
    chrome_options = Options()
    chrome_options.add_argument('--headless')  # Run in background
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_experimental_option('excludeSwitches', ['enable-automation'])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    service = Service()  # Assumes chromedriver is in PATH
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return driver

def extract_material_names(csv_file_path):
    """Extract unique material names from the CSV file"""
    try:
        df = pd.read_csv(csv_file_path)
        material_names = set()
        
        # Check if 'Material_Name' column exists
        if 'Material_Name' in df.columns:
            material_names.update(df['Material_Name'].dropna().unique())
        
        # Check if 'Typical_Materials' column exists
        if 'Typical_Materials' in df.columns:
            for materials in df['Typical_Materials'].dropna():
                # Split comma-separated materials
                for material in str(materials).split(','):
                    material_names.add(material.strip())
        
        return list(material_names)
    except Exception as e:
        print(f"Error reading CSV file: {e}")
        return []

def search_indiamart(driver, search_query):
    """Search for a material on IndiaMart and extract all anchor links"""
    # Format the search query for URL
    formatted_query = search_query.replace(' ', '+')
    search_url = f"https://dir.indiamart.com/search.mp?ss={formatted_query}"
    
    print(f"Searching for: {search_query}")
    driver.get(search_url)
    
    # Wait for page to load
    time.sleep(3)
    
    anchor_links = []
    page_count = 1
    
    while True:
        print(f"Scraping page {page_count} for '{search_query}'...")
        
        # Wait for product cards to load
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "a.cardlinks"))
            )
        except:
            print(f"No product links found for '{search_query}' or timeout.")
            break
        
        # Find all anchor links with class containing 'cardlinks'
        links = driver.find_elements(By.CSS_SELECTOR, "a[class*='cardlinks']")
        
        for link in links:
            href = link.get_attribute('href')
            text = link.text.strip()
            
            # Only include valid product links
            if href and ('proddetail' in href or 'www.indiamart.com/' in href):
                anchor_links.append({
                    'search_query': search_query,
                    'href': href, 
                    'title': text
                })
        
        print(f"Found {len(links)} links on this page")
        
        # Check if there's a next page
        try:
            next_button = driver.find_element(By.CSS_SELECTOR, "a[title='Next Page']")
            if next_button.get_attribute('href'):
                next_button.click()
                time.sleep(3)  # Wait for next page to load
                page_count += 1
            else:
                break
        except:
            print("No more pages found.")
            break
    
    return anchor_links

def main():
    # Initialize the driver
    driver = setup_driver()
    
    try:
        # Extract material names from both CSV files
        materials1 = extract_material_names('facility_construction_summary.csv')
        materials2 = extract_material_names('construction_materials_by_facility.csv')
        
        # Combine and deduplicate material names
        all_materials = list(set(materials1 + materials2))
        
        print(f"Found {len(all_materials)} unique materials to search for")
        
        # Search for each material and collect all anchor links
        all_anchor_links = []
        
        for i, material in enumerate(all_materials):
            print(f"Processing material {i+1}/{len(all_materials)}")
            
            # Skip materials that are too generic or short
            if len(material) < 3:
                print(f"Skipping '{material}' - too short")
                continue
                
            try:
                links = search_indiamart(driver, material)
                all_anchor_links.extend(links)
                print(f"Found {len(links)} links for '{material}'")
                
                # Add a delay between searches to avoid being blocked
                time.sleep(2)
                
            except Exception as e:
                print(f"Error searching for '{material}': {e}")
                continue
        
        # Save all anchor links to CSV
        if all_anchor_links:
            with open('indiamart_anchor_links.csv', 'w', newline='', encoding='utf-8') as f:
                fieldnames = ['search_query', 'href', 'title']
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(all_anchor_links)
            
            print(f"Saved {len(all_anchor_links)} anchor links to 'indiamart_anchor_links.csv'")
        else:
            print("No anchor links found")
        
    finally:
        # Close the driver
        driver.quit()

if __name__ == "__main__":
    main()
    