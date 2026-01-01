"""
Health Trends Evidence Tracker API
FastAPI application for querying health trends and their evidence scores.

Run locally:
    uvicorn api:app --reload

Run in production:
    uvicorn api:app --host 0.0.0.0 --port $PORT
"""

import os
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

import asyncpg

load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL')

# =============================================================================
# Database Connection
# =============================================================================

# Global connection pool
db_pool: Optional[asyncpg.Pool] = None


async def get_pool() -> asyncpg.Pool:
    """Get the database connection pool"""
    global db_pool
    if db_pool is None:
        raise HTTPException(status_code=503, detail="Database not connected")
    return db_pool


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage database connection lifecycle"""
    global db_pool
    
    # Startup
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL environment variable not set")
    
    print("Connecting to database...")
    db_pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
    print("✓ Database connected")
    
    yield
    
    # Shutdown
    if db_pool:
        await db_pool.close()
        print("✓ Database disconnected")


# =============================================================================
# Pydantic Models (Response Schemas)
# =============================================================================

class CategoryOut(BaseModel):
    id: int
    name: str
    description: Optional[str]
    icon: Optional[str]


class TrendSummary(BaseModel):
    id: int
    name: str
    slug: str
    category: Optional[str]
    overall_score: Optional[float]
    evidence_grade: Optional[str]
    description: Optional[str]


class ClaimOut(BaseModel):
    id: int
    claim_text: str
    claim_slug: str
    evidence_score: Optional[float]
    evidence_grade: Optional[str]
    summary: Optional[str]
    num_human_rcts: int
    num_meta_analyses: int
    is_primary_claim: bool


class StudyOut(BaseModel):
    pubmed_id: str
    title: str
    journal: Optional[str]
    publication_year: Optional[int]
    study_type: Optional[str]
    is_human_study: bool
    sample_size: Optional[int]
    supports_claim: Optional[str]


class TrendDetail(BaseModel):
    id: int
    name: str
    slug: str
    category: Optional[str]
    description: Optional[str]
    aliases: Optional[list[str]]
    overall_score: Optional[float]
    evidence_grade: Optional[str]
    confidence_level: Optional[str]
    claims: list[ClaimOut]


class ClaimDetail(BaseModel):
    id: int
    claim_text: str
    claim_slug: str
    evidence_score: Optional[float]
    evidence_grade: Optional[str]
    summary: Optional[str]
    detailed_analysis: Optional[str]
    num_human_rcts: int
    num_meta_analyses: int
    num_observational: int
    num_animal_studies: int
    studies: list[StudyOut]


class SearchResult(BaseModel):
    trends: list[TrendSummary]
    total: int
    query: str


class StatsOut(BaseModel):
    total_trends: int
    total_claims: int
    total_studies: int
    trends_by_category: dict[str, int]
    grade_distribution: dict[str, int]


# =============================================================================
# FastAPI App
# =============================================================================

app = FastAPI(
    title="Health Trends Evidence Tracker",
    description="API for querying scientific evidence behind health supplements, devices, and protocols.",
    version="1.0.0",
    lifespan=lifespan
)

# CORS - allow frontend to call API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict this to your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# Endpoints
# =============================================================================

@app.get("/", tags=["Health"])
async def root():
    """API health check"""
    return {
        "status": "ok",
        "message": "Health Trends Evidence Tracker API",
        "docs": "/docs"
    }


@app.get("/stats", response_model=StatsOut, tags=["Stats"])
async def get_stats():
    """Get overall database statistics"""
    pool = await get_pool()
    
    async with pool.acquire() as conn:
        total_trends = await conn.fetchval("SELECT COUNT(*) FROM trends WHERE is_published = TRUE")
        total_claims = await conn.fetchval("SELECT COUNT(*) FROM claims")
        total_studies = await conn.fetchval("SELECT COUNT(*) FROM studies")
        
        # Trends by category
        cat_rows = await conn.fetch("""
            SELECT c.name, COUNT(t.id) as count
            FROM categories c
            LEFT JOIN trends t ON c.id = t.category_id AND t.is_published = TRUE
            GROUP BY c.name
            ORDER BY count DESC
        """)
        trends_by_category = {row['name']: row['count'] for row in cat_rows}
        
        # Grade distribution
        grade_rows = await conn.fetch("""
            SELECT evidence_grade, COUNT(*) as count
            FROM trends
            WHERE is_published = TRUE AND evidence_grade IS NOT NULL
            GROUP BY evidence_grade
        """)
        grade_distribution = {row['evidence_grade']: row['count'] for row in grade_rows}
    
    return StatsOut(
        total_trends=total_trends,
        total_claims=total_claims,
        total_studies=total_studies,
        trends_by_category=trends_by_category,
        grade_distribution=grade_distribution
    )


# -----------------------------------------------------------------------------
# Categories
# -----------------------------------------------------------------------------

@app.get("/categories", response_model=list[CategoryOut], tags=["Categories"])
async def list_categories():
    """Get all categories"""
    pool = await get_pool()
    
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT id, name, description, icon
            FROM categories
            ORDER BY name
        """)
    
    return [CategoryOut(**dict(row)) for row in rows]


