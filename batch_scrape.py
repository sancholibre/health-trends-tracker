"""
Batch Scraper - Populate all trends with PubMed data
Run this to scrape studies for all claims and calculate evidence scores.

Usage:
    python batch_scrape.py              # Run all trends
    python batch_scrape.py --trend ashwagandha  # Run single trend
    python batch_scrape.py --dry-run    # Preview without saving
"""

import asyncio
import asyncpg
import os
import sys
from datetime import datetime
from dotenv import load_dotenv

from pubmed_scraper import PubMedScraper, HealthClaimSearcher
from evidence_scorer import EvidenceScorer, StudySummary, StudyType

load_dotenv()

# Mapping of trend slugs to their search aliases
TREND_ALIASES = {
    'tongkat-ali': ['eurycoma longifolia', 'longjack'],
    'turkesterone': ['ajuga turkestanica', 'ecdysterone'],
    'fadogia-agrestis': ['fadogia'],
    'shilajit': ['mumijo', 'mineral pitch'],
    'ashwagandha': ['withania somnifera', 'indian ginseng'],
    'magnesium-glycinate': ['magnesium bisglycinate'],
    'l-theanine': ['theanine', 'suntheanine'],
    'inositol': ['myo-inositol'],
    'lions-mane': ['hericium erinaceus'],
    'apigenin': [],
    'berberine': ['berberine HCl'],
    'sea-moss': ['irish moss', 'chondrus crispus'],
    'beef-liver-supplements': ['desiccated liver'],
    'red-light-therapy': ['photobiomodulation', 'LLLT', 'low level laser therapy'],
    'cold-plunge': ['cold water immersion', 'cold exposure', 'cryotherapy'],
    'mouth-taping': [],
    'grounding-mats': ['earthing', 'grounding therapy'],
    'creatine': ['creatine monohydrate'],
    'collagen-peptides': ['hydrolyzed collagen', 'collagen hydrolysate'],
    'raw-milk': ['unpasteurized milk'],
}

# Mapping of claim text patterns to search terms
CLAIM_SEARCH_TERMS = {
    'testosterone': ['testosterone', 'androgen', 'luteinizing hormone', 'LH'],
    'cortisol': ['cortisol', 'stress hormone', 'HPA axis'],
    'anxiety': ['anxiety', 'anxiolytic', 'GAD'],
    'stress': ['stress', 'psychological stress', 'cortisol'],
    'sleep': ['sleep', 'insomnia', 'sleep quality'],
    'muscle': ['muscle', 'strength', 'hypertrophy', 'lean mass'],
    'cognitive': ['cognitive', 'memory', 'cognition', 'brain'],
    'inflammation': ['inflammation', 'inflammatory', 'CRP', 'cytokine'],
    'blood sugar': ['blood glucose', 'glycemic', 'insulin', 'HbA1c'],
    'skin': ['skin', 'collagen', 'wrinkles', 'dermal'],
    'gut': ['gut', 'microbiome', 'digestive', 'intestinal'],
    'libido': ['libido', 'sexual function', 'erectile'],
    'energy': ['energy', 'fatigue', 'ATP', 'mitochondria'],
    'recovery': ['recovery', 'DOMS', 'muscle soreness'],
    'mood': ['mood', 'depression', 'well-being'],
    'weight': ['weight loss', 'body composition', 'fat mass'],
    'thyroid': ['thyroid', 'T3', 'T4', 'TSH'],
}


def get_search_terms_for_claim(claim_text: str) -> list[str]:
    """Extract relevant search terms based on claim text"""
    claim_lower = claim_text.lower()
    terms = []
    
    for keyword, search_terms in CLAIM_SEARCH_TERMS.items():
        if keyword in claim_lower:
            terms.extend(search_terms)
    
    # If no specific terms found, use key words from claim
    if not terms:
        # Extract nouns/key terms (simple approach)
        stop_words = {'increases', 'reduces', 'improves', 'supports', 'enhances', 'and', 'the', 'for', 'with'}
        terms = [w for w in claim_text.lower().split() if w not in stop_words and len(w) > 3]
    
    return terms[:3]  # Limit to 3 terms


