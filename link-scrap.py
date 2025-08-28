from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import csv
import time

# Set up Selenium with Chrome (replace with your chromedriver path if needed)
service = Service()  # Assumes chromedriver in PATH
options = webdriver.ChromeOptions()
options.add_argument('--headless')  # Run without UI for efficiency
driver = webdriver.Chrome(service=service, options=options)

# The search URL
search_url = "https://dir.indiamart.com/search.mp?ss=rebar+steel&mcatid=119126&catid=53&v=4&sref=as-rcnt%7Ckwd%3Dce+%7Cpos%3D1%7Ccat%3D-2%7Cmcat%3D-2%7Ckwd_len%3D3%7Ckwd_cnt%3D2&cityid=&prdsrc=1&tags=res:RC3|ktp:N0|stype:attr=1|mtp:S|wc:2|lcf:-1|qr_nm:gd|cs:14741|com-cf:nl|ptrs:na|mc:42729|cat:795|qry_typ:P|lang:en|flavl:0-1|rtn:0-0-0-0-4-5-1|qrd:250826|mrd:250826|prdt:250826|gli:G1I2"

# Navigate to search page
driver.get(search_url)
time.sleep(3)  # Wait for dynamic load

# Find all card links (adjust selector if class changes)
try:
    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CLASS_NAME, 'cardlinks')))
except:
    print("No card links found or timeout.")
    driver.quit()
    exit()

card_links = driver.find_elements(By.CLASS_NAME, 'cardlinks')

# Extract href and text, save to CSV
links_data = []
for link in card_links:
    href = link.get_attribute('href')
    text = link.text.strip()
    if href and 'proddetail' in href:  # Filter for product details
        links_data.append({'href': href, 'title': text})

with open('rebar.csv', 'w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=['href', 'title'])
    writer.writeheader()
    writer.writerows(links_data)

print(f"Extracted {len(links_data)} links to 'links.csv'.")

# Now scrape each product page
products_data = []
for item in links_data:
    driver.get(item['href'])
    time.sleep(2)  # Wait for load
    
    # Scrape key elements (adjust selectors based on page structure; inspect elements)
    try:
        name = driver.find_element(By.CSS_SELECTOR, 'h1.prodname').text.strip()  # Product name
    except:
        name = 'N/A'
    
    try:
        price = driver.find_element(By.CSS_SELECTOR, '.price').text.strip()  # Price
    except:
        price = 'N/A'
    
    try:
        description = driver.find_element(By.CSS_SELECTOR, '.proddesc').text.strip()  # Description
    except:
        description = 'N/A'
    
    try:
        seller = driver.find_element(By.CSS_SELECTOR, '.seller-name').text.strip()  # Seller
    except:
        seller = 'N/A'
    
    products_data.append({
        'href': item['href'],
        'name': name,
        'price': price,
        'description': description,
        'seller': seller
    })

print("Scraped product details to 'products.csv'.")

driver.quit()