import json
import re
import time
import csv
import os
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.chrome.options import Options

class FragranceScraper:
    def __init__(self, csv_file="url.csv", max_urls=1000, progress_file="scraping_progress.json"):
        self.csv_file = csv_file
        self.max_urls = max_urls
        self.progress_file = progress_file
        self.progress_data = self.load_progress()
        
    def load_progress(self):
        """Load progress from file or create new progress data"""
        default_progress = {
            "current_index": 1001,
            "total_processed": 0,
            "successful_scrapes": 0,
            "failed_scrapes": 0,
            "start_time": datetime.now().isoformat(),
            "last_update": datetime.now().isoformat(),
            "completed_urls": [],
            "failed_urls": []
        }
        
        if os.path.exists(self.progress_file):
            try:
                with open(self.progress_file, 'r') as f:
                    progress = json.load(f)
                    
                # Ensure all required keys exist, fill missing ones with defaults
                for key, default_value in default_progress.items():
                    if key not in progress:
                        progress[key] = default_value
                
                print(f"Resuming from index {progress.get('current_index', 0)}")
                return progress
            except Exception as e:
                print(f"Error loading progress file: {e}, starting fresh")
        
        return default_progress
    
    def save_progress(self):
        """Save current progress to file"""
        self.progress_data["last_update"] = datetime.now().isoformat()
        with open(self.progress_file, 'w') as f:
            json.dump(self.progress_data, f, indent=2)
    
    def load_urls_from_csv(self):
        """Load URLs from CSV file"""
        urls = []
        try:
            with open(self.csv_file, 'r', encoding='utf-8') as f:
                csv_reader = csv.reader(f)
                
                for row_num, row in enumerate(csv_reader):
                    if len(urls) >= self.max_urls:
                        break
                    
                    if row and len(row) > 0:
                        # Check each column for a URL
                        for col_index in range(len(row)):
                            cell_value = row[col_index].strip()
                            if cell_value.startswith('http'):
                                urls.append(cell_value)
                                break
            
            return urls
        except Exception as e:
            print(f"Error loading CSV file: {e}")
            return []

    def setup_driver(self):
        """Set up and return a Chrome WebDriver with appropriate options."""
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36")
        
        driver = webdriver.Chrome(options=chrome_options)
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return driver

    def extract_notes_data(self, driver):
        """Extract notes information with improved selectors based on actual HTML structure."""
        notes_data = {
            "Top Notes": [],
            "Middle Notes": [],
            "Base Notes": [],
            "General Notes": []  # For cases where notes aren't categorized
        }
        
        try:
            # Wait for page to load
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # Multiple approaches to find notes sections
            note_section_approaches = [
                # Approach 1: Look for h4 elements with bold text containing note type
                {
                    "header_selector": "//h4[contains(., 'Top Notes')]",
                    "container_xpath": "./following-sibling::div[1]//div[contains(@style, 'display: flex; justify-content: center')]//div[contains(@style, 'margin: 0.2rem')]"
                },
                {
                    "header_selector": "//h4[contains(., 'Middle Notes')]", 
                    "container_xpath": "./following-sibling::div[1]//div[contains(@style, 'display: flex; justify-content: center')]//div[contains(@style, 'margin: 0.2rem')]"
                },
                {
                    "header_selector": "//h4[contains(., 'Base Notes')]",
                    "container_xpath": "./following-sibling::div[1]//div[contains(@style, 'display: flex; justify-content: center')]//div[contains(@style, 'margin: 0.2rem')]"
                },
                # Approach 2: Look for bold elements
                {
                    "header_selector": "//b[contains(text(), 'Top Notes')]",
                    "container_xpath": "./../../following-sibling::div[1]//div[contains(@style, 'margin: 0.2rem')]"
                },
                {
                    "header_selector": "//b[contains(text(), 'Middle Notes')]",
                    "container_xpath": "./../../following-sibling::div[1]//div[contains(@style, 'margin: 0.2rem')]"
                },
                {
                    "header_selector": "//b[contains(text(), 'Base Notes')]",
                    "container_xpath": "./../../following-sibling::div[1]//div[contains(@style, 'margin: 0.2rem')]"
                }
            ]
            
            # Map approach indices to note types
            note_type_mapping = {
                0: "Top Notes", 1: "Middle Notes", 2: "Base Notes",
                3: "Top Notes", 4: "Middle Notes", 5: "Base Notes"
            }
            
            for i, approach in enumerate(note_section_approaches):
                note_type = note_type_mapping[i]
                
                # Skip if we already found notes for this type
                if notes_data[note_type]:
                    continue
                    
                try:
                    # Find the header
                    header = driver.find_element(By.XPATH, approach["header_selector"])
                    
                    # Find note elements in the container
                    note_elements = header.find_elements(By.XPATH, approach["container_xpath"])
                    
                    for note_element in note_elements:
                        try:
                            # Extract note name from the div text (the note name should be direct text)
                            note_name = None
                            
                            # Method 1: Look for direct text in the note element
                            note_text_div = note_element.find_element(By.XPATH, ".//div[last()]")  # Last div usually contains the name
                            if note_text_div.text and note_text_div.text.strip():
                                note_name = note_text_div.text.strip()
                            
                            # Method 2: Look for anchor tag text
                            if not note_name:
                                try:
                                    note_link = note_element.find_element(By.XPATH, ".//a")
                                    # Get the text after the span (the actual note name)
                                    full_text = note_link.get_attribute("textContent")
                                    if full_text:
                                        note_name = full_text.strip()
                                except:
                                    pass
                            
                            if not note_name:
                                continue
                            
                            # Extract intensity from opacity
                            intensity = 1.0
                            try:
                                style = note_element.get_attribute("style")
                                if style:
                                    opacity_match = re.search(r"opacity:\s*([\d.]+)", style)
                                    if opacity_match:
                                        intensity = float(opacity_match.group(1))
                            except:
                                pass
                            
                            # Extract note image URL
                            note_image = None
                            try:
                                img_element = note_element.find_element(By.TAG_NAME, "img")
                                note_image = img_element.get_attribute("src")
                            except:
                                pass
                            
                            # Only add if we have a valid note name
                            if note_name and len(note_name) > 1:
                                notes_data[note_type].append({
                                    "name": note_name,
                                    "intensity": intensity,
                                    "image_url": note_image
                                })
                                
                        except Exception as e:
                            continue
                            
                except Exception as e:
                    continue
            
            # Fallback method - if no notes found, try to extract from any links
            if not any(notes_data.values()):
                try:
                    all_note_links = driver.find_elements(By.XPATH, "//a[contains(@href, '/notes/')]")
                    
                    for link in all_note_links:
                        try:
                            note_name = link.text.strip()
                            if note_name and len(note_name) > 1:
                                # Try to determine note type based on position/context
                                parent_text = link.find_element(By.XPATH, "./ancestor::div[5]").get_attribute("outerHTML")
                                
                                if "Top" in parent_text:
                                    target_list = "Top Notes"
                                elif "Middle" in parent_text:
                                    target_list = "Middle Notes"
                                elif "Base" in parent_text:
                                    target_list = "Base Notes"
                                else:
                                    # Default to distributing evenly
                                    total_notes = sum(len(v) for v in notes_data.values())
                                    if total_notes < 3:
                                        target_list = "Top Notes"
                                    elif total_notes < 6:
                                        target_list = "Middle Notes"
                                    else:
                                        target_list = "Base Notes"
                                
                                notes_data[target_list].append({
                                    "name": note_name,
                                    "intensity": 1.0,
                                    "image_url": None
                                })
                                
                        except Exception as e:
                            continue
                except Exception as e:
                    pass
            
            # New fallback: Extract notes from general note containers (like your example HTML)
            if not any(notes_data.values()):
                try:
                    # Look for the specific pattern in your HTML
                    general_note_containers = driver.find_elements(By.XPATH, 
                        "//div[contains(@style, 'display: flex; justify-content: center; text-align: center; flex-flow: wrap')]//div[contains(@style, 'margin: 0.2rem')]")
                    
                    for note_container in general_note_containers:
                        try:
                            # Extract note name - look for the text content
                            note_name = None
                            
                            # Method 1: Look for direct div text (last div usually contains name)
                            divs = note_container.find_elements(By.XPATH, "./div")
                            if len(divs) >= 2:  # Should have at least image div and text div
                                text_div = divs[-1]  # Last div should contain the name
                                note_name = text_div.text.strip()
                            
                            # Method 2: Look for anchor link text
                            if not note_name:
                                try:
                                    note_link = note_container.find_element(By.XPATH, ".//a[contains(@href, '/notes/')]")
                                    note_name = note_link.get_attribute("textContent").strip()
                                    # Clean up if there's a span element
                                    if note_name and "link-span" not in note_name:
                                        note_name = note_name.replace("link-span", "").strip()
                                except:
                                    pass
                            
                            if not note_name or len(note_name) <= 1:
                                continue
                            
                            # Extract opacity-based intensity
                            intensity = 1.0
                            try:
                                style = note_container.get_attribute("style")
                                if style:
                                    opacity_match = re.search(r"opacity:\s*([\d.]+)", style)
                                    if opacity_match:
                                        intensity = float(opacity_match.group(1))
                            except:
                                pass
                            
                            # Extract note image URL
                            note_image = None
                            try:
                                img_element = note_container.find_element(By.TAG_NAME, "img")
                                note_image = img_element.get_attribute("src")
                            except:
                                pass
                            
                            # Add to General Notes since no category specified
                            notes_data["General Notes"].append({
                                "name": note_name,
                                "intensity": intensity,
                                "image_url": note_image
                            })
                            
                        except Exception as e:
                            continue
                
                except Exception as e:
                    pass
            
            # Additional fallback: Look for any note-related elements
            if not any(notes_data.values()):
                try:
                    # Try to find any elements with note URLs
                    note_elements = driver.find_elements(By.XPATH, "//a[contains(@href, '/notes/') or contains(@href, '/sastojci/')]")
                    
                    for element in note_elements:
                        try:
                            note_name = element.text.strip()
                            if note_name and len(note_name) > 1 and not any(
                                note_name in [note['name'] for notes_list in notes_data.values() for note in notes_list]
                            ):
                                notes_data["General Notes"].append({
                                    "name": note_name,
                                    "intensity": 1.0,
                                    "image_url": None
                                })
                        except:
                            continue
                            
                except:
                    pass
                    
        except Exception as e:
            pass
        
        return notes_data

    def extract_pros_cons(self, driver):
        """Extract pros and cons with corrected selectors based on provided XPaths."""
        pros_cons = {"pros": [], "cons": []}
        
        try:
            # Wait for the pros/cons section
            time.sleep(3)
            
            # Extract PROS using the provided XPaths
            try:
                # Find all pros items using the specific XPath
                pros_items = driver.find_elements(By.XPATH, "//div[contains(@style, 'rgb(207, 249, 207)')]//div[contains(@class, 'cell small-12') and contains(@style, 'display: inline-flex')]")
                
                for i, item in enumerate(pros_items):
                    try:
                        # Extract the main text (not the vote numbers)
                        # Look for the span that contains the actual pros text
                        text_elements = item.find_elements(By.XPATH, ".//span[not(contains(@class, 'num-votes')) and string-length(text()) > 10]")
                        
                        pros_text = None
                        for text_elem in text_elements:
                            text_content = text_elem.text.strip()
                            # Skip if it's just numbers or very short text
                            if text_content and len(text_content) > 10 and not text_content.isdigit():
                                pros_text = text_content
                                break
                        
                        # If no suitable text found in spans, try other elements
                        if not pros_text:
                            # Look for any text element that's not just numbers
                            all_text_elements = item.find_elements(By.XPATH, ".//*[text()]")
                            for elem in all_text_elements:
                                text_content = elem.text.strip()
                                if text_content and len(text_content) > 10 and not text_content.isdigit() and not re.match(r'^\d+$', text_content):
                                    pros_text = text_content
                                    break
                        
                        # Extract vote counts
                        up_votes = 0
                        down_votes = 0
                        try:
                            # Look for vote elements - they usually contain numbers
                            vote_elements = item.find_elements(By.XPATH, ".//span[contains(@class, 'num-votes') or (string-length(text()) <= 5 and number(text()))]")
                            
                            # Try to extract vote numbers
                            numbers_found = []
                            for vote_elem in vote_elements:
                                vote_text = vote_elem.text.strip()
                                if vote_text.isdigit():
                                    numbers_found.append(int(vote_text))
                            
                            # Assign votes based on what we found
                            if len(numbers_found) >= 2:
                                up_votes = numbers_found[0]
                                down_votes = numbers_found[1]
                            elif len(numbers_found) == 1:
                                up_votes = numbers_found[0]
                                
                        except Exception as ve:
                            pass
                        
                        # Only add if we have meaningful text
                        if pros_text:
                            pros_cons["pros"].append({
                                "text": pros_text,
                                "up_votes": up_votes,
                                "down_votes": down_votes
                            })
                            
                    except Exception as e:
                        continue
                        
            except Exception as e:
                pass
            
            # Extract CONS using the provided XPaths
            try:
                # Find all cons items using the specific XPath
                cons_items = driver.find_elements(By.XPATH, "//div[contains(@style, 'rgb(247, 228, 225)')]//div[contains(@class, 'cell small-12') and contains(@style, 'display: inline-flex')]")
                
                for i, item in enumerate(cons_items):
                    try:
                        # Extract the main text (not the vote numbers)
                        # Look for the span that contains the actual cons text
                        text_elements = item.find_elements(By.XPATH, ".//span[not(contains(@class, 'num-votes')) and string-length(text()) > 10]")
                        
                        cons_text = None
                        for text_elem in text_elements:
                            text_content = text_elem.text.strip()
                            # Skip if it's just numbers or very short text
                            if text_content and len(text_content) > 10 and not text_content.isdigit():
                                cons_text = text_content
                                break
                        
                        # If no suitable text found in spans, try other elements
                        if not cons_text:
                            # Look for any text element that's not just numbers
                            all_text_elements = item.find_elements(By.XPATH, ".//*[text()]")
                            for elem in all_text_elements:
                                text_content = elem.text.strip()
                                if text_content and len(text_content) > 10 and not text_content.isdigit() and not re.match(r'^\d+$', text_content):
                                    cons_text = text_content
                                    break
                        
                        # Extract vote counts
                        up_votes = 0
                        down_votes = 0
                        try:
                            # Look for vote elements - they usually contain numbers
                            vote_elements = item.find_elements(By.XPATH, ".//span[contains(@class, 'num-votes') or (string-length(text()) <= 5 and number(text()))]")
                            
                            # Try to extract vote numbers
                            numbers_found = []
                            for vote_elem in vote_elements:
                                vote_text = vote_elem.text.strip()
                                if vote_text.isdigit():
                                    numbers_found.append(int(vote_text))
                            
                            # Assign votes based on what we found
                            if len(numbers_found) >= 2:
                                up_votes = numbers_found[0]
                                down_votes = numbers_found[1]
                            elif len(numbers_found) == 1:
                                up_votes = numbers_found[0]
                                
                        except Exception as ve:
                            pass
                        
                        # Only add if we have meaningful text
                        if cons_text:
                            pros_cons["cons"].append({
                                "text": cons_text,
                                "up_votes": up_votes,
                                "down_votes": down_votes
                            })
                            
                    except Exception as e:
                        continue
                        
            except Exception as e:
                pass
                
            # Fallback method if the main approach doesn't work
            if not pros_cons["pros"] and not pros_cons["cons"]:
                try:
                    # Try alternative selectors
                    fallback_pros = driver.find_elements(By.XPATH, "//div[contains(@style, 'border') and contains(@style, '207, 249, 207')]//span[string-length(text()) > 10]")
                    fallback_cons = driver.find_elements(By.XPATH, "//div[contains(@style, 'border') and contains(@style, '247, 228, 225')]//span[string-length(text()) > 10]")
                    
                    for elem in fallback_pros:
                        text = elem.text.strip()
                        if text and len(text) > 10 and not text.isdigit():
                            pros_cons["pros"].append({
                                "text": text,
                                "up_votes": 0,
                                "down_votes": 0
                            })
                    
                    for elem in fallback_cons:
                        text = elem.text.strip()
                        if text and len(text) > 10 and not text.isdigit():
                            pros_cons["cons"].append({
                                "text": text,
                                "up_votes": 0,
                                "down_votes": 0
                            })
                            
                except Exception as fe:
                    pass
                    
        except Exception as e:
            pass
        
        return pros_cons

    def extract_stats_with_multiple_approaches(self, driver, stat_type):
        """Generic function to extract statistics with multiple approaches."""
        stats = {}
        
        # Define selectors and labels for different stat types
        stat_configs = {
            "ownership": {
                "labels": ["own", "had", "want"],
                "container_selectors": [
                    "//div[contains(@style, 'display: flex; justify-content: space-around;')]",
                    "//div[contains(@class, 'ownership-stats')]"
                ],
                "item_xpath": ".//div[contains(@style, 'display: flex; flex-flow: column wrap')]"
            },
            "sentiment": {
                "labels": ["love", "like", "ok", "dislike", "hate"],
                "container_selectors": [
                    "//div[contains(@class, 'small-6')][1]//div[contains(@style, 'display: flex; justify-content: space-evenly;')]",
                    "//div[.//span[contains(@class, 'vote-button-legend') and contains(text(), 'love')]]/.."
                ],
                "item_xpath": ".//div[contains(@style, 'display: flex; flex-direction: column; justify-content: space-around')]"
            },
            "seasonality": {
                "labels": ["winter", "spring", "summer", "fall", "day", "night"],
                "container_selectors": [
                    "//div[contains(@class, 'small-6')][2]//div[contains(@style, 'display: flex; justify-content: space-evenly;')]",
                    "//div[.//span[contains(@class, 'vote-button-legend') and contains(text(), 'winter')]]/.."
                ],
                "item_xpath": ".//div[contains(@style, 'display: flex; flex-direction: column; justify-content: space-around')]"
            }
        }
        
        if stat_type not in stat_configs:
            return stats
        
        config = stat_configs[stat_type]
        
        try:
            # Try different container selectors
            for container_selector in config["container_selectors"]:
                try:
                    container = driver.find_element(By.XPATH, container_selector)
                    
                    # Find stat items
                    stat_items = container.find_elements(By.XPATH, config["item_xpath"])
                    
                    # Extract percentages
                    for i, item in enumerate(stat_items[:len(config["labels"])]):
                        try:
                            # Look for the percentage bar with width style
                            percentage_bars = item.find_elements(By.XPATH, ".//div[contains(@style, 'width:') and contains(@style, '%')]")
                            
                            if percentage_bars:
                                # Get the innermost bar (the one with the actual percentage)
                                percentage_bar = percentage_bars[-1]
                                width_style = percentage_bar.get_attribute("style")
                                width_match = re.search(r"width:\s*([\d.]+)%", width_style)
                                
                                if width_match:
                                    percentage = float(width_match.group(1))
                                    stats[config["labels"][i]] = percentage
                            else:
                                # Alternative approach: look for any element with width style
                                elements_with_width = item.find_elements(By.XPATH, ".//*[contains(@style, 'width:')]")
                                for element in elements_with_width:
                                    style = element.get_attribute("style")
                                    width_match = re.search(r"width:\s*([\d.]+)%", style)
                                    if width_match:
                                        percentage = float(width_match.group(1))
                                        stats[config["labels"][i]] = percentage
                                        break
                                
                        except Exception as e:
                            continue
                    
                    # If we found stats, break
                    if stats:
                        break
                        
                except Exception as e:
                    continue
        
        except Exception as e:
            pass
        
        return stats

    def extract_main_accords_improved(self, driver):
        """Extract main accords with improved detection."""
        main_accords = []
        
        try:
            # Multiple selectors for accord bars
            accord_selectors = [
                "//div[contains(@class, 'accord-bar')]",
                "//div[contains(@style, 'background') and contains(@style, 'width') and contains(@style, '%')]",
                "//div[contains(@class, 'main-accord')]"
            ]
            
            for selector in accord_selectors:
                try:
                    accord_elements = driver.find_elements(By.XPATH, selector)
                    
                    if accord_elements:
                        for accord in accord_elements:
                            try:
                                # Extract accord name
                                accord_name = accord.text.strip()
                                
                                # If no direct text, try to find it in children
                                if not accord_name:
                                    text_elements = accord.find_elements(By.XPATH, ".//*[text()]")
                                    for elem in text_elements:
                                        text = elem.text.strip()
                                        if text and len(text) > 1:
                                            accord_name = text
                                            break
                                
                                if not accord_name:
                                    continue
                                
                                # Extract intensity from style
                                intensity = 0
                                style = accord.get_attribute("style")
                                if style:
                                    width_match = re.search(r"width:\s*([\d.]+)%", style)
                                    if width_match:
                                        intensity = float(width_match.group(1))
                                
                                main_accords.append({
                                    "name": accord_name,
                                    "intensity": intensity
                                })
                                
                            except Exception as e:
                                continue
                        
                        # If we found accords, break
                        if main_accords:
                            break
                            
                except Exception as e:
                    continue
                    
            # Fallback: look for accord names in the page structure
            if not main_accords:
                try:
                    # Look for common accord patterns
                    accord_patterns = [
                        "sweet", "woody", "fresh", "spicy", "floral", "citrus", 
                        "amber", "vanilla", "musk", "fruity", "aromatic", "oriental"
                    ]
                    
                    page_text = driver.find_element(By.TAG_NAME, "body").text.lower()
                    found_accords = []
                    
                    for pattern in accord_patterns:
                        if pattern in page_text and pattern not in found_accords:
                            main_accords.append({
                                "name": pattern,
                                "intensity": 50.0  # Default intensity
                            })
                            found_accords.append(pattern)
                            
                except:
                    pass
                    
        except Exception as e:
            pass
        
        return main_accords

    def scrape_fragrance_details(self, url):
        """Enhanced scrape function with better error handling and multiple approaches"""
        driver = self.setup_driver()
        
        try:
            driver.get(url)
            
            # Wait for page to load
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            time.sleep(5)  # More time for dynamic content
            
            # Extract fragrance name
            fragrance_name = None
            name_selectors = ["h1", "[itemprop='name']", ".perfume-name", "h1[itemprop='name']"]
            
            for selector in name_selectors:
                try:
                    if selector.startswith("["):
                        element = driver.find_element(By.CSS_SELECTOR, selector)
                    else:
                        element = driver.find_element(By.TAG_NAME, selector)
                    fragrance_name = element.text.strip()
                    if fragrance_name:
                        break
                except:
                    continue
            
            # Extract image URL
            image_url = None
            image_selectors = [
                "img[itemprop='image']",
                "img.perfume-image",
                "img[alt*='perfume']",
                ".perfume-bottle img"
            ]
            
            for selector in image_selectors:
                try:
                    img_element = driver.find_element(By.CSS_SELECTOR, selector)
                    image_url = img_element.get_attribute("src")
                    if image_url:
                        break
                except:
                    continue
            
            # Extract brand information
            brand_info = {}
            try:
                brand_selectors = [
                    "p[itemprop='brand']",
                    ".brand-info",
                    "[itemprop='brand']"
                ]
                
                for selector in brand_selectors:
                    try:
                        brand_element = driver.find_element(By.CSS_SELECTOR, selector)
                        
                        # Try to extract brand name
                        brand_name = None
                        try:
                            brand_name = brand_element.find_element(By.CSS_SELECTOR, "span[itemprop='name']").text
                        except:
                            brand_name = brand_element.text.strip()
                        
                        # Try to extract brand URL
                        brand_url = None
                        try:
                            brand_url = brand_element.find_element(By.CSS_SELECTOR, "a[itemprop='url']").get_attribute("href")
                        except:
                            pass
                        
                        # Try to extract brand logo
                        brand_logo = None
                        try:
                            brand_logo = brand_element.find_element(By.CSS_SELECTOR, "img[itemprop='logo']").get_attribute("src")
                        except:
                            pass
                        
                        if brand_name:
                            brand_info = {
                                "name": brand_name,
                                "url": brand_url,
                                "logo_url": brand_logo
                            }
                            break
                            
                    except:
                        continue
                        
            except Exception as e:
                pass
            
            # Extract main accords with improved method
            main_accords = self.extract_main_accords_improved(driver)
            
            # Extract notes with improved method
            notes = self.extract_notes_data(driver)
            
            # Extract pros and cons with corrected method
            pros_cons = self.extract_pros_cons(driver)
            
            # Extract photos
            photos = []
            try:
                photo_selectors = [
                    ".fragramcarousel img",
                    ".photo-gallery img",
                    ".perfume-photos img"
                ]
                
                for selector in photo_selectors:
                    try:
                        photo_elements = driver.find_elements(By.CSS_SELECTOR, selector)
                        for img in photo_elements:
                            src = img.get_attribute("src")
                            if src and src not in photos:
                                photos.append(src)
                        if photos:
                            break
                    except:
                        continue
            except Exception as e:
                pass
            
            # Extract statistics with improved methods
            ownership_stats = self.extract_stats_with_multiple_approaches(driver, "ownership")
            sentiment_stats = self.extract_stats_with_multiple_approaches(driver, "sentiment")
            seasonality_stats = self.extract_stats_with_multiple_approaches(driver, "seasonality")
            
            # Compile all data
            fragrance_data = {
                "name": fragrance_name,
                "image_url": image_url,
                "brand": brand_info,
                "main_accords": main_accords,
                "notes": notes,
                "pros": pros_cons["pros"],
                "cons": pros_cons["cons"],
                "photos": photos,
                "ownership_stats": ownership_stats,
                "sentiment_stats": sentiment_stats,
                "seasonality_stats": seasonality_stats,
                "url": url
            }
            
            return fragrance_data
            
        except Exception as e:
            print(f"An error occurred during scraping {url}: {e}")
            return None
        finally:
            driver.quit()

    def save_to_json(self, data, filename):
        """Save data to a JSON file"""
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            return True
        except Exception as e:
            print(f"Error saving to JSON: {e}")
            return False

    def create_output_filename(self, fragrance_name, index):
        """Create a safe filename for the JSON output"""
        if fragrance_name:
            safe_name = re.sub(r'[^\w\s-]', '', fragrance_name).strip()
            filename = f"{index:04d}_{safe_name.replace(' ', '_').lower()}_data.json"
        else:
            filename = f"{index:04d}_unknown_fragrance_data.json"
        
        # Ensure filename isn't too long
        if len(filename) > 200:
            filename = filename[:190] + "_data.json"
        
        return filename

    def print_progress_summary(self):
        """Print detailed progress summary"""
        print("\n" + "="*60)
        print("PROGRESS SUMMARY")
        print("="*60)
        print(f"Current Index: {self.progress_data['current_index']}")
        print(f"Total Processed: {self.progress_data['total_processed']}")
        print(f"Successful Scrapes: {self.progress_data['successful_scrapes']}")
        print(f"Failed Scrapes: {self.progress_data['failed_scrapes']}")
        
        if self.progress_data['total_processed'] > 0:
            success_rate = (self.progress_data['successful_scrapes'] / self.progress_data['total_processed']) * 100
            print(f"Success Rate: {success_rate:.2f}%")
        
        start_time = datetime.fromisoformat(self.progress_data['start_time'])
        elapsed_time = datetime.now() - start_time
        print(f"Elapsed Time: {elapsed_time}")
        
        if self.progress_data['successful_scrapes'] > 0:
            avg_time_per_success = elapsed_time.total_seconds() / self.progress_data['successful_scrapes']
            print(f"Average Time per Success: {avg_time_per_success:.2f} seconds")
        
        print("="*60)

    def print_scrape_result(self, index, url, fragrance_data, success):
        """Print result of individual scrape"""
        status = "✅ SUCCESS" if success else "❌ FAILED"
        print(f"\n[{index+1:4d}] {status}: {url}")
        
        if success and fragrance_data:
            print(f"     Name: {fragrance_data.get('name', 'N/A')}")
            print(f"     Brand: {fragrance_data.get('brand', {}).get('name', 'N/A')}")
            print(f"     Notes: T={len(fragrance_data['notes']['Top Notes'])}, "
                  f"M={len(fragrance_data['notes']['Middle Notes'])}, "
                  f"B={len(fragrance_data['notes']['Base Notes'])}, "
                  f"G={len(fragrance_data['notes']['General Notes'])}")
            print(f"     Pros/Cons: {len(fragrance_data['pros'])}/{len(fragrance_data['cons'])}")

    def run_scraper(self):
        """Main function to run the scraper with progress tracking"""
        print("🚀 Starting Enhanced Fragrance Scraper")
        print(f"📁 Loading URLs from: {self.csv_file}")
        print(f"🎯 Target: First {self.max_urls} URLs")
        print(f"📊 Progress file: {self.progress_file}")
        
        # Load URLs
        urls = self.load_urls_from_csv()
        if not urls:
            print("❌ No URLs found to scrape!")
            return
        
        # Limit to max_urls
        urls = urls[:self.max_urls]
        print(f"📋 Loaded {len(urls)} URLs to process")
        
        # Create output directory
        output_dir = "scraped_fragrances"
        os.makedirs(output_dir, exist_ok=True)
        
        # Start from current index
        start_index = self.progress_data['current_index']
        print(f"▶️  Starting from index {start_index}")
        
        try:
            for i in range(start_index, len(urls)):
                url = urls[i]
                
                # Skip if already completed
                if url in self.progress_data['completed_urls']:
                    print(f"⏭️  Skipping already completed: {url}")
                    continue
                
                # Update current index
                self.progress_data['current_index'] = i
                
                print(f"\n🔄 Processing [{i+1}/{len(urls)}]: {url}")
                
                try:
                    # Scrape the fragrance
                    fragrance_data = self.scrape_fragrance_details(url)
                    
                    if fragrance_data:
                        # Create filename and save
                        filename = self.create_output_filename(fragrance_data.get('name'), i)
                        filepath = os.path.join(output_dir, filename)
                        
                        if self.save_to_json(fragrance_data, filepath):
                            # Update progress
                            self.progress_data['successful_scrapes'] += 1
                            self.progress_data['completed_urls'].append(url)
                            self.print_scrape_result(i, url, fragrance_data, True)
                            print(f"     💾 Saved to: {filepath}")
                        else:
                            self.progress_data['failed_scrapes'] += 1
                            self.progress_data['failed_urls'].append(url)
                            self.print_scrape_result(i, url, None, False)
                    else:
                        # Failed scrape
                        self.progress_data['failed_scrapes'] += 1
                        self.progress_data['failed_urls'].append(url)
                        self.print_scrape_result(i, url, None, False)
                
                except Exception as e:
                    print(f"❌ Error processing {url}: {e}")
                    self.progress_data['failed_scrapes'] += 1
                    self.progress_data['failed_urls'].append(url)
                
                # Update total processed
                self.progress_data['total_processed'] += 1
                
                # Save progress every 5 items
                if (i + 1) % 5 == 0:
                    self.save_progress()
                    self.print_progress_summary()
                
                # Add delay to be respectful
                time.sleep(2)
                
                # Print mini progress every 10 items
                if (i + 1) % 10 == 0:
                    success_rate = (self.progress_data['successful_scrapes'] / self.progress_data['total_processed']) * 100
                    print(f"\n📊 Mini Update: {i+1}/{len(urls)} processed, {success_rate:.1f}% success rate")
        
        except KeyboardInterrupt:
            print("\n\n⏸️  SCRAPING INTERRUPTED BY USER")
            print("💾 Saving progress...")
            self.save_progress()
            self.print_progress_summary()
            print("✅ Progress saved. You can resume by running the script again.")
            return
        
        except Exception as e:
            print(f"\n❌ CRITICAL ERROR: {e}")
            print("💾 Saving progress...")
            self.save_progress()
            return
        
        # Final save and summary
        self.save_progress()
        print("\n" + "="*60)
        print("🎉 SCRAPING COMPLETED!")
        print("="*60)
        self.print_progress_summary()
        print(f"📁 Results saved in: {output_dir}/")
        
        if self.progress_data['failed_urls']:
            print(f"❌ Failed URLs ({len(self.progress_data['failed_urls'])}):")
            for failed_url in self.progress_data['failed_urls'][:5]:  # Show first 5
                print(f"   - {failed_url}")
            if len(self.progress_data['failed_urls']) > 5:
                print(f"   ... and {len(self.progress_data['failed_urls']) - 5} more")


def main():
    """Main function to run the scraper"""
    # Configuration
    CSV_FILE = "url.csv"
    MAX_URLS = 1000
    PROGRESS_FILE = "scraping_progress.json"
    
    # Initialize and run scraper
    scraper = FragranceScraper(
        csv_file=CSV_FILE,
        max_urls=MAX_URLS,
        progress_file=PROGRESS_FILE
    )
    
    scraper.run_scraper()


if __name__ == "__main__":
    main()