def study_to_summary(study) -> StudySummary:
    """Convert PubMed study to scorer format"""
    type_map = {
        'meta_analysis': StudyType.META_ANALYSIS,
        'rct': StudyType.RCT,
        'review': StudyType.REVIEW,
        'observational': StudyType.OBSERVATIONAL,
        'animal': StudyType.ANIMAL,
        'in_vitro': StudyType.IN_VITRO,
        'clinical_trial': StudyType.RCT,
        'unknown': StudyType.UNKNOWN
    }
    return StudySummary(
        study_type=type_map.get(study.study_type, StudyType.UNKNOWN),
        is_human=study.is_human_study,
        sample_size=study.sample_size,
        publication_year=study.publication_year,
        supports_claim='yes'  # Default assumption
    )


async def scrape_claim(conn, scraper, searcher, scorer, trend_name: str, trend_slug: str, claim: dict, dry_run: bool = False):
    """Scrape PubMed for a single claim and update database"""
    
    aliases = TREND_ALIASES.get(trend_slug, [])
    search_terms = get_search_terms_for_claim(claim['claim_text'])
    
    print(f"\n  📚 Claim: {claim['claim_text']}")
    print(f"     Search: {trend_name} + {search_terms}")
    
    try:
        # Search PubMed
        studies = await searcher.search_supplement_claim(
            supplement_name=trend_name,
            claim=' '.join(search_terms),
            aliases=aliases,
            max_results=100  # Increased from 20 to capture more studies
        )
        
        print(f"     Found: {len(studies)} studies")
        
        if not studies:
            print(f"     ⚠️  No studies found")
            return
        
        # Score the evidence
        study_summaries = [study_to_summary(s) for s in studies]
        result = scorer.score_claim(study_summaries)
        
        print(f"     Score: {result.final_score:.1f}/10 ({result.grade})")
        print(f"     RCTs: {result.human_rcts}, Meta: {result.meta_analyses}")
        
        if dry_run:
            print(f"     [DRY RUN - not saving]")
            return
        
        # Generate summary
        summary_parts = []
        if result.meta_analyses > 0:
            summary_parts.append(f"{result.meta_analyses} meta-analys{'e' if result.meta_analyses == 1 else 'i'}s")
        if result.human_rcts > 0:
            summary_parts.append(f"{result.human_rcts} RCT{'s' if result.human_rcts > 1 else ''}")
        
        if result.final_score >= 8:
            strength = "Strong evidence"
        elif result.final_score >= 6:
            strength = "Moderate evidence"
        elif result.final_score >= 4:
            strength = "Limited evidence"
        else:
            strength = "Weak evidence"
        
        summary = f"{strength} from {' and '.join(summary_parts)}." if summary_parts else f"{strength}. Limited research available."
        
        # Update claim in database
        await conn.execute("""
            UPDATE claims 
            SET evidence_score = $1,
                evidence_grade = $2,
                num_human_rcts = $3,
                num_meta_analyses = $4,
                num_observational = $5,
                num_animal_studies = $6,
                summary = $7,
                confidence_level = 'auto',
                last_scored_at = NOW()
            WHERE id = $8
        """,
            result.final_score,
            result.grade,
            result.human_rcts,
            result.meta_analyses,
            result.human_other,
            result.animal_studies,
            summary,
            claim['id']
        )
        
        # Save studies and link to claim
        for study in studies:
            study_id = await conn.fetchval("""
                INSERT INTO studies (pubmed_id, title, journal, publication_year, 
                                    study_type, is_human_study, sample_size, abstract)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (pubmed_id) DO UPDATE SET title = EXCLUDED.title
                RETURNING id
            """,
                study.pubmed_id,
                study.title,
                study.journal,
                study.publication_year,
                study.study_type,
                study.is_human_study,
                study.sample_size,
                study.abstract[:5000] if study.abstract else None  # Truncate long abstracts
            )
            
            await conn.execute("""
                INSERT INTO claim_studies (claim_id, study_id, supports_claim)
                VALUES ($1, $2, 'yes')
                ON CONFLICT (claim_id, study_id) DO NOTHING
            """, claim['id'], study_id)
        
        print(f"     ✓ Saved to database")
        
    except Exception as e:
        print(f"     ❌ Error: {e}")


