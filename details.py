from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import csv
import json
import time
import os

# Set up Selenium with Chrome
service = Service()
options = webdriver.ChromeOptions()
# Uncomment the next line if you want to run in headless mode
# options.add_argument('--headless')
driver = webdriver.Chrome(service=service, options=options)
fn = 'server_racks_links'
# Read the links.csv file
links_data = []
with open('links.csv', 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        links_data.append(row)

# List to hold all product data
all_products = []

# Scrape details from each product page
for index, item in enumerate(links_data):
    url = item['href']
    title = item['title']
    print(f"Scraping {index+1}/{len(links_data)}: {title}")
    
    driver.get(url)
    time.sleep(3)  # Wait for page to load

    # Initialize data dictionary
    data = {
        'url': url,
        'title': title,
        'details': {},  # To hold all key-value pairs from the table
        'description': 'N/A',
        'seller_info': {},  # To hold seller information
        'company_info': {},  # To hold company information
        'reviews': []  # To hold reviews
    }

    try:
        # Wait for the table to load
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, '.fs14.color.tabledesc'))
        )
        
        # Extract table details
        table = driver.find_element(By.CSS_SELECTOR, '.fs14.color.tabledesc')
        rows = table.find_elements(By.TAG_NAME, 'tr')
        
        for row in rows:
            try:
                cells = row.find_elements(By.TAG_NAME, 'td')
                if len(cells) >= 2:
                    key = cells[0].text.strip().replace(' ', '_').lower()
                    # Handle the case where value might be in a span with class 'datatooltip'
                    value_elements = cells[1].find_elements(By.CSS_SELECTOR, 'span.datatooltip')
                    if value_elements:
                        value = value_elements[0].text.strip()
                    else:
                        value = cells[1].text.strip()
                    data['details'][key] = value
            except Exception as e:
                print(f"Error processing row: {e}")
                continue

        # Extract description
        try:
            desc_element = driver.find_element(By.CSS_SELECTOR, '.pro-descN')
            data['description'] = desc_element.text.strip()
        except NoSuchElementException:
            print(f"Description not found for {url}")
            data['description'] = 'N/A'

        # Extract seller information from cmpbox
        try:
            seller_box = driver.find_element(By.CSS_SELECTOR, '.cmpbox.verT.pd_flsh')
            
            # Extract seller location
            try:
                location_element = seller_box.find_element(By.CSS_SELECTOR, '.city-highlight')
                data['seller_info']['location'] = location_element.text.strip()
            except NoSuchElementException:
                data['seller_info']['location'] = 'N/A'
            
            # Extract seller name
            try:
                seller_name_element = seller_box.find_element(By.CSS_SELECTOR, 'h2.fs15')
                data['seller_info']['seller_name'] = seller_name_element.text.strip()
            except NoSuchElementException:
                data['seller_info']['seller_name'] = 'N/A'
            
            # Extract GST number
            try:
                gst_element = seller_box.find_element(By.CSS_SELECTOR, '.fs11.color1')
                data['seller_info']['gst_number'] = gst_element.text.strip()
            except NoSuchElementException:
                data['seller_info']['gst_number'] = 'N/A'
            
            # Extract TrustSEAL verification
            try:
                trustseal_element = seller_box.find_element(By.XPATH, "//*[contains(text(), 'TrustSEAL Verified')]")
                data['seller_info']['trustseal_verified'] = True
            except NoSuchElementException:
                data['seller_info']['trustseal_verified'] = False
            
            # Extract years of experience
            try:
                years_element = seller_box.find_element(By.XPATH, "//*[contains(text(), 'yrs')]")
                data['seller_info']['years_of_experience'] = years_element.text.strip()
            except NoSuchElementException:
                data['seller_info']['years_of_experience'] = 'N/A'
            
            # Extract rating
            try:
                rating_element = seller_box.find_element(By.CSS_SELECTOR, '.bo.color')
                data['seller_info']['rating'] = rating_element.text.strip()
            except NoSuchElementException:
                data['seller_info']['rating'] = 'N/A'
            
            # Extract number of reviews
            try:
                reviews_element = seller_box.find_element(By.CLASS_NAME, 'tcund')
                data['seller_info']['number_of_reviews'] = reviews_element.text.strip()
            except NoSuchElementException:
                data['seller_info']['number_of_reviews'] = 'N/A'
            
            # Extract response rate - FIXED SELECTOR
            try:
                response_rate_element = seller_box.find_element(By.XPATH, ".//*[contains(text(), 'Response Rate')]")
                data['seller_info']['response_rate'] = response_rate_element.text.strip()
            except NoSuchElementException:
                data['seller_info']['response_rate'] = 'N/A'

        except NoSuchElementException:
            print(f"Seller information (cmpbox) not found for {url}")
            data['seller_info'] = {'error': 'Seller information not available'}

        # Extract additional seller information from rdsp
        try:
            rdsp_box = driver.find_element(By.CSS_SELECTOR, '.rdsp')
            
            # Extract contact person name
            try:
                contact_person_element = rdsp_box.find_element(By.ID, 'supp_nm')
                data['seller_info']['contact_person'] = contact_person_element.text.strip()
            except NoSuchElementException:
                data['seller_info']['contact_person'] = 'N/A'
            
            # Extract full address
            try:
                address_element = rdsp_box.find_element(By.CSS_SELECTOR, '#g_img span.color1')
                data['seller_info']['full_address'] = address_element.text.strip()
            except NoSuchElementException:
                data['seller_info']['full_address'] = 'N/A'
            
            # Extract website URL
            try:
                website_element = rdsp_box.find_element(By.CSS_SELECTOR, 'a.color1.utd')
                data['seller_info']['website'] = website_element.get_attribute('href')
            except NoSuchElementException:
                data['seller_info']['website'] = 'N/A'

        except NoSuchElementException:
            print(f"Seller information (rdsp) not found for {url}")
            # Don't overwrite existing seller_info, just add note
            data['seller_info']['rdsp_info'] = 'Not available'

        # Extract company information from About the Company section
        try:
            about_section = driver.find_element(By.ID, 'aboutUs')
            
            # Extract company details
            try:
                detail_elements = about_section.find_elements(By.CSS_SELECTOR, '.lh21.pdinb.wid3.mb20.verT')
                for detail in detail_elements:
                    try:
                        label = detail.find_element(By.CSS_SELECTOR, '.on.color7').text.strip()
                        value = detail.find_element(By.CSS_SELECTOR, 'span:not(.on.color7)').text.strip()
                        data['company_info'][label.lower().replace(' ', '_')] = value
                    except NoSuchElementException:
                        continue
            except NoSuchElementException:
                print("Company details not found")
            
            # Extract company description
            try:
                desc_element = about_section.find_element(By.CSS_SELECTOR, '.companyDescBelow')
                data['company_info']['description'] = desc_element.text.strip()
            except NoSuchElementException:
                data['company_info']['description'] = 'N/A'

        except NoSuchElementException:
            print(f"About the Company section not found for {url}")
            data['company_info'] = {'error': 'Company information not available'}

        # Extract reviews from Ratings & Reviews section
        try:
            reviews_section = driver.find_element(By.ID, 'sellerRating')
            
            # Extract overall rating information
            try:
                overall_rating = reviews_section.find_element(By.CSS_SELECTOR, '.bo.fs30')
                data['reviews'].append({
                    'type': 'overall_rating',
                    'value': overall_rating.text.strip()
                })
            except NoSuchElementException:
                pass
            
            # Extract rating distribution - FIXED SELECTOR
            try:
                rating_bars = reviews_section.find_elements(By.CSS_SELECTOR, '.dsf.pd_aic.lh20')
                for bar in rating_bars:
                    try:
                        # Get the star rating text (e.g., "5★")
                        stars_text = bar.find_element(By.CSS_SELECTOR, 'span:first-child').text.strip()
                        
                        # Get the percentage text - look for the last span element
                        percentage_text = bar.find_elements(By.TAG_NAME, 'span')[-1].text.strip()
                        
                        data['reviews'].append({
                            'type': 'rating_distribution',
                            'stars': stars_text,
                            'percentage': percentage_text
                        })
                    except NoSuchElementException:
                        continue
            except NoSuchElementException:
                pass
            
            # Extract performance metrics
            try:
                performance_metrics = reviews_section.find_elements(By.CSS_SELECTOR, '.crlcrd')
                for metric in performance_metrics:
                    try:
                        title = metric.find_element(By.CSS_SELECTOR, '.title h2').text.strip()
                        value = metric.find_element(By.CSS_SELECTOR, '.number h3').text.strip()
                        data['reviews'].append({
                            'type': 'performance_metric',
                            'metric': title,
                            'value': value
                        })
                    except NoSuchElementException:
                        continue
            except NoSuchElementException:
                pass
            
            # Extract individual reviews - FIXED SELECTORS
            try:
                review_elements = reviews_section.find_elements(By.CSS_SELECTOR, '.brdE0b.pd15')
                for review in review_elements:
                    try:
                        # Extract rating
                        rating_element = review.find_element(By.CSS_SELECTOR, '.rtSml')
                        rating = rating_element.text.strip().replace('\n', ' ')
                        
                        # Extract reviewer information
                        reviewer_info = review.find_element(By.CSS_SELECTOR, '.pWdBk')
                        reviewer_name = reviewer_info.find_element(By.CSS_SELECTOR, '.color').text.strip()
                        
                        # Extract reviewer location (all text except the name)
                        reviewer_location_text = reviewer_info.find_element(By.CSS_SELECTOR, '.fs14.clr82').text.strip()
                        reviewer_location = reviewer_location_text.replace(reviewer_name, '').strip()
                        
                        # Extract review date and product
                        date_product = reviewer_info.find_element(By.CSS_SELECTOR, '.fs12.clr82').text.strip()
                        
                        # Extract review text
                        try:
                            review_text = review.find_element(By.CSS_SELECTOR, '.fs16.color.mt10').text.strip()
                        except NoSuchElementException:
                            review_text = ''
                        
                        # Extract response indicators
                        response_indicators = []
                        try:
                            indicators = review.find_elements(By.CSS_SELECTOR, '.pfsh.inRqd p')
                            for indicator in indicators:
                                response_indicators.append(indicator.text.strip())
                        except NoSuchElementException:
                            pass
                        
                        data['reviews'].append({
                            'type': 'individual_review',
                            'rating': rating,
                            'reviewer_name': reviewer_name,
                            'reviewer_location': reviewer_location,
                            'date_and_product': date_product,
                            'review_text': review_text,
                            'response_indicators': response_indicators
                        })
                    except NoSuchElementException:
                        continue
            except NoSuchElementException:
                print("Individual reviews not found")

        except NoSuchElementException:
            print(f"Ratings & Reviews section not found for {url}")
            data['reviews'] = [{'error': 'Reviews not available'}]

    except TimeoutException:
        print(f"Timeout waiting for table on {url}")
    except Exception as e:
        print(f"Error scraping {url}: {e}")

    all_products.append(data)
    
    # Save progress after each product (optional)
    if (index + 1) % 5 == 0:
        with open(fn+'.json', 'w', encoding='utf-8') as f:
            json.dump(all_products, f, indent=4, ensure_ascii=False)
        print(f"Saved progress after {index+1} products")

# Save all products to a single JSON file
with open('all_products.json', 'w',encoding='utf-8') as f:
    json.dump(all_products, f, indent=4, ensure_ascii=False)

print(f"Saved all product details for {len(all_products)} products to 'all_products.json'.")

driver.quit()