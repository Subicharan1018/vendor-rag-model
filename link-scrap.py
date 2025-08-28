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
search_url = "https://dir.indiamart.com/search.mp?ss=ht+switchgear+panel&mcatid=162&catid=72&v=4&cityid=70627&prdsrc=1&src=as-popular%7Ckwd%3DHT+switchgear%7Cpos%3D1%7Ccat%3D72%7Cmcat%3D162%7Ckwd_len%3D13%7Ckwd_cnt%3D2&cq=navi+mumbai&tags=res:RC3|ktp:N0|stype:attr=1|mtp:G|wc:3|lcf:3|cq:navi%20mumbai|qr_nm:gl-gd|cs:17336|com-cf:nl|ptrs:na|mc:2869|cat:591|qry_typ:P|lang:en|rtn:3-0-0-0-2-3-2|tyr:2|qrd:250825|mrd:250828|prdt:250828|pfen:1|gli:G1I2"
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

with open('links.csv', 'w', newline='', encoding='utf-8') as f:
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