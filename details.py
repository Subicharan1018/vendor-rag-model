import json
import csv
import time
import os
from multiprocessing import Pool
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

def scrape_product(item):
    # Set up Selenium with Chrome for each process
    service = Service()
    options = webdriver.ChromeOptions()
    # Uncomment the next line for headless mode
    # options.add_argument('--headless')
    driver = webdriver.Chrome(service=service, options=options)
    
    url = item['href']
    title = item['title']
    print(f"Scraping: {title} (Process {os.getpid()})")
    
    driver.get(url)
    time.sleep(3)  # Wait for page to load

    # Initialize data dictionary
    data = {
        'url': url,
        'title': title,
        'price': 'N/A',
        'price_unit': 'N/A',
        'details': {},
        'description': 'N/A',
        'seller_info': {},
        'company_info': {},
        'reviews': []
    }

    try:
        # Extract price information
        try:
            price_element = driver.find_element(By.ID, 'askprice_pg-1')
            price_text = price_element.find_element(By.CLASS_NAME, 'price-unit').text
            price_value = ''.join(filter(str.isdigit, price_text))
            data['price'] = price_value if price_value else 'N/A'
            
            try:
                unit_element = price_element.find_element(By.CLASS_NAME, 'units')
                data['price_unit'] = unit_element.text.strip()
            except NoSuchElementException:
                data['price_unit'] = 'N/A'
        except NoSuchElementException:
            print(f"Price information not found for {url}")
            data['price'] = 'N/A'
            data['price_unit'] = 'N/A'

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
                    value_elements = cells[1].find_elements(By.CSS_SELECTOR, 'span.datatooltip')
                    if value_elements:
                        value = value_elements[0].text.strip()
                    else:
                        value = cells[1].text.strip()
                    data['details'][key] = value
            except Exception as e:
                print(f"Error processing row for {url}: {e}")
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
            
            try:
                location_element = seller_box.find_element(By.CSS_SELECTOR, '.city-highlight')
                data['seller_info']['location'] = location_element.text.strip()
            except NoSuchElementException:
                data['seller_info']['location'] = 'N/A'
            
            try:
                seller_name_element = seller_box.find_element(By.CSS_SELECTOR, 'h2.fs15')
                data['seller_info']['seller_name'] = seller_name_element.text.strip()
            except NoSuchElementException:
                data['seller_info']['seller_name'] = 'N/A'
            
            try:
                gst_element = seller_box.find_element(By.CSS_SELECTOR, '.fs11.color1')
                data['seller_info']['gst_number'] = gst_element.text.strip()
            except NoSuchElementException:
                data['seller_info']['gst_number'] = 'N/A'
            
            try:
                trustseal_element = seller_box.find_element(By.XPATH, "//*[contains(text(), 'TrustSEAL Verified')]")
                data['seller_info']['trustseal_verified'] = True
            except NoSuchElementException:
                data['seller_info']['trustseal_verified'] = False
            
            try:
                years_element = seller_box.find_element(By.XPATH, "//*[contains(text(), 'yrs')]")
                data['seller_info']['years_of_experience'] = years_element.text.strip()
            except NoSuchElementException:
                data['seller_info']['years_of_experience'] = 'N/A'
            
            try:
                rating_element = seller_box.find_element(By.CSS_SELECTOR, '.bo.color')
                data['seller_info']['rating'] = rating_element.text.strip()
            except NoSuchElementException:
                data['seller_info']['rating'] = 'N/A'
            
            try:
                reviews_element = seller_box.find_element(By.CLASS_NAME, 'tcund')
                data['seller_info']['number_of_reviews'] = reviews_element.text.strip()
            except NoSuchElementException:
                data['seller_info']['number_of_reviews'] = 'N/A'
            
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
            
            try:
                contact_person_element = rdsp_box.find_element(By.ID, 'supp_nm')
                data['seller_info']['contact_person'] = contact_person_element.text.strip()
            except NoSuchElementException:
                data['seller_info']['contact_person'] = 'N/A'
            
            try:
                address_element = rdsp_box.find_element(By.CSS_SELECTOR, '#g_img span.color1')
                data['seller_info']['full_address'] = address_element.text.strip()
            except NoSuchElementException:
                data['seller_info']['full_address'] = 'N/A'
            
            try:
                website_element = rdsp_box.find_element(By.CSS_SELECTOR, 'a.color1.utd')
                data['seller_info']['website'] = website_element.get_attribute('href')
            except NoSuchElementException:
                data['seller_info']['website'] = 'N/A'

        except NoSuchElementException:
            print(f"Seller information (rdsp) not found for {url}")
            data['seller_info']['rdsp_info'] = 'Not available'

        # Extract company information from About the Company section
        try:
            about_section = driver.find_element(By.ID, 'aboutUs')
            
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
            
            try:
                overall_rating = reviews_section.find_element(By.CSS_SELECTOR, '.bo.fs30')
                data['reviews'].append({
                    'type': 'overall_rating',
                    'value': overall_rating.text.strip()
                })
            except NoSuchElementException:
                pass
            
            try:
                rating_bars = reviews_section.find_elements(By.CSS_SELECTOR, '.dsf.pd_aic.lh20')
                for bar in rating_bars:
                    try:
                        stars_text = bar.find_element(By.CSS_SELECTOR, 'span:first-child').text.strip()
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
            
            try:
                review_elements = reviews_section.find_elements(By.CSS_SELECTOR, '.brdE0b.pd15')
                for review in review_elements:
                    try:
                        rating_element = review.find_element(By.CSS_SELECTOR, '.rtSml')
                        rating = rating_element.text.strip().replace('\n', ' ')
                        reviewer_info = review.find_element(By.CSS_SELECTOR, '.pWdBk')
                        reviewer_name = reviewer_info.find_element(By.CSS_SELECTOR, '.color').text.strip()
                        reviewer_location_text = reviewer_info.find_element(By.CSS_SELECTOR, '.fs14.clr82').text.strip()
                        reviewer_location = reviewer_location_text.replace(reviewer_name, '').strip()
                        date_product = reviewer_info.find_element(By.CSS_SELECTOR, '.fs12.clr82').text.strip()
                        try:
                            review_text = review.find_element(By.CSS_SELECTOR, '.fs16.color.mt10').text.strip()
                        except NoSuchElementException:
                            review_text = ''
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

    driver.quit()
    return data

def main():
    # Read the links.csv file
    links_data = []
    with open('indiamart_anchor_links.csv', 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            links_data.append(row)

    # Split links_data into four chunks
    num_processes = 4
    chunk_size = len(links_data) // num_processes
    chunks = [links_data[i:i + chunk_size] for i in range(0, len(links_data), chunk_size)]
    
    # Adjust the last chunk to include any remaining items
    if len(chunks) > num_processes:
        chunks[-2].extend(chunks[-1])
        chunks.pop()

    # Create a process pool and scrape in parallel
    with Pool(processes=num_processes) as pool:
        results = pool.map(scrape_product, chunks[0] + chunks[1] + chunks[2] + chunks[3])

    # Combine results
    all_products = []
    for result in results:
        all_products.append(result)

    # Save all products to a single JSON file
    with open('all_products.json', 'w', encoding='utf-8') as f:
        json.dump(all_products, f, indent=4, ensure_ascii=False)

    print(f"Saved all product details for {len(all_products)} products to 'all_products.json'.")

if __name__ == '__main__':
    main()