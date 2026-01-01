"""
Database utilities for Health Trends Tracker
Handles PostgreSQL connection and basic operations.
"""

import os
import asyncio
from typing import Optional, Any
from contextlib import asynccontextmanager

try:
    import asyncpg
except ImportError:
    asyncpg = None
    print("Warning: asyncpg not installed. Run: pip install asyncpg")

from dotenv import load_dotenv

load_dotenv()

# Database configuration
DATABASE_URL = os.getenv('DATABASE_URL')


class Database:
    """
    Async PostgreSQL database handler using asyncpg.
    
    Usage:
        db = Database()
        await db.connect()
        
        # Execute queries
        rows = await db.fetch("SELECT * FROM trends WHERE is_published = $1", True)
        
        # Insert
        await db.execute(
            "INSERT INTO trends (name, slug) VALUES ($1, $2)",
            "Ashwagandha", "ashwagandha"
        )
        
        await db.disconnect()
    """
    
    def __init__(self, database_url: Optional[str] = None):
        self.database_url = database_url or DATABASE_URL
        self.pool: Optional[asyncpg.Pool] = None
    
    async def connect(self, min_size: int = 2, max_size: int = 10):
        """Create connection pool"""
        if not self.database_url:
            raise ValueError("DATABASE_URL not set")
        
        if asyncpg is None:
            raise ImportError("asyncpg is required. Install with: pip install asyncpg")
        
        self.pool = await asyncpg.create_pool(
            self.database_url,
            min_size=min_size,
            max_size=max_size
        )
        print(f"✓ Connected to database")
    
    async def disconnect(self):
        """Close connection pool"""
        if self.pool:
            await self.pool.close()
            print("✓ Disconnected from database")
    
    @asynccontextmanager
    async def connection(self):
        """Get a connection from the pool"""
        async with self.pool.acquire() as conn:
            yield conn
    
    async def execute(self, query: str, *args) -> str:
        """Execute a query (INSERT, UPDATE, DELETE)"""
        async with self.connection() as conn:
            return await conn.execute(query, *args)
    
    async def fetch(self, query: str, *args) -> list:
        """Fetch multiple rows"""
        async with self.connection() as conn:
            return await conn.fetch(query, *args)
    
    async def fetchrow(self, query: str, *args) -> Optional[Any]:
        """Fetch a single row"""
        async with self.connection() as conn:
            return await conn.fetchrow(query, *args)
    
    async def fetchval(self, query: str, *args) -> Any:
        """Fetch a single value"""
        async with self.connection() as conn:
            return await conn.fetchval(query, *args)


# =============================================================================
# Repository Classes (Data Access Layer)
# =============================================================================

class TrendRepository:
    """Data access for trends table"""
    
    def __init__(self, db: Database):
        self.db = db
    
    async def get_all(self, published_only: bool = True) -> list[dict]:
        """Get all trends"""
        query = """
            SELECT t.*, c.name as category_name
            FROM trends t
            LEFT JOIN categories c ON t.category_id = c.id
        """
        if published_only:
            query += " WHERE t.is_published = TRUE"
        query += " ORDER BY t.name"
        
        rows = await self.db.fetch(query)
        return [dict(r) for r in rows]
    
    async def get_by_slug(self, slug: str) -> Optional[dict]:
        """Get trend by slug"""
        query = """
            SELECT t.*, c.name as category_name
            FROM trends t
            LEFT JOIN categories c ON t.category_id = c.id
            WHERE t.slug = $1
        """
        row = await self.db.fetchrow(query, slug)
        return dict(row) if row else None
    
    async def get_by_id(self, trend_id: int) -> Optional[dict]:
        """Get trend by ID"""
        query = """
            SELECT t.*, c.name as category_name
            FROM trends t
            LEFT JOIN categories c ON t.category_id = c.id
            WHERE t.id = $1
        """
        row = await self.db.fetchrow(query, trend_id)
        return dict(row) if row else None
    
    async def search(self, query_text: str, limit: int = 10) -> list[dict]:
        """Full-text search on trends"""
        sql = """
            SELECT t.*, c.name as category_name,
                   ts_rank(
                       to_tsvector('english', t.name || ' ' || COALESCE(t.description, '') || ' ' || COALESCE(array_to_string(t.aliases, ' '), '')),
                       plainto_tsquery('english', $1)
                   ) as rank
            FROM trends t
            LEFT JOIN categories c ON t.category_id = c.id
            WHERE t.is_published = TRUE
              AND to_tsvector('english', t.name || ' ' || COALESCE(t.description, '') || ' ' || COALESCE(array_to_string(t.aliases, ' '), ''))
                  @@ plainto_tsquery('english', $1)
            ORDER BY rank DESC
            LIMIT $2
        """
        rows = await self.db.fetch(sql, query_text, limit)
        return [dict(r) for r in rows]
    
    async def update_score(self, trend_id: int, score: float, grade: str):
        """Update a trend's aggregate score"""
        await self.db.execute(
            """
            UPDATE trends 
            SET overall_score = $2, evidence_grade = $3, last_scored_at = NOW()
            WHERE id = $1
            """,
            trend_id, score, grade
        )