# -----------------------------------------------------------------------------
# Trends
# -----------------------------------------------------------------------------

@app.get("/trends", response_model=list[TrendSummary], tags=["Trends"])
async def list_trends(
    category: Optional[str] = Query(None, description="Filter by category name"),
    min_score: Optional[float] = Query(None, ge=0, le=10, description="Minimum evidence score"),
    max_score: Optional[float] = Query(None, ge=0, le=10, description="Maximum evidence score"),
    grade: Optional[str] = Query(None, description="Filter by grade (A, B, C, D, F)"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    """
    List all published trends with optional filters.
    """
    pool = await get_pool()
    
    query = """
        SELECT t.id, t.name, t.slug, c.name as category, 
               t.overall_score, t.evidence_grade, t.description
        FROM trends t
        LEFT JOIN categories c ON t.category_id = c.id
        WHERE t.is_published = TRUE
    """
    params = []
    param_count = 0
    
    if category:
        param_count += 1
        query += f" AND c.name ILIKE ${param_count}"
        params.append(f"%{category}%")
    
    if min_score is not None:
        param_count += 1
        query += f" AND t.overall_score >= ${param_count}"
        params.append(min_score)
    
    if max_score is not None:
        param_count += 1
        query += f" AND t.overall_score <= ${param_count}"
        params.append(max_score)
    
    if grade:
        param_count += 1
        query += f" AND t.evidence_grade LIKE ${param_count}"
        params.append(f"{grade.upper()}%")
    
    query += " ORDER BY t.name"
    query += f" LIMIT ${param_count + 1} OFFSET ${param_count + 2}"
    params.extend([limit, offset])
    
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
    
    return [TrendSummary(**dict(row)) for row in rows]


@app.get("/trends/{slug}", response_model=TrendDetail, tags=["Trends"])
async def get_trend(slug: str):
    """
    Get detailed information about a specific trend, including all its claims.
    """
    pool = await get_pool()
    
    async with pool.acquire() as conn:
        # Get trend
        trend_row = await conn.fetchrow("""
            SELECT t.id, t.name, t.slug, c.name as category, t.description,
                   t.aliases, t.overall_score, t.evidence_grade, t.confidence_level
            FROM trends t
            LEFT JOIN categories c ON t.category_id = c.id
            WHERE t.slug = $1 AND t.is_published = TRUE
        """, slug)
        
        if not trend_row:
            raise HTTPException(status_code=404, detail=f"Trend '{slug}' not found")
        
        # Get claims for this trend
        claim_rows = await conn.fetch("""
            SELECT id, claim_text, claim_slug, evidence_score, evidence_grade,
                   summary, num_human_rcts, num_meta_analyses, is_primary_claim
            FROM claims
            WHERE trend_id = $1
            ORDER BY is_primary_claim DESC, evidence_score DESC NULLS LAST
        """, trend_row['id'])
    
    claims = [ClaimOut(
        id=row['id'],
        claim_text=row['claim_text'],
        claim_slug=row['claim_slug'],
        evidence_score=row['evidence_score'],
        evidence_grade=row['evidence_grade'],
        summary=row['summary'],
        num_human_rcts=row['num_human_rcts'] or 0,
        num_meta_analyses=row['num_meta_analyses'] or 0,
        is_primary_claim=row['is_primary_claim']
    ) for row in claim_rows]
    
    return TrendDetail(
        id=trend_row['id'],
        name=trend_row['name'],
        slug=trend_row['slug'],
        category=trend_row['category'],
        description=trend_row['description'],
        aliases=trend_row['aliases'],
        overall_score=trend_row['overall_score'],
        evidence_grade=trend_row['evidence_grade'],
        confidence_level=trend_row['confidence_level'],
        claims=claims
    )


# -----------------------------------------------------------------------------
# Claims
# -----------------------------------------------------------------------------

@app.get("/trends/{slug}/claims", response_model=list[ClaimOut], tags=["Claims"])
async def list_claims_for_trend(slug: str):
    """Get all claims for a specific trend"""
    pool = await get_pool()
    
    async with pool.acquire() as conn:
        # First get trend ID
        trend_id = await conn.fetchval(
            "SELECT id FROM trends WHERE slug = $1 AND is_published = TRUE", 
            slug
        )
        
        if not trend_id:
            raise HTTPException(status_code=404, detail=f"Trend '{slug}' not found")
        
        rows = await conn.fetch("""
            SELECT id, claim_text, claim_slug, evidence_score, evidence_grade,
                   summary, num_human_rcts, num_meta_analyses, is_primary_claim
            FROM claims
            WHERE trend_id = $1
            ORDER BY is_primary_claim DESC, evidence_score DESC NULLS LAST
        """, trend_id)
    
    return [ClaimOut(
        id=row['id'],
        claim_text=row['claim_text'],
        claim_slug=row['claim_slug'],
        evidence_score=row['evidence_score'],
        evidence_grade=row['evidence_grade'],
        summary=row['summary'],
        num_human_rcts=row['num_human_rcts'] or 0,
        num_meta_analyses=row['num_meta_analyses'] or 0,
        is_primary_claim=row['is_primary_claim']
    ) for row in rows]


@app.get("/claims/{claim_id}", response_model=ClaimDetail, tags=["Claims"])
async def get_claim_detail(claim_id: int):
    """
    Get detailed information about a specific claim, including all linked studies.
    """
    pool = await get_pool()
    
    async with pool.acquire() as conn:
        # Get claim
        claim_row = await conn.fetchrow("""
            SELECT id, claim_text, claim_slug, evidence_score, evidence_grade,
                   summary, detailed_analysis, num_human_rcts, num_meta_analyses,
                   num_observational, num_animal_studies
            FROM claims
            WHERE id = $1
        """, claim_id)
        
        if not claim_row:
            raise HTTPException(status_code=404, detail=f"Claim {claim_id} not found")
        
        # Get linked studies
        study_rows = await conn.fetch("""
            SELECT s.pubmed_id, s.title, s.journal, s.publication_year,
                   s.study_type, s.is_human_study, s.sample_size,
                   cs.supports_claim
            FROM studies s
            JOIN claim_studies cs ON s.id = cs.study_id
            WHERE cs.claim_id = $1
            ORDER BY s.publication_year DESC
        """, claim_id)
    
    studies = [StudyOut(
        pubmed_id=row['pubmed_id'],
        title=row['title'],
        journal=row['journal'],
        publication_year=row['publication_year'],
        study_type=row['study_type'],
        is_human_study=row['is_human_study'],
        sample_size=row['sample_size'],
        supports_claim=row['supports_claim']
    ) for row in study_rows]
    
    return ClaimDetail(
        id=claim_row['id'],
        claim_text=claim_row['claim_text'],
        claim_slug=claim_row['claim_slug'],
        evidence_score=claim_row['evidence_score'],
        evidence_grade=claim_row['evidence_grade'],
        summary=claim_row['summary'],
        detailed_analysis=claim_row['detailed_analysis'],
        num_human_rcts=claim_row['num_human_rcts'] or 0,
        num_meta_analyses=claim_row['num_meta_analyses'] or 0,
        num_observational=claim_row['num_observational'] or 0,
        num_animal_studies=claim_row['num_animal_studies'] or 0,
        studies=studies
    )


# -----------------------------------------------------------------------------
# Search
# -----------------------------------------------------------------------------

@app.get("/search", response_model=SearchResult, tags=["Search"])
async def search_trends(
    q: str = Query(..., min_length=2, description="Search query"),
    limit: int = Query(10, ge=1, le=50)
):
    """
    Search trends by name, description, or aliases.
    """
    pool = await get_pool()
    
    async with pool.acquire() as conn:
        # Simple ILIKE search (the full-text index failed, so we use this fallback)
        rows = await conn.fetch("""
            SELECT t.id, t.name, t.slug, c.name as category,
                   t.overall_score, t.evidence_grade, t.description
            FROM trends t
            LEFT JOIN categories c ON t.category_id = c.id
            WHERE t.is_published = TRUE
              AND (
                  t.name ILIKE $1
                  OR t.description ILIKE $1
                  OR array_to_string(t.aliases, ' ') ILIKE $1
              )
            ORDER BY 
                CASE WHEN t.name ILIKE $1 THEN 0 ELSE 1 END,
                t.name
            LIMIT $2
        """, f"%{q}%", limit)
        
        total = len(rows)
    
    trends = [TrendSummary(**dict(row)) for row in rows]
    
    return SearchResult(trends=trends, total=total, query=q)


# -----------------------------------------------------------------------------
# Leaderboards
# -----------------------------------------------------------------------------

@app.get("/leaderboard/top-rated", response_model=list[TrendSummary], tags=["Leaderboards"])
async def top_rated_trends(limit: int = Query(10, ge=1, le=20)):
    """Get trends with the highest evidence scores"""
    pool = await get_pool()
    
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT t.id, t.name, t.slug, c.name as category,
                   t.overall_score, t.evidence_grade, t.description
            FROM trends t
            LEFT JOIN categories c ON t.category_id = c.id
            WHERE t.is_published = TRUE AND t.overall_score IS NOT NULL
            ORDER BY t.overall_score DESC
            LIMIT $1
        """, limit)
    
    return [TrendSummary(**dict(row)) for row in rows]


@app.get("/leaderboard/least-evidence", response_model=list[TrendSummary], tags=["Leaderboards"])
async def least_evidence_trends(limit: int = Query(10, ge=1, le=20)):
    """Get trends with the weakest evidence (the 'bullshit' list)"""
    pool = await get_pool()
    
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT t.id, t.name, t.slug, c.name as category,
                   t.overall_score, t.evidence_grade, t.description
            FROM trends t
            LEFT JOIN categories c ON t.category_id = c.id
            WHERE t.is_published = TRUE AND t.overall_score IS NOT NULL
            ORDER BY t.overall_score ASC
            LIMIT $1
        """, limit)
    
    return [TrendSummary(**dict(row)) for row in rows]


# =============================================================================
# Run with: uvicorn api:app --reload
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("api:app", host="0.0.0.0", port=port, reload=True)
