
from fastapi import FastAPI, HTTPException, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import csv
import re
from collections import Counter
import pdfplumber
import io
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# FastAPI app
app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # React app URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database setup - Using SQLite for easier setup
DATABASE_URL = "sqlite:///./jobs.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# SQLAlchemy Models
class Job(Base):
    __tablename__ = "jobs"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    company = Column(String)
    location = Column(String)
    salary = Column(String)
    link = Column(String, unique=True)
    description = Column(Text, nullable=True)
    posted_date = Column(DateTime, default=datetime.utcnow)
    source = Column(String, default="myjob.mu")
    sector = Column(String)

class CV(Base):
    __tablename__ = "cvs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer)
    skills = Column(Text)
    uploaded_at = Column(DateTime, default=datetime.utcnow)

# Create tables
Base.metadata.create_all(bind=engine)

# Pydantic Models
class JobBase(BaseModel):
    title: str
    company: str
    location: str
    salary: str
    link: str
    description: Optional[str] = None
    posted_date: datetime
    source: str
    sector: Optional[str] = None

class JobCreate(JobBase):
    pass

class JobResponse(JobBase):
    id: int
    class Config:
        from_attributes = True

class CVUpload(BaseModel):
    user_id: int
    skills: str

class CVMatchResponse(BaseModel):
    job_id: int
    job_title: str
    company: str
    match_score: float

# Helper functions
def parse_salary(salary: str) -> Optional[float]:
    if salary in ["Not disclosed", "Negotiable", "See description"]:
        return None
    try:
        numbers = re.findall(r'\d{1,3}(?:,\d{3})*', salary)
        return float(numbers[0].replace(',', '')) if numbers else None
    except:
        return None

def extract_skills_from_pdf(pdf_file: UploadFile) -> str:
    try:
        logger.info(f"Processing PDF: {pdf_file.filename}")
        with pdfplumber.open(pdf_file.file) as pdf:
            text = ""
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        
        if not text:
            logger.warning("No text extracted from PDF")
            return "no skills detected"
        
        # Normalize text
        text = re.sub(r'[^\w\s,]', '', text.lower())
        logger.info(f"Extracted text (first 100 chars): {text[:100]}")
        
        # Common skills list
        common_skills = [
            'python', 'sql', 'javascript', 'java', 'html', 'css', 'web development',
            'data analysis', 'machine learning', 'network', 'cybersecurity', 'cloud',
            'database', 'devops', 'frontend', 'backend', 'software development'
        ]
        found_skills = []
        
        # Check for "skills" section
        skills_section = re.search(r'skills[:\s]*(.*?)(?:\n\n|\Z)', text, re.DOTALL)
        if skills_section:
            skills_text = skills_section.group(1)
            found_skills.extend(skill for skill in common_skills if skill in skills_text)
            logger.info(f"Skills from skills section: {found_skills}")
        
        # Check entire text for skills
        for skill in common_skills:
            if skill in text and skill not in found_skills:
                found_skills.append(skill)
        
        skills = ", ".join(found_skills) if found_skills else "no skills detected"
        logger.info(f"Final extracted skills: {skills}")
        return skills
    except Exception as e:
        logger.error(f"Error processing PDF: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Error processing PDF: {str(e)}")

def calculate_match_score(cv_skills: str, job_title: str, job_description: Optional[str]) -> float:
    # Normalize inputs: lowercase, remove punctuation
    def normalize_text(text: str) -> set:
        if not text:
            return set()
        text = re.sub(r'[^\w\s]', '', text.lower())
        return set(text.split())

    # Parse CV skills
    cv_skills_set = set(skill.strip().lower() for skill in cv_skills.split(','))
    if not cv_skills_set:
        return 0.0

    # Parse job text (title and description)
    job_title_set = normalize_text(job_title)
    job_description_set = normalize_text(job_description) if job_description else set()

    # Calculate matches
    title_matches = len(cv_skills_set.intersection(job_title_set))
    description_matches = len(cv_skills_set.intersection(job_description_set))

    # Weighted score: 30% title, 70% description (if available)
    total_job_words = len(job_title_set) + len(job_description_set)
    if total_job_words == 0:
        return 0.0

    title_weight = 0.3
    description_weight = 0.7 if job_description else 0.0
    total_matches = title_matches + description_matches
    if total_matches == 0:
        return 0.0

    # Normalize by number of CV skills
    match_score = (title_matches * title_weight + description_matches * description_weight) / len(cv_skills_set) * 100
    return min(match_score, 100.0)

