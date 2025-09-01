import json
import re
import time
import csv
import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.chrome.options import Options

def setup_driver():
    """Set up and return a Chrome WebDriver with appropriate options."""
    chrome_options = Options()
    # Uncomment the next line if you want to run in headless mode
    # chrome_options.add_argument("--headless")
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

def extract_notes_data(driver):
    """Extract notes information with improved selectors based on actual HTML structure."""
    notes_data = {
        "Top Notes": [],
        "Middle Notes": [],
        "Base Notes": []
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
                print(f"Found header for {note_type}")
                
                # Find note elements in the container
                note_elements = header.find_elements(By.XPATH, approach["container_xpath"])
                print(f"Found {len(note_elements)} note elements for {note_type}")
                
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
                            print(f"Added note: {note_name} (intensity: {intensity})")
                            
                    except Exception as e:
                        print(f"Error extracting individual note: {e}")
                        continue
                        
            except Exception as e:
                print(f"Error extracting {note_type} with approach {i}: {e}")
                continue
        
        # Fallback method - if no notes found, try to extract from any links
        if not any(notes_data.values()):
            print("No notes found with primary methods, trying fallback...")
            try:
                all_note_links = driver.find_elements(By.XPATH, "//a[contains(@href, '/notes/')]")
                print(f"Found {len(all_note_links)} note links as fallback")
                
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
                print(f"Fallback method failed: {e}")
                
    except Exception as e:
        print(f"Error in extract_notes_data: {e}")
    
    return notes_data

def extract_pros_cons(driver):
    """Extract pros and cons with corrected selectors based on provided XPaths."""
    pros_cons = {"pros": [], "cons": []}
    
    try:
        # Wait for the pros/cons section
        time.sleep(3)
        
        # Extract PROS using the provided XPaths
        try:
            print("Extracting pros...")
            # Find all pros items using the specific XPath
            pros_items = driver.find_elements(By.XPATH, "//div[contains(@style, 'rgb(207, 249, 207)')]//div[contains(@class, 'cell small-12') and contains(@style, 'display: inline-flex')]")
            print(f"Found {len(pros_items)} pros items")
            
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
                        print(f"Error extracting votes for pros item {i}: {ve}")
                    
                    # Only add if we have meaningful text
                    if pros_text:
                        pros_cons["pros"].append({
                            "text": pros_text,
                            "up_votes": up_votes,
                            "down_votes": down_votes
                        })
                        print(f"Added pros: {pros_text[:50]}... (👍{up_votes} 👎{down_votes})")
                        
                except Exception as e:
                    print(f"Error processing pros item {i}: {e}")
                    continue
                    
        except Exception as e:
            print(f"Error extracting pros: {e}")
        
        # Extract CONS using the provided XPaths
        try:
            print("Extracting cons...")
            # Find all cons items using the specific XPath
            cons_items = driver.find_elements(By.XPATH, "//div[contains(@style, 'rgb(247, 228, 225)')]//div[contains(@class, 'cell small-12') and contains(@style, 'display: inline-flex')]")
            print(f"Found {len(cons_items)} cons items")
            
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
                        print(f"Error extracting votes for cons item {i}: {ve}")
                    
                    # Only add if we have meaningful text
                    if cons_text:
                        pros_cons["cons"].append({
                            "text": cons_text,
                            "up_votes": up_votes,
                            "down_votes": down_votes
                        })
                        print(f"Added cons: {cons_text[:50]}... (👍{up_votes} 👎{down_votes})")
                        
                except Exception as e:
                    print(f"Error processing cons item {i}: {e}")
                    continue
                    
        except Exception as e:
            print(f"Error extracting cons: {e}")
            
        # Fallback method if the main approach doesn't work
        if not pros_cons["pros"] and not pros_cons["cons"]:
            print("Main pros/cons extraction failed, trying fallback...")
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
                print(f"Fallback pros/cons extraction failed: {fe}")
                
    except Exception as e:
        print(f"Error in extract_pros_cons: {e}")
    
    return pros_cons

def extract_stats_with_multiple_approaches(driver, stat_type):
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
                print(f"Found {stat_type} container")
                
                # Find stat items
                stat_items = container.find_elements(By.XPATH, config["item_xpath"])
                print(f"Found {len(stat_items)} {stat_type} stat items")
                
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
                                print(f"Extracted {config['labels'][i]}: {percentage}%")
                            else:
                                print(f"No width match for {config['labels'][i]}")
                        else:
                            # Alternative approach: look for any element with width style
                            elements_with_width = item.find_elements(By.XPATH, ".//*[contains(@style, 'width:')]")
                            for element in elements_with_width:
                                style = element.get_attribute("style")
                                width_match = re.search(r"width:\s*([\d.]+)%", style)
                                if width_match:
                                    percentage = float(width_match.group(1))
                                    stats[config["labels"][i]] = percentage
                                    print(f"Extracted {config['labels'][i]}: {percentage}% (alt method)")
                                    break
                            
                    except Exception as e:
                        print(f"Error extracting {stat_type} stat {i} ({config['labels'][i]}): {e}")
                        continue
                
                # If we found stats, break
                if stats:
                    break
                    
            except Exception as e:
                print(f"Container selector failed for {stat_type}: {e}")
                continue
    
    except Exception as e:
        print(f"Error extracting {stat_type} stats: {e}")
    
    return stats

def extract_main_accords_improved(driver):
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
                            print(f"Error processing accord: {e}")
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
        print(f"Error extracting main accords: {e}")
    
    return main_accords

def scrape_fragrance_details(url):
    """
    Enhanced scrape function with better error handling and multiple approaches
    """
    driver = setup_driver()
    
    try:
        print(f"Navigating to: {url}")
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
                
        print(f"Found fragrance name: {fragrance_name}")
        
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
                
        print(f"Found image URL: {image_url}")
        
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
            print(f"Error extracting brand info: {e}")
        
        print(f"Found brand: {brand_info.get('name', 'N/A')}")
        
        # Extract main accords with improved method
        main_accords = extract_main_accords_improved(driver)
        print(f"Found {len(main_accords)} main accords")
        
        # Extract notes with improved method
        notes = extract_notes_data(driver)
        print(f"Found notes: Top={len(notes['Top Notes'])}, Middle={len(notes['Middle Notes'])}, Base={len(notes['Base Notes'])}")
        
        # Extract pros and cons with corrected method
        pros_cons = extract_pros_cons(driver)
        print(f"Found {len(pros_cons['pros'])} pros and {len(pros_cons['cons'])} cons")
        
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
                    photo_elements = driver.find_elements(By.CSS_SELECTor, selector)
                    for img in photo_elements:
                        src = img.get_attribute("src")
                        if src and src not in photos:
                            photos.append(src)
                    if photos:
                        break
                except:
                    continue
        except Exception as e:
            print(f"Error extracting photos: {e}")
            
        print(f"Found {len(photos)} photos")
        
        # Extract statistics with improved methods
        ownership_stats = extract_stats_with_multiple_approaches(driver, "ownership")
        print(f"Found {len(ownership_stats)} ownership stats")
        
        sentiment_stats = extract_stats_with_multiple_approaches(driver, "sentiment")
        print(f"Found {len(sentiment_stats)} sentiment stats")
        
        seasonality_stats = extract_stats_with_multiple_approaches(driver, "seasonality")
        print(f"Found {len(seasonality_stats)} seasonality stats")
        
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
        print(f"An error occurred during scraping: {e}")
        import traceback
        traceback.print_exc()
        return None
    finally:
        driver.quit()

def save_to_json(data, filename):
    """Save data to a JSON file"""
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def load_progress():
    """Load progress from a file to resume scraping from where it left off"""
    progress_file = "scraping_progress.json"
    if os.path.exists(progress_file):
        with open(progress_file, 'r') as f:
            return json.load(f)
    return {"completed_urls": [], "failed_urls": []}

def save_progress(completed_urls, failed_urls):
    """Save progress to a file"""
    progress_file = "scraping_progress.json"
    with open(progress_file, 'w') as f:
        json.dump({"completed_urls": completed_urls, "failed_urls": failed_urls}, f)

def read_urls_from_csv(csv_file, limit=1000):
    """Read URLs from a CSV file"""
    urls = []
    with open(csv_file, 'r', newline='', encoding='utf-8') as file:
        reader = csv.reader(file)
        for i, row in enumerate(reader):
            if i >= limit:
                break
            if row and len(row) > 0:
                urls.append(row[0])
    return urls

def main():
    # Configuration
    csv_file = "url.csv"
    output_dir = "scraped_data"
    limit = 1000  # Number of URLs to process
    
    # Create output directory if it doesn't exist
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # Load progress
    progress = load_progress()
    completed_urls = progress.get("completed_urls", [])
    failed_urls = progress.get("failed_urls", [])
    
    # Read URLs from CSV
    all_urls = read_urls_from_csv(csv_file, limit)
    
    # Filter out already processed URLs
    urls_to_process = [url for url in all_urls if url not in completed_urls and url not in failed_urls]
    
    print(f"Total URLs to process: {len(urls_to_process)}")
    print(f"Already completed: {len(completed_urls)}")
    print(f"Previously failed: {len(failed_urls)}")
    
    # Process each URL
    for i, url in enumerate(urls_to_process):
        print(f"\nProcessing URL {i+1}/{len(urls_to_process)}: {url}")
        
        try:
            # Scrape the fragrance details
            fragrance_data = scrape_fragrance_details(url)
            
            if fragrance_data:
                # Generate filename from fragrance name
                safe_name = re.sub(r'[^\w\s-]', '', fragrance_data.get('name', 'fragrance')).strip()
                if not safe_name:
                    safe_name = f"fragrance_{i}"
                filename = f"{safe_name.replace(' ', '_').lower()}_data.json"
                filepath = os.path.join(output_dir, filename)
                
                # Save the data
                save_to_json(fragrance_data, filepath)
                print(f"Data successfully saved to {filepath}")
                
                # Mark as completed
                completed_urls.append(url)
            else:
                print(f"Failed to scrape data from {url}")
                failed_urls.append(url)
                
        except Exception as e:
            print(f"Error processing {url}: {e}")
            failed_urls.append(url)
        
        # Save progress after each URL
        save_progress(completed_urls, failed_urls)
        print(f"Progress saved. Completed: {len(completed_urls)}, Failed: {len(failed_urls)}")
        
        # Add a delay to be respectful to the server
        time.sleep(2)
    
    print("\nScraping completed!")
    print(f"Successfully scraped: {len(completed_urls)} URLs")
    print(f"Failed: {len(failed_urls)} URLs")
    
    # Save final progress
    save_progress(completed_urls, failed_urls)

if __name__ == "__main__":
    main()