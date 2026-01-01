"""
PubMed Scraper for Health Trends Evidence Tracker
Uses NCBI E-utilities API (free, no key required for low volume)

Documentation: https://www.ncbi.nlm.nih.gov/books/NBK25500/
"""

import asyncio
import aiohttp
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import re
import time
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# E-utilities base URLs
ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

# Rate limiting: NCBI allows 3 requests/second without API key, 10/second with key
REQUESTS_PER_SECOND = 3
REQUEST_DELAY = 1.0 / REQUESTS_PER_SECOND


@dataclass
class PubMedStudy:
    """Represents a study fetched from PubMed"""
    pubmed_id: str
    title: str
    abstract: Optional[str] = None
    authors: list[str] = field(default_factory=list)
    journal: Optional[str] = None
    publication_date: Optional[datetime] = None
    publication_year: Optional[int] = None
    doi: Optional[str] = None
    study_type: Optional[str] = None  # Will be inferred
    is_human_study: bool = False
    sample_size: Optional[int] = None
    keywords: list[str] = field(default_factory=list)
    mesh_terms: list[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for database insertion"""
        return {
            'pubmed_id': self.pubmed_id,
            'title': self.title,
            'abstract': self.abstract,
            'authors': self.authors,
            'journal': self.journal,
            'publication_date': self.publication_date,
            'publication_year': self.publication_year,
            'doi': self.doi,
            'study_type': self.study_type,
            'is_human_study': self.is_human_study,
            'sample_size': self.sample_size,
            'keywords': self.keywords,
            'mesh_terms': self.mesh_terms
        }


class PubMedScraper:
    """
    Scraper for PubMed using E-utilities API
    
    Usage:
        scraper = PubMedScraper()
        studies = await scraper.search_and_fetch("tongkat ali testosterone")
    """
    
    def __init__(self, email: Optional[str] = None, api_key: Optional[str] = None):
        """
        Initialize scraper.
        
        Args:
            email: Your email (recommended by NCBI for contact purposes)
            api_key: NCBI API key (optional, increases rate limit to 10/sec)
        """
        self.email = email
        self.api_key = api_key
        self.last_request_time = 0
        
    async def _rate_limit(self):
        """Enforce rate limiting"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        if time_since_last < REQUEST_DELAY:
            await asyncio.sleep(REQUEST_DELAY - time_since_last)
        self.last_request_time = time.time()
    
    def _build_params(self, extra_params: dict) -> dict:
        """Build request parameters with common fields"""
        params = extra_params.copy()
        if self.email:
            params['email'] = self.email
        if self.api_key:
            params['api_key'] = self.api_key
        return params
    
    async def search(
        self,
        query: str,
        max_results: int = 50,
        min_date: Optional[str] = None,
        max_date: Optional[str] = None,
        study_types: Optional[list[str]] = None
    ) -> list[str]:
        """
        Search PubMed and return list of PMIDs.
        
        Args:
            query: Search query (supports PubMed query syntax)
            max_results: Maximum number of results to return
            min_date: Minimum publication date (YYYY/MM/DD)
            max_date: Maximum publication date (YYYY/MM/DD)
            study_types: Filter by study type (e.g., ['randomized controlled trial', 'meta-analysis'])
        
        Returns:
            List of PubMed IDs (PMIDs)
        """
        await self._rate_limit()
        
        # Build query with filters
        full_query = query
        
        # Add study type filters if specified
        if study_types:
            type_filter = ' OR '.join([f'"{st}"[pt]' for st in study_types])
            full_query = f"({full_query}) AND ({type_filter})"
        
        params = self._build_params({
            'db': 'pubmed',
            'term': full_query,
            'retmax': max_results,
            'retmode': 'json',
            'sort': 'relevance'
        })
        
        if min_date:
            params['mindate'] = min_date
        if max_date:
            params['maxdate'] = max_date
        if min_date or max_date:
            params['datetype'] = 'pdat'  # Publication date
        
        async with aiohttp.ClientSession() as session:
            async with session.get(ESEARCH_URL, params=params) as response:
                if response.status != 200:
                    logger.error(f"Search failed: {response.status}")
                    return []
                
                data = await response.json()
                
        result = data.get('esearchresult', {})
        pmids = result.get('idlist', [])
        total_count = int(result.get('count', 0))
        
        logger.info(f"Found {total_count} results for '{query}', returning {len(pmids)}")
        return pmids
    
    async def fetch_details(self, pmids: list[str]) -> list[PubMedStudy]:
        """
        Fetch detailed information for a list of PMIDs.
        
        Args:
            pmids: List of PubMed IDs
            
        Returns:
            List of PubMedStudy objects
        """
        if not pmids:
            return []
        
        await self._rate_limit()
        
        params = self._build_params({
            'db': 'pubmed',
            'id': ','.join(pmids),
            'retmode': 'xml'
        })
        
        async with aiohttp.ClientSession() as session:
            async with session.get(EFETCH_URL, params=params) as response:
                if response.status != 200:
                    logger.error(f"Fetch failed: {response.status}")
                    return []
                
                xml_text = await response.text()
        
        return self._parse_xml(xml_text)
    
    def _parse_xml(self, xml_text: str) -> list[PubMedStudy]:
        """Parse PubMed XML response into PubMedStudy objects"""
        studies = []
        
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            logger.error(f"XML parse error: {e}")
            return []
        
        for article in root.findall('.//PubmedArticle'):
            try:
                study = self._parse_article(article)
                if study:
                    studies.append(study)
            except Exception as e:
                logger.error(f"Error parsing article: {e}")
                continue
        
        return studies
    
    def _parse_article(self, article: ET.Element) -> Optional[PubMedStudy]:
        """Parse a single PubmedArticle element"""
        
        # Get PMID
        pmid_elem = article.find('.//PMID')
        if pmid_elem is None:
            return None
        pmid = pmid_elem.text
        
        # Get title
        title_elem = article.find('.//ArticleTitle')
        title = title_elem.text if title_elem is not None else "No title"
        
        # Get abstract
        abstract_parts = []
        for abstract_text in article.findall('.//AbstractText'):
            label = abstract_text.get('Label', '')
            text = abstract_text.text or ''
            if label:
                abstract_parts.append(f"{label}: {text}")
            else:
                abstract_parts.append(text)
        abstract = ' '.join(abstract_parts) if abstract_parts else None
        
        # Get authors
        authors = []
        for author in article.findall('.//Author'):
            lastname = author.find('LastName')
            forename = author.find('ForeName')
            if lastname is not None:
                name = lastname.text
                if forename is not None:
                    name = f"{forename.text} {name}"
                authors.append(name)
        
        # Get journal
        journal_elem = article.find('.//Journal/Title')
        journal = journal_elem.text if journal_elem is not None else None
        
        # Get publication date
        pub_date = None
        pub_year = None
        
        # Try PubDate first
        year_elem = article.find('.//PubDate/Year')
        month_elem = article.find('.//PubDate/Month')
        day_elem = article.find('.//PubDate/Day')
        
        if year_elem is not None:
            pub_year = int(year_elem.text)
            month = 1
            day = 1
            
            if month_elem is not None:
                month_text = month_elem.text
                # Handle month names
                month_map = {
                    'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
                    'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
                }
                month = month_map.get(month_text, int(month_text) if month_text.isdigit() else 1)
            
            if day_elem is not None and day_elem.text.isdigit():
                day = int(day_elem.text)
            
            try:
                pub_date = datetime(pub_year, month, day)
            except ValueError:
                pub_date = datetime(pub_year, 1, 1)
        
        # Get DOI
        doi = None
        for article_id in article.findall('.//ArticleId'):
            if article_id.get('IdType') == 'doi':
                doi = article_id.text
                break
        
        # Get MeSH terms
        mesh_terms = []
        for mesh in article.findall('.//MeshHeading/DescriptorName'):
            if mesh.text:
                mesh_terms.append(mesh.text)
        
        # Get keywords
        keywords = []
        for keyword in article.findall('.//Keyword'):
            if keyword.text:
                keywords.append(keyword.text)
        
        # Infer study type from publication types
        pub_types = [pt.text for pt in article.findall('.//PublicationType') if pt.text]
        study_type = self._infer_study_type(pub_types, title, abstract)
        
        # Infer if human study
        is_human = self._is_human_study(mesh_terms, abstract or '', title)
        
        # Try to extract sample size from abstract
        sample_size = self._extract_sample_size(abstract) if abstract else None
        
        return PubMedStudy(
            pubmed_id=pmid,
            title=title,
            abstract=abstract,
            authors=authors,
            journal=journal,
            publication_date=pub_date,
            publication_year=pub_year,
            doi=doi,
            study_type=study_type,
            is_human_study=is_human,
            sample_size=sample_size,
            keywords=keywords,
            mesh_terms=mesh_terms
        )
    
    def _infer_study_type(self, pub_types: list[str], title: str, abstract: Optional[str]) -> str:
        """Infer study type from publication types and content"""
        
        pub_types_lower = [pt.lower() for pt in pub_types]
        combined_text = f"{title} {abstract or ''}".lower()
        
        # Check publication types first (most reliable)
        if 'meta-analysis' in pub_types_lower:
            return 'meta_analysis'
        if 'systematic review' in pub_types_lower:
            return 'systematic_review'
        if 'randomized controlled trial' in pub_types_lower:
            return 'rct'
        if 'clinical trial' in pub_types_lower:
            return 'clinical_trial'
        if 'review' in pub_types_lower:
            return 'review'
        if 'case reports' in pub_types_lower:
            return 'case_study'
        
        # Infer from content
        if 'meta-analysis' in combined_text or 'meta analysis' in combined_text:
            return 'meta_analysis'
        if 'systematic review' in combined_text:
            return 'systematic_review'
        if 'randomized' in combined_text and ('placebo' in combined_text or 'controlled' in combined_text):
            return 'rct'
        if 'double-blind' in combined_text or 'double blind' in combined_text:
            return 'rct'
        if any(term in combined_text for term in ['rats', 'mice', 'rodent', 'animal model', 'in vivo']):
            if 'human' not in combined_text and 'participants' not in combined_text:
                return 'animal'
        if any(term in combined_text for term in ['in vitro', 'cell culture', 'cell line']):
            return 'in_vitro'
        if 'observational' in combined_text or 'cohort' in combined_text:
            return 'observational'
        
        return 'unknown'
    
    def _is_human_study(self, mesh_terms: list[str], abstract: str, title: str) -> bool:
        """Determine if study was conducted on humans"""
        
        combined_text = f"{title} {abstract}".lower()
        mesh_lower = [m.lower() for m in mesh_terms]
        
        # Explicit human indicators
        human_terms = ['humans', 'human', 'patients', 'participants', 'subjects', 'volunteers', 
                       'men', 'women', 'adults', 'elderly', 'children']
        
        # Check MeSH terms
        if 'humans' in mesh_lower:
            return True
        if 'animals' in mesh_lower and 'humans' not in mesh_lower:
            return False
        
        # Check content
        animal_terms = ['rats', 'mice', 'rodents', 'rabbits', 'dogs', 'monkeys', 'in vitro', 'cell line']
        
        has_human = any(term in combined_text for term in human_terms)
        has_animal = any(term in combined_text for term in animal_terms)
        
        if has_human and not has_animal:
            return True
        if has_animal and not has_human:
            return False
        
        # Default to unknown (assume not human for safety)
        return False
    
    def _extract_sample_size(self, abstract: str) -> Optional[int]:
        """Attempt to extract sample size from abstract"""
        
        patterns = [
            r'n\s*=\s*(\d+)',
            r'(\d+)\s+(?:participants|subjects|patients|volunteers|individuals|adults|men|women)',
            r'(?:sample|sample size|enrolled|recruited)\s+(?:of\s+)?(\d+)',
            r'(\d+)\s+(?:were|was)\s+(?:enrolled|recruited|randomized)',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, abstract.lower())
            if matches:
                # Return the largest number found (often the total N)
                numbers = [int(m) for m in matches if int(m) > 5 and int(m) < 100000]
                if numbers:
                    return max(numbers)
        
        return None
    
    async def search_and_fetch(
        self,
        query: str,
        max_results: int = 50,
        **search_kwargs
    ) -> list[PubMedStudy]:
        """
        Convenience method: search and fetch in one call.
        
        Args:
            query: Search query
            max_results: Maximum results
            **search_kwargs: Additional args for search()
            
        Returns:
            List of PubMedStudy objects
        """
        pmids = await self.search(query, max_results, **search_kwargs)
        if not pmids:
            return []
        
        # Fetch in batches of 200 (NCBI recommendation)
        all_studies = []
        batch_size = 200
        
        for i in range(0, len(pmids), batch_size):
            batch = pmids[i:i + batch_size]
            studies = await self.fetch_details(batch)
            all_studies.extend(studies)
        
        return all_studies


# =============================================================================
# Search Strategies for Health Claims
# =============================================================================

class HealthClaimSearcher:
    """
    Higher-level class for searching health claims.
    Builds optimized queries for different types of claims.
    """
    
    def __init__(self, scraper: Optional[PubMedScraper] = None):
        self.scraper = scraper or PubMedScraper()
    
    async def search_supplement_claim(
        self,
        supplement_name: str,
        claim: str,
        aliases: Optional[list[str]] = None,
        max_results: int = 30
    ) -> list[PubMedStudy]:
        """
        Search for studies about a supplement's claimed benefit.
        
        Args:
            supplement_name: Name of supplement (e.g., "ashwagandha")
            claim: The health claim (e.g., "reduces anxiety")
            aliases: Alternative names for the supplement
            max_results: Maximum results to return
        """
        # Build name query with aliases
        names = [supplement_name]
        if aliases:
            names.extend(aliases)
        name_query = ' OR '.join([f'"{name}"' for name in names])
        
        # Parse claim into search terms
        claim_terms = self._parse_claim(claim)
        claim_query = ' OR '.join(claim_terms)
        
        # Combined query
        query = f"({name_query}) AND ({claim_query})"
        
        logger.info(f"Searching: {query}")
        
        return await self.scraper.search_and_fetch(query, max_results)
    
    def _parse_claim(self, claim: str) -> list[str]:
        """Convert a claim into search terms"""
        
        # Common claim patterns and their search terms
        claim_mappings = {
            'testosterone': ['testosterone', 'androgen', 'luteinizing hormone'],
            'anxiety': ['anxiety', 'anxiolytic', 'GAD', 'generalized anxiety'],
            'stress': ['stress', 'cortisol', 'HPA axis', 'adaptogen'],
            'sleep': ['sleep', 'insomnia', 'sleep quality', 'PSQI'],
            'muscle': ['muscle', 'lean mass', 'strength', 'hypertrophy'],
            'cognition': ['cognition', 'cognitive', 'memory', 'brain function'],
            'inflammation': ['inflammation', 'inflammatory', 'cytokine', 'CRP'],
            'energy': ['energy', 'fatigue', 'vitality'],
            'libido': ['libido', 'sexual function', 'erectile', 'aphrodisiac'],
            'blood sugar': ['blood glucose', 'glycemic', 'HbA1c', 'insulin'],
            'weight': ['weight loss', 'body composition', 'BMI', 'obesity'],
        }
        
        claim_lower = claim.lower()
        terms = []
        
        for key, search_terms in claim_mappings.items():
            if key in claim_lower:
                terms.extend(search_terms)
        
        # If no mapping found, use the claim itself
        if not terms:
            terms = [claim]
        
        return terms
    
    async def search_with_quality_filter(
        self,
        supplement_name: str,
        claim: str,
        aliases: Optional[list[str]] = None,
        human_only: bool = True,
        study_types: Optional[list[str]] = None
    ) -> list[PubMedStudy]:
        """
        Search with filters for higher quality studies.
        
        Args:
            supplement_name: Supplement name
            claim: Health claim
            aliases: Alternative names
            human_only: Only return human studies
            study_types: Filter by type (e.g., ['randomized controlled trial'])
        """
        studies = await self.search_supplement_claim(
            supplement_name, claim, aliases, max_results=100
        )
        
        # Filter results
        filtered = []
        for study in studies:
            if human_only and not study.is_human_study:
                continue
            if study_types and study.study_type not in study_types:
                continue
            filtered.append(study)
        
        return filtered


# =============================================================================
# Main / Testing
# =============================================================================

async def main():
    """Test the scraper"""
    scraper = PubMedScraper()
    searcher = HealthClaimSearcher(scraper)
    
    # Example: Search for tongkat ali testosterone studies
    print("\n" + "="*60)
    print("Searching: Tongkat Ali + Testosterone")
    print("="*60)
    
    studies = await searcher.search_supplement_claim(
        supplement_name="tongkat ali",
        claim="increases testosterone",
        aliases=["eurycoma longifolia", "longjack"],
        max_results=10
    )
    
    for study in studies:
        print(f"\n[{study.pubmed_id}] {study.title[:80]}...")
        print(f"  Type: {study.study_type} | Human: {study.is_human_study} | N={study.sample_size}")
        print(f"  Journal: {study.journal}")
        print(f"  Year: {study.publication_year}")
    
    print(f"\nTotal: {len(studies)} studies found")
    
    # Example: Search for ashwagandha anxiety (more researched)
    print("\n" + "="*60)
    print("Searching: Ashwagandha + Anxiety (RCTs only)")
    print("="*60)
    
    studies = await searcher.search_with_quality_filter(
        supplement_name="ashwagandha",
        claim="reduces anxiety",
        aliases=["withania somnifera"],
        human_only=True
    )
    
    rcts = [s for s in studies if s.study_type == 'rct']
    print(f"\nFound {len(studies)} human studies, {len(rcts)} RCTs")
    
    for study in rcts[:5]:
        print(f"\n[{study.pubmed_id}] {study.title[:80]}...")
        print(f"  N={study.sample_size} | Year: {study.publication_year}")


if __name__ == "__main__":
    asyncio.run(main())
