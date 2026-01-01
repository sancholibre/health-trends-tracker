# Health Trends Evidence Tracker

**"Is This Health Trend Bullshit?"** — A data-driven tool that rates the scientific evidence behind supplements, health products, and wellness trends.

## 🎯 What This Does

This project scrapes PubMed for scientific studies, analyzes them, and generates evidence scores for health claims. It answers questions like:

- Does tongkat ali actually increase testosterone?
- Is there real evidence for cold plunge benefits?
- How solid is the research on ashwagandha for anxiety?

## 📊 How Scoring Works

Each health claim is scored on a **0-10 scale** based on:

| Component | Weight | What It Measures |
|-----------|--------|------------------|
| Quantity | 25% | Number of studies (diminishing returns) |
| Quality | 40% | Study types (meta-analysis > RCT > observational > animal) |
| Consistency | 20% | Do results agree or contradict? |
| Recency | 15% | How recent is the research? |

**Grade Mapping:**
- **A (9-10):** Strong evidence from multiple high-quality human studies
- **B (7-8.9):** Moderate evidence, some RCTs or strong observational data
- **C (5-6.9):** Limited evidence, few human studies
- **D (3-4.9):** Weak evidence, mostly animal/in-vitro
- **F (0-2.9):** No meaningful evidence

## 🏗️ Project Structure

```
health-trends-tracker/
├── schema.sql           # PostgreSQL database schema
├── pubmed_scraper.py    # PubMed E-utilities API scraper
├── evidence_scorer.py   # Rules-based evidence scoring
├── database.py          # Database connection & repositories
├── requirements.txt     # Python dependencies
└── README.md           # This file
```

## 🚀 Quick Start

### 1. Set Up PostgreSQL on Railway

1. Go to [Railway](https://railway.app)
2. Create new project → Add PostgreSQL
3. Copy the `DATABASE_URL` from the Variables tab

### 2. Configure Environment

```bash
cd health-trends-tracker

# Create .env file
echo "DATABASE_URL=postgresql://..." > .env

# Install dependencies
pip install -r requirements.txt
```

### 3. Initialize Database

```bash
# Connect to Railway PostgreSQL and run schema
psql $DATABASE_URL -f schema.sql
```

Or use the Python helper:
```python
from database import init_database
import asyncio

asyncio.run(init_database(DATABASE_URL, "schema.sql"))
```

### 4. Test the Scraper

```python
import asyncio
from pubmed_scraper import PubMedScraper, HealthClaimSearcher

async def test():
    scraper = PubMedScraper()
    searcher = HealthClaimSearcher(scraper)
    
    studies = await searcher.search_supplement_claim(
        supplement_name="ashwagandha",
        claim="reduces anxiety",
        aliases=["withania somnifera"],
        max_results=20
    )
    
    for s in studies:
        print(f"[{s.pubmed_id}] {s.title[:60]}...")
        print(f"  Type: {s.study_type} | Human: {s.is_human_study}")

asyncio.run(test())
```

### 5. Test the Scorer

```python
from evidence_scorer import score_from_counts, print_score_report

# Example: Ashwagandha for anxiety
result = score_from_counts(
    human_rcts=5,
    meta_analyses=1,
    human_other=3,
    avg_sample_size=60,
    years_since_last=2
)

print_score_report(result)
# Output: EVIDENCE SCORE: 9.5/10 (A)
```

## 📋 Initial 20 Trends

The database is pre-seeded with these trends:

### Testosterone & Performance
1. Tongkat Ali
2. Turkesterone
3. Fadogia Agrestis
4. Shilajit
5. Ashwagandha

### Mental Health & Cognition
6. Magnesium Glycinate
7. L-Theanine
8. Inositol
9. Lion's Mane
10. Apigenin

### Gut & Metabolic
11. Berberine
12. Sea Moss
13. Beef Liver Supplements

### Devices & Protocols
14. Red Light Therapy
15. Cold Plunge
16. Mouth Taping
17. Grounding Mats

### General Wellness
18. Creatine
19. Collagen Peptides
20. Raw Milk

## 🔧 Database Schema Overview

**Core Tables:**
- `trends` — The supplements/devices/protocols
- `claims` — Specific health claims per trend
- `studies` — PubMed papers
- `claim_studies` — Links claims to supporting/refuting studies

**Supporting Tables:**
- `categories` — For organizing trends
- `trending_snapshots` — Historical popularity data
- `articles` — For blog content

## 🛠️ Next Steps (Roadmap)

### Phase 1: Data Population ✓
- [x] Database schema
- [x] PubMed scraper
- [x] Evidence scorer
- [x] Initial 20 trends seeded

### Phase 2: API Layer
- [ ] FastAPI endpoints
- [ ] Search endpoint
- [ ] Trend detail endpoint
- [ ] Claim scores endpoint

### Phase 3: Frontend
- [ ] Next.js or React app
- [ ] Search UI
- [ ] Trend pages
- [ ] Visualizations (radar charts, scatter plots)

### Phase 4: Automation
- [ ] Scheduled PubMed scraping
- [ ] Google Trends integration
- [ ] Reddit sentiment tracking
- [ ] Auto-rescoring

### Phase 5: Content & Growth
- [ ] "Top 10 Overhyped" articles
- [ ] Newsletter integration
- [ ] SEO optimization

## 📝 Key Design Decisions

1. **Multiple claims per trend:** A supplement can be good for one thing and useless for another. We score each claim separately.

2. **Transparency:** Show exactly how scores are calculated. Users can see study counts, penalties, and bonuses.

3. **Conservative scoring:** Extraordinary claims require extraordinary evidence. The system is intentionally skeptical.

4. **Auto vs. Expert:** Distinguish between auto-scored claims and expert-reviewed ones.

## 🔗 Data Sources

- **PubMed** — Primary source for scientific studies (E-utilities API)
- **Google Trends** — Popularity tracking
- **Reddit** — Sentiment and discussion volume
- **Examine.com** — Reference for initial claim mapping (not scraped)

## 📄 License

MIT — do whatever you want with it.

---

*Built December 2024*
