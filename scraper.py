from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import csv
import os
import time
import re
from datetime import datetime
from collections import Counter

BASE_URL = "https://www.myjob.mu/ShowResults.aspx?Keywords=&Location=&Cat=22"
CSV_FILE = "C:/Users/nahee/Downloads/fortomorrow/Web_Scrappingg/Web_Scrapping/jobs.csv"

def clean_text(text):
    if not isinstance(text, str):
        return str(text)
    return re.sub(r'[\u200b-\u200f\u202a-\u202e]', '', text).strip()

def infer_sector(title):
    title = title.lower()
    hospitality_keywords = r'\b(waiter|waitress|chef|hostess|sommelier|bellboy|receptionist|guest service|hotel|resort|restaurant|food|beverage|catering|hospitality|barista|bartender|housekeeping|concierge|front desk|kitchen|culinary|server|banquet|event manager|spa|tourism|guest relations|food service|chef de rang|outlet supervisor)\b'
    finance_keywords = r'\b(account|finance|financial|payroll|auditor|banking|tax|compliance|accounts officer|accountant|bookkeeper|controller|treasurer|financial analyst|credit|investment|budget|fiscal|ledger|actuary|insurance|risk|underwriter|billing)\b'
    it_keywords = r'\b(developer|programmer|software|coder|engineer|devops|full stack|frontend|backend|web developer|app developer|application developer|data|bi|business intelligence|data scientist|data analyst|data engineer|machine learning|ai|artificial intelligence|analytics|it|network|system|sysadmin|administrator|infrastructure|cloud|server|database|dba|cybersecurity|infosec|information security|penetration tester|ethical hacker|architect|solution architect|enterprise architect|technical architect|system architect|test|tester|qa|quality assurance|test engineer|automation engineer|technician|computer|it support|helpdesk|support engineer|technical support|blockchain|iot|internet of things|augmented reality|ar|vr|virtual reality|it manager|it consultant|project manager|scrum master|agile coach|systems analyst|software architect|cloud engineer|network engineer|it specialist|data architect|machine learning engineer|ai specialist|cybersecurity analyst|it coordinator|tech lead|sre|site reliability|software developer|ui developer|ux developer|api developer)\b'
    healthcare_keywords = r'\b(nurse|doctor|pharmacist|medical|health|therapist|physician|surgeon|dentist|radiologist|lab technician|healthcare|clinical|paramedic|caregiver|health officer|nursing|midwife|anesthetist|dietitian)\b'
    retail_keywords = r'\b(sales|cashier|store|merchandiser|retail|shop|sales associate|sales executive|sales consultant|store manager|retail manager|visual merchandiser|customer service|shop assistant|sales team leader|inventory)\b'
    admin_keywords = r'\b(administrative|admin|secretary|receptionniste|clerk|coordinator|human resources|hr|manager paie|team manager|governance|officer|office manager|executive assistant|data entry|reception|administrator|operations|compliance officer|payroll officer|hr officer|program coordinator|governance professional|stock administrator|stock controller)\b'
    technical_keywords = r'\b(electrician|carpenter|hvac|maintenance|repair|mechanic|plumber|technician|engineer|technical|maintenance manager|facilities|installation|service technician|refrigeration|air conditioning|technical assistant)\b'
    other_keywords = r'\b(driver|security|helper|purchasing|consultant|trainer|specialist|liaison|logistics|warehouse|delivery|travel|instructor|facilitator|advisor|agent|guard|procurement|supply chain|corporate trainer|fashion designer)\b'

    if re.search(hospitality_keywords, title): return 'Hospitality'
    elif re.search(finance_keywords, title): return 'Finance'
    elif re.search(it_keywords, title): return 'IT'
    elif re.search(healthcare_keywords, title): return 'Healthcare'
    elif re.search(retail_keywords, title): return 'Retail'
    elif re.search(admin_keywords, title): return 'Administration'
    elif re.search(technical_keywords, title): return 'Technical'
    return 'Other'

def run_scraper():
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    fieldnames = ["title", "company", "location", "salary", "link", "description", "posted_date", "source", "sector"]
    
    # Ensure CSV has headers
    os.makedirs(os.path.dirname(CSV_FILE), exist_ok=True)
    if not os.path.exists(CSV_FILE) or os.path.getsize(CSV_FILE) == 0:
        with open(CSV_FILE, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
    
    existing_links = set()
    try:
        with open(CSV_FILE, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if "link" in row:
                    existing_links.add(row["link"])
    except FileNotFoundError:
        print(f"CSV file {CSV_FILE} not found, starting fresh.")
    
    jobs = []
    page = 1
    new_jobs = 0
    while page <= 39:
        url = f"{BASE_URL}&Page={page}"
        print(f"Scraping page {page}...")
        driver.get(url)
        time.sleep(3)
        soup = BeautifulSoup(driver.page_source, "html.parser")
        job_cards = soup.select("div.module.job-result")
        if not job_cards:
            print("No more jobs found.")
            break
        
        for job in job_cards:
            title_tag = job.select_one("h2[itemprop=title] > a")
            company_tag = job.select_one("h3[itemprop=name] > a[itemprop=hiringOrganization]")
            salary_tag = job.select_one("li[itemprop=baseSalary].salary")
            location_tag = job.select_one("li[itemprop=jobLocation].location > a")
            description_tag = job.select_one("div[itemprop=description]")
            date_tag = job.select_one("li.date-posted > time")
            
            title = clean_text(title_tag.text) if title_tag else "N/A"
            href = title_tag["href"] if title_tag else ""
            link = "https://www.myjob.mu" + href if href else "N/A"
            if link in existing_links:
                print(f"Skipped duplicate: {title} ({link})")
                continue
            company = clean_text(company_tag.text) if company_tag else "Not Specified"
            location = clean_text(location_tag.text) if location_tag else "Not Specified"
            salary = clean_text(salary_tag.text) if salary_tag else "Not Specified"
            description = clean_text(description_tag.text) if description_tag else None
            posted_date = date_tag["datetime"] if date_tag else datetime.utcnow().isoformat()
            source = "myjob.mu"
            sector = infer_sector(title)
            
            job = {
                "title": title, "company": company, "location": location,
                "salary": salary, "link": link, "description": description,
                "posted_date": posted_date, "source": source, "sector": sector
            }
            jobs.append(job)
            existing_links.add(link)
            new_jobs += 1
            print(f"Added: {title} at {company} ({link})")
        
        page += 1
        time.sleep(1)
    
    driver.quit()
    
    # Write to CSV
    with open(CSV_FILE, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        for job in jobs:
            writer.writerow(job)
    
    print(f"Done! {new_jobs} new jobs saved to '{CSV_FILE}'.")
    return jobs  # Return jobs for database insertion