class ClaimRepository:
    """Data access for claims table"""
    
    def __init__(self, db: Database):
        self.db = db
    
    async def get_for_trend(self, trend_id: int) -> list[dict]:
        """Get all claims for a trend"""
        query = """
            SELECT * FROM claims
            WHERE trend_id = $1
            ORDER BY is_primary_claim DESC, claim_text
        """
        rows = await self.db.fetch(query, trend_id)
        return [dict(r) for r in rows]
    
    async def get_by_id(self, claim_id: int) -> Optional[dict]:
        """Get claim by ID"""
        row = await self.db.fetchrow("SELECT * FROM claims WHERE id = $1", claim_id)
        return dict(row) if row else None
    
    async def update_score(
        self, 
        claim_id: int, 
        score: float, 
        grade: str,
        num_rcts: int = 0,
        num_meta: int = 0,
        summary: Optional[str] = None
    ):
        """Update a claim's evidence score"""
        await self.db.execute(
            """
            UPDATE claims 
            SET evidence_score = $2, 
                evidence_grade = $3, 
                num_human_rcts = $4,
                num_meta_analyses = $5,
                summary = $6,
                last_scored_at = NOW()
            WHERE id = $1
            """,
            claim_id, score, grade, num_rcts, num_meta, summary
        )


class StudyRepository:
    """Data access for studies table"""
    
    def __init__(self, db: Database):
        self.db = db
    
    async def get_by_pubmed_id(self, pubmed_id: str) -> Optional[dict]:
        """Get study by PubMed ID"""
        row = await self.db.fetchrow(
            "SELECT * FROM studies WHERE pubmed_id = $1",
            pubmed_id
        )
        return dict(row) if row else None
    
    async def upsert(self, study_data: dict) -> int:
        """Insert or update a study, return ID"""
        query = """
            INSERT INTO studies (
                pubmed_id, doi, title, authors, journal, 
                publication_date, publication_year,
                study_type, is_human_study, sample_size,
                abstract, keywords, mesh_terms
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
            ON CONFLICT (pubmed_id) DO UPDATE SET
                title = EXCLUDED.title,
                abstract = EXCLUDED.abstract,
                updated_at = NOW()
            RETURNING id
        """
        return await self.db.fetchval(
            query,
            study_data.get('pubmed_id'),
            study_data.get('doi'),
            study_data.get('title'),
            study_data.get('authors', []),
            study_data.get('journal'),
            study_data.get('publication_date'),
            study_data.get('publication_year'),
            study_data.get('study_type'),
            study_data.get('is_human_study', False),
            study_data.get('sample_size'),
            study_data.get('abstract'),
            study_data.get('keywords', []),
            study_data.get('mesh_terms', [])
        )
    
    async def get_for_claim(self, claim_id: int) -> list[dict]:
        """Get all studies linked to a claim"""
        query = """
            SELECT s.*, cs.supports_claim, cs.relevance_score, cs.notes
            FROM studies s
            JOIN claim_studies cs ON s.id = cs.study_id
            WHERE cs.claim_id = $1
            ORDER BY s.publication_year DESC
        """
        rows = await self.db.fetch(query, claim_id)
        return [dict(r) for r in rows]
    
    async def link_to_claim(
        self, 
        claim_id: int, 
        study_id: int, 
        supports: str = 'unknown',
        relevance: float = 0.5
    ):
        """Link a study to a claim"""
        await self.db.execute(
            """
            INSERT INTO claim_studies (claim_id, study_id, supports_claim, relevance_score)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (claim_id, study_id) DO UPDATE SET
                supports_claim = EXCLUDED.supports_claim,
                relevance_score = EXCLUDED.relevance_score
            """,
            claim_id, study_id, supports, relevance
        )


# =============================================================================
# Initialization Helper
# =============================================================================

async def init_database(database_url: str, schema_path: str = "schema.sql") -> Database:
    """Initialize database with schema if needed"""
    db = Database(database_url)
    await db.connect()
    
    # Check if tables exist
    exists = await db.fetchval(
        "SELECT EXISTS (SELECT FROM pg_tables WHERE tablename = 'trends')"
    )
    
    if not exists:
        print("Creating database schema...")
        with open(schema_path, 'r') as f:
            schema_sql = f.read()
        
        async with db.connection() as conn:
            await conn.execute(schema_sql)
        print("✓ Schema created successfully")
    else:
        print("✓ Database schema already exists")
    
    return db


async def get_db_stats(db: Database) -> dict:
    """Get basic database statistics"""
    stats = {}
    
    stats['trends'] = await db.fetchval("SELECT COUNT(*) FROM trends")
    stats['published_trends'] = await db.fetchval(
        "SELECT COUNT(*) FROM trends WHERE is_published = TRUE"
    )
    stats['claims'] = await db.fetchval("SELECT COUNT(*) FROM claims")
    stats['studies'] = await db.fetchval("SELECT COUNT(*) FROM studies")
    stats['categories'] = await db.fetchval("SELECT COUNT(*) FROM categories")
    
    return stats


# =============================================================================
# CLI for testing
# =============================================================================

async def main():
    """Test database connection"""
    import sys
    
    if not DATABASE_URL:
        print("ERROR: DATABASE_URL environment variable not set")
        print("\nSet it in .env file or export it:")
        print("  export DATABASE_URL='postgresql://user:pass@host:5432/dbname'")
        sys.exit(1)
    
    try:
        db = await init_database(DATABASE_URL)
        
        stats = await get_db_stats(db)
        print("\nDatabase Statistics:")
        for key, value in stats.items():
            print(f"  • {key}: {value}")
        
        # Test a query
        trends = await TrendRepository(db).get_all(published_only=False)
        print(f"\nLoaded {len(trends)} trends")
        
        if trends:
            print("\nFirst 5 trends:")
            for t in trends[:5]:
                print(f"  • {t['name']} ({t.get('category_name', 'No category')})")
        
        await db.disconnect()
        
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