async def scrape_trend(conn, scraper, searcher, scorer, trend: dict, dry_run: bool = False):
    """Scrape all claims for a single trend"""
    
    print(f"\n{'='*60}")
    print(f"🔬 {trend['name']}")
    print(f"{'='*60}")
    
    # Get claims for this trend
    claims = await conn.fetch("""
        SELECT id, claim_text, claim_slug
        FROM claims
        WHERE trend_id = $1
    """, trend['id'])
    
    print(f"   Claims to process: {len(claims)}")
    
    for claim in claims:
        await scrape_claim(conn, scraper, searcher, scorer, trend['name'], trend['slug'], dict(claim), dry_run)
        await asyncio.sleep(1)  # Rate limiting between claims
    
    # Recalculate trend score
    if not dry_run:
        avg_score = await conn.fetchval("""
            SELECT AVG(evidence_score) 
            FROM claims 
            WHERE trend_id = $1 AND evidence_score IS NOT NULL
        """, trend['id'])
        
        if avg_score:
            # Determine grade
            if avg_score >= 9:
                grade = 'A+'
            elif avg_score >= 8:
                grade = 'A'
            elif avg_score >= 7:
                grade = 'B+'
            elif avg_score >= 6:
                grade = 'B'
            elif avg_score >= 5:
                grade = 'C+'
            elif avg_score >= 4:
                grade = 'C'
            elif avg_score >= 3:
                grade = 'D'
            else:
                grade = 'F'
            
            await conn.execute("""
                UPDATE trends 
                SET overall_score = $1, evidence_grade = $2
                WHERE id = $3
            """, avg_score, grade, trend['id'])
            
            print(f"\n   📊 Trend Score: {avg_score:.1f}/10 ({grade})")


async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Batch scrape PubMed for health trends')
    parser.add_argument('--trend', type=str, help='Scrape only this trend (by slug)')
    parser.add_argument('--dry-run', action='store_true', help='Preview without saving to database')
    args = parser.parse_args()
    
    print("=" * 60)
    print("🔬 Health Trends Batch Scraper")
    print("=" * 60)
    
    if args.dry_run:
        print("⚠️  DRY RUN MODE - No changes will be saved")
    
    # Connect to database
    conn = await asyncpg.connect(os.getenv('DATABASE_URL'))
    print("✓ Connected to database")
    
    # Initialize scraper and scorer
    scraper = PubMedScraper()
    searcher = HealthClaimSearcher(scraper)
    scorer = EvidenceScorer()
    
    try:
        # Get trends to process
        if args.trend:
            trends = await conn.fetch("""
                SELECT id, name, slug FROM trends WHERE slug = $1
            """, args.trend)
            if not trends:
                print(f"❌ Trend '{args.trend}' not found")
                return
        else:
            trends = await conn.fetch("""
                SELECT id, name, slug FROM trends WHERE is_published = TRUE ORDER BY name
            """)
        
        print(f"\n📋 Processing {len(trends)} trends...")
        
        for trend in trends:
            await scrape_trend(conn, scraper, searcher, scorer, dict(trend), args.dry_run)
            await asyncio.sleep(2)  # Rate limiting between trends
        
        print("\n" + "=" * 60)
        print("✅ Batch scraping complete!")
        print("=" * 60)
        
        # Show summary
        stats = await conn.fetchrow("""
            SELECT 
                COUNT(DISTINCT s.id) as studies,
                COUNT(DISTINCT c.id) FILTER (WHERE c.evidence_score IS NOT NULL) as scored_claims,
                COUNT(DISTINCT t.id) FILTER (WHERE t.overall_score IS NOT NULL) as scored_trends
            FROM trends t
            LEFT JOIN claims c ON t.id = c.trend_id
            LEFT JOIN claim_studies cs ON c.id = cs.claim_id
            LEFT JOIN studies s ON cs.study_id = s.id
        """)
        
        print(f"\n📊 Database Summary:")
        print(f"   Studies indexed: {stats['studies']}")
        print(f"   Claims scored: {stats['scored_claims']}")
        print(f"   Trends scored: {stats['scored_trends']}")
        
    finally:
        await conn.close()


if __name__ == '__main__':
    asyncio.run(main())