# Load jobs from CSV
def load_jobs_from_csv():
    CSV_FILE = "jobs.csv"
    db = SessionLocal()
    batch_size = 100
    batch = []
    try:
        with open(CSV_FILE, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            if next(reader, None):  # Skip header if present
                f.seek(0)
                reader = csv.DictReader(f)
            logger.info("CSV Headers: %s", reader.fieldnames)
            for i, row in enumerate(reader):
                clean_title = re.sub(r'[\u200b-\u200f\u202a-\u202e]', '', row["title"]).strip()
                logger.debug("Row %d: %s", i+1, {**row, "title": clean_title})
                if db.query(Job).filter(Job.link == row["link"]).first():
                    logger.info("Skipping duplicate job: %s (%s)", clean_title, row['link'])
                    continue
                db_job = Job(
                    title=clean_title,
                    company=row["company"],
                    location=row["location"],
                    salary=row["salary"],
                    link=row["link"],
                    description=row.get("description"),
                    posted_date=datetime.fromisoformat(row["posted_date"]) if row.get("posted_date") else datetime.utcnow(),
                    source=row.get("source", "myjob.mu"),
                    sector=row.get("sector", "Other")
                )
                batch.append(db_job)
                if len(batch) >= batch_size:
                    db.add_all(batch)
                    try:
                        db.commit()
                        logger.info("Committed batch of %d jobs", len(batch))
                    except Exception as e:
                        logger.error("Error inserting batch: %s", e)
                        db.rollback()
                    batch = []
        if batch:
            db.add_all(batch)
            try:
                db.commit()
                logger.info("Committed final batch of %d jobs", len(batch))
            except Exception as e:
                logger.error("Error inserting final batch: %s", e)
                db.rollback()
    except FileNotFoundError:
        logger.error("CSV file %s not found.", CSV_FILE)
    except Exception as e:
        logger.error("Error loading CSV: %s", e)
    finally:
        db.close()

# API Endpoints
@app.on_event("startup")
async def startup_event():
    load_jobs_from_csv()

@app.post("/jobs", response_model=JobResponse)
async def create_job(job: JobCreate):
    db = SessionLocal()
    try:
        if db.query(Job).filter(Job.link == job.link).first():
            raise HTTPException(status_code=400, detail="Job with this link already exists")
        db_job = Job(**job.dict())
        db.add(db_job)
        db.commit()
        db.refresh(db_job)
        return db_job
    finally:
        db.close()

@app.get("/jobs", response_model=List[JobResponse])
async def get_jobs(offset: int = 0, limit: int = 100):
    db = SessionLocal()
    try:
        jobs = db.query(Job).offset(offset).limit(limit).all()
        return jobs
    finally:
        db.close()

@app.get("/filter", response_model=List[JobResponse])
async def filter_jobs(location: Optional[str] = None, min_salary: Optional[float] = None, job_type: Optional[str] = None, sector: Optional[str] = None, offset: int = 0, limit: int = 100):
    db = SessionLocal()
    try:
        query = db.query(Job)
        if location:
            query = query.filter(Job.location.ilike(f"%{location}%"))
        if sector:
            query = query.filter(Job.sector == sector)
        if job_type:
            query = query.filter(Job.title.ilike(f"%{job_type}%"))
        if min_salary:
            # Apply salary filter last
            jobs = query.all()
            filtered_jobs = []
            for job in jobs:
                if job.salary not in ["Not disclosed", "Negotiable", "See description"]:
                    salary_num = parse_salary(job.salary)
                    if salary_num and salary_num >= min_salary:
                        filtered_jobs.append(job)
            return filtered_jobs[offset:offset+limit]
        return query.offset(offset).limit(limit).all()
    finally:
        db.close()

@app.post("/cv-upload", response_model=List[CVMatchResponse])
async def upload_cv(cv: CVUpload):
    db = SessionLocal()
    try:
        db_cv = CV(user_id=cv.user_id, skills=cv.skills)
        db.add(db_cv)
        db.commit()
        jobs = db.query(Job).all()
        matches = []
        for job in jobs:
            match_score = calculate_match_score(cv.skills, job.title, job.description)
            if match_score > 0:
                matches.append(CVMatchResponse(
                    job_id=job.id,
                    job_title=job.title,
                    company=job.company,
                    match_score=match_score
                ))
        return sorted(matches, key=lambda x: x.match_score, reverse=True)[:10]
    finally:
        db.close()

@app.post("/cv-upload-pdf", response_model=List[CVMatchResponse])
async def upload_cv_pdf(user_id: int = Form(...), file: UploadFile = File(...)):
    if not file.filename.endswith('.pdf'):
        logger.error("Invalid file type uploaded: %s", file.filename)
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")
    
    db = SessionLocal()
    try:
        logger.info("Received CV upload for user_id: %d", user_id)
        # Extract skills from PDF
        skills = extract_skills_from_pdf(file)
        
        # Store CV in database
        db_cv = CV(user_id=user_id, skills=skills)
        db.add(db_cv)
        db.commit()
        logger.info("Stored CV with skills: %s", skills)
        
        # Match against jobs
        jobs = db.query(Job).all()
        matches = []
        for job in jobs:
            match_score = calculate_match_score(skills, job.title, job.description)
            if match_score > 0:
                matches.append(CVMatchResponse(
                    job_id=job.id,
                    job_title=job.title,
                    company=job.company,
                    match_score=match_score
                ))
        logger.info("Found %d matching jobs", len(matches))
        return sorted(matches, key=lambda x: x.match_score, reverse=True)[:10]
    except Exception as e:
        logger.error("Error in cv-upload-pdf: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")
    finally:
        db.close()

@app.get("/stats")
async def get_stats():
    db = SessionLocal()
    try:
        jobs = db.query(Job).all()
        company_counts = Counter(job.company for job in jobs)
        location_counts = Counter(job.location for job in jobs)
        salary_ranges = Counter(job.salary for job in jobs if job.salary not in ["Not disclosed", "Negotiable", "See description"])
        sector_counts = Counter(job.sector for job in jobs)
        return {
            "total_jobs": len(jobs),
            "companies": company_counts.most_common(5),
            "locations": location_counts.most_common(5),
            "salary_ranges": salary_ranges.most_common(5),
            "sectors": sector_counts.most_common(5)
        }
    finally:
        db.close()