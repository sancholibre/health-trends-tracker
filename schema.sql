-- Health Trends Evidence Tracker
-- Database Schema v1.0
-- 
-- This schema supports tracking health trends (supplements, devices, protocols),
-- their associated claims, and the scientific evidence behind them.

-- Enable UUID extension for better ID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================================
-- CORE TABLES
-- ============================================================================

-- Categories for organizing trends
CREATE TABLE categories (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    icon VARCHAR(50),  -- For UI display (e.g., emoji or icon name)
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Main trends table (supplements, devices, protocols)
CREATE TABLE trends (
    id SERIAL PRIMARY KEY,
    uuid UUID DEFAULT uuid_generate_v4() UNIQUE,
    name VARCHAR(200) NOT NULL,
    slug VARCHAR(200) NOT NULL UNIQUE,  -- URL-friendly name
    category_id INTEGER REFERENCES categories(id),
    description TEXT,
    
    -- Aliases and search terms
    aliases TEXT[],  -- e.g., ['longjack', 'eurycoma longifolia'] for tongkat ali
    
    -- Aggregate scores (computed from claims)
    overall_score DECIMAL(3,1),  -- 0.0 - 10.0
    evidence_grade CHAR(2),       -- A+, A, A-, B+, B, B-, C+, C, C-, D, F
    confidence_level VARCHAR(20), -- 'auto', 'reviewed', 'expert_verified'
    
    -- Metadata
    image_url TEXT,
    wikipedia_url TEXT,
    examine_url TEXT,
    
    -- Status
    is_published BOOLEAN DEFAULT FALSE,
    is_featured BOOLEAN DEFAULT FALSE,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_scored_at TIMESTAMP WITH TIME ZONE
);

-- Claims associated with each trend
CREATE TABLE claims (
    id SERIAL PRIMARY KEY,
    uuid UUID DEFAULT uuid_generate_v4() UNIQUE,
    trend_id INTEGER NOT NULL REFERENCES trends(id) ON DELETE CASCADE,
    
    claim_text VARCHAR(500) NOT NULL,  -- e.g., "Increases testosterone levels"
    claim_slug VARCHAR(200) NOT NULL,   -- URL-friendly
    
    -- Evidence scoring
    evidence_score DECIMAL(3,1),  -- 0.0 - 10.0
    evidence_grade CHAR(2),        -- A+, A, A-, B+, B, B-, C+, C, C-, D, F
    confidence_level VARCHAR(20) DEFAULT 'auto',
    
    -- Scoring components (for transparency)
    num_human_rcts INTEGER DEFAULT 0,
    num_meta_analyses INTEGER DEFAULT 0,
    num_observational INTEGER DEFAULT 0,
    num_animal_studies INTEGER DEFAULT 0,
    num_in_vitro INTEGER DEFAULT 0,
    avg_sample_size INTEGER,
    effect_size_reported BOOLEAN DEFAULT FALSE,
    replication_score INTEGER,  -- 0-3: none, single lab, multiple labs, independent
    years_since_last_study INTEGER,
    
    -- Human-readable summary
    summary TEXT,  -- One-liner: "Modest effect in older men, no evidence in young males"
    detailed_analysis TEXT,  -- Longer expert analysis
    
    -- Status
    is_primary_claim BOOLEAN DEFAULT FALSE,  -- Main claim for this trend
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_scored_at TIMESTAMP WITH TIME ZONE,
    
    UNIQUE(trend_id, claim_slug)
);

-- Scientific studies from PubMed
CREATE TABLE studies (
    id SERIAL PRIMARY KEY,
    pubmed_id VARCHAR(20) UNIQUE,  -- PMID
    doi VARCHAR(100),
    
    -- Basic info
    title TEXT NOT NULL,
    authors TEXT[],
    journal VARCHAR(300),
    publication_date DATE,
    publication_year INTEGER,
    
    -- Study characteristics
    study_type VARCHAR(50),  -- 'rct', 'meta_analysis', 'systematic_review', 'observational', 'animal', 'in_vitro', 'case_study'
    is_human_study BOOLEAN DEFAULT FALSE,
    sample_size INTEGER,
    duration_weeks INTEGER,
    
    -- Content
    abstract TEXT,
    keywords TEXT[],
    mesh_terms TEXT[],
    
    -- Quality indicators
    journal_impact_factor DECIMAL(5,2),
    citation_count INTEGER,
    is_retracted BOOLEAN DEFAULT FALSE,
    
    -- Timestamps
    fetched_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Junction table: which studies support which claims
CREATE TABLE claim_studies (
    id SERIAL PRIMARY KEY,
    claim_id INTEGER NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    study_id INTEGER NOT NULL REFERENCES studies(id) ON DELETE CASCADE,
    
    -- Relationship details
    supports_claim VARCHAR(20) DEFAULT 'unknown',  -- 'yes', 'no', 'mixed', 'unknown'
    relevance_score DECIMAL(3,2),  -- 0.00 - 1.00, how directly relevant
    
    -- Notes
    notes TEXT,  -- Why this study is relevant/irrelevant
    
    -- Who added this link
    added_by VARCHAR(50) DEFAULT 'auto',  -- 'auto', 'manual', 'expert'
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    UNIQUE(claim_id, study_id)
);

-- ============================================================================
-- TRENDING DATA
-- ============================================================================

-- Snapshots of trending data over time
CREATE TABLE trending_snapshots (
    id SERIAL PRIMARY KEY,
    trend_id INTEGER NOT NULL REFERENCES trends(id) ON DELETE CASCADE,
    snapshot_date DATE NOT NULL,
    
    -- Google Trends data (0-100 normalized)
    google_trends_score INTEGER,
    google_trends_change_7d DECIMAL(5,2),  -- % change from 7 days ago
    google_trends_change_30d DECIMAL(5,2),
    
    -- Reddit mentions
    reddit_mentions_7d INTEGER,
    reddit_sentiment DECIMAL(3,2),  -- -1.0 to 1.0
    
    -- Amazon data (if applicable)
    amazon_rank INTEGER,
    amazon_review_count INTEGER,
    amazon_avg_rating DECIMAL(2,1),
    
    -- Social mentions
    tiktok_mentions INTEGER,
    twitter_mentions INTEGER,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    UNIQUE(trend_id, snapshot_date)
);

-- ============================================================================
-- USER ENGAGEMENT (future feature)
-- ============================================================================

-- Track which trends users are interested in
CREATE TABLE user_searches (
    id SERIAL PRIMARY KEY,
    search_query VARCHAR(500),
    matched_trend_id INTEGER REFERENCES trends(id),
    search_timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    user_session_id VARCHAR(100)  -- Anonymous session tracking
);

-- ============================================================================
-- CONTENT & EDITORIAL
-- ============================================================================

-- For blog-style content pieces
CREATE TABLE articles (
    id SERIAL PRIMARY KEY,
    uuid UUID DEFAULT uuid_generate_v4() UNIQUE,
    title VARCHAR(300) NOT NULL,
    slug VARCHAR(300) NOT NULL UNIQUE,
    subtitle TEXT,
    content TEXT,  -- Markdown content
    
    -- SEO
    meta_description VARCHAR(160),
    meta_keywords TEXT[],
    
    -- Relationships
    featured_trends INTEGER[],  -- Array of trend IDs
    
    -- Publishing
    is_published BOOLEAN DEFAULT FALSE,
    published_at TIMESTAMP WITH TIME ZONE,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================================================
-- INDEXES
-- ============================================================================

-- Trends
CREATE INDEX idx_trends_category ON trends(category_id);
CREATE INDEX idx_trends_slug ON trends(slug);
CREATE INDEX idx_trends_published ON trends(is_published);
CREATE INDEX idx_trends_score ON trends(overall_score DESC);

-- Claims
CREATE INDEX idx_claims_trend ON claims(trend_id);
CREATE INDEX idx_claims_score ON claims(evidence_score DESC);

-- Studies
CREATE INDEX idx_studies_pubmed ON studies(pubmed_id);
CREATE INDEX idx_studies_type ON studies(study_type);
CREATE INDEX idx_studies_year ON studies(publication_year);
CREATE INDEX idx_studies_human ON studies(is_human_study);

-- Claim-Studies
CREATE INDEX idx_claim_studies_claim ON claim_studies(claim_id);
CREATE INDEX idx_claim_studies_study ON claim_studies(study_id);

-- Trending
CREATE INDEX idx_trending_trend_date ON trending_snapshots(trend_id, snapshot_date DESC);

-- Full-text search on trends
CREATE INDEX idx_trends_search ON trends USING gin(to_tsvector('english', name || ' ' || COALESCE(description, '') || ' ' || COALESCE(array_to_string(aliases, ' '), '')));

-- ============================================================================
-- FUNCTIONS
-- ============================================================================

-- Function to auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Triggers for updated_at
CREATE TRIGGER update_trends_updated_at BEFORE UPDATE ON trends
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_claims_updated_at BEFORE UPDATE ON claims
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_studies_updated_at BEFORE UPDATE ON studies
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Function to calculate evidence grade from score
CREATE OR REPLACE FUNCTION score_to_grade(score DECIMAL)
RETURNS CHAR(2) AS $$
BEGIN
    RETURN CASE
        WHEN score >= 9.5 THEN 'A+'
        WHEN score >= 9.0 THEN 'A'
        WHEN score >= 8.5 THEN 'A-'
        WHEN score >= 8.0 THEN 'B+'
        WHEN score >= 7.0 THEN 'B'
        WHEN score >= 6.0 THEN 'B-'
        WHEN score >= 5.0 THEN 'C+'
        WHEN score >= 4.0 THEN 'C'
        WHEN score >= 3.0 THEN 'C-'
        WHEN score >= 2.0 THEN 'D'
        ELSE 'F'
    END;
END;
$$ LANGUAGE plpgsql;

-- Function to recalculate trend's overall score from its claims
CREATE OR REPLACE FUNCTION recalculate_trend_score(p_trend_id INTEGER)
RETURNS VOID AS $$
DECLARE
    v_avg_score DECIMAL;
BEGIN
    SELECT AVG(evidence_score) INTO v_avg_score
    FROM claims
    WHERE trend_id = p_trend_id AND evidence_score IS NOT NULL;
    
    UPDATE trends
    SET overall_score = v_avg_score,
        evidence_grade = score_to_grade(v_avg_score),
        last_scored_at = NOW()
    WHERE id = p_trend_id;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- SEED DATA: Categories
-- ============================================================================

INSERT INTO categories (name, description, icon) VALUES
    ('Testosterone & Performance', 'Supplements and methods claimed to boost testosterone, strength, or athletic performance', '💪'),
    ('Mental Health & Cognition', 'Supplements for anxiety, depression, focus, memory, and brain health', '🧠'),
    ('Gut & Metabolic Health', 'Probiotics, prebiotics, and supplements for digestion and metabolism', '🦠'),
    ('Devices & Protocols', 'Biohacking devices, therapies, and lifestyle protocols', '⚡'),
    ('Skin & Beauty', 'Collagen, anti-aging, and cosmetic supplements', '✨'),
    ('Sleep & Recovery', 'Supplements and methods for better sleep and physical recovery', '😴'),
    ('General Wellness', 'Vitamins, minerals, and general health supplements', '🌿');

-- ============================================================================
-- SEED DATA: Initial 20 Trends
-- ============================================================================

INSERT INTO trends (name, slug, category_id, description, aliases, is_published) VALUES

-- Testosterone & Performance
('Tongkat Ali', 'tongkat-ali', 1, 
 'Southeast Asian herb (Eurycoma longifolia) traditionally used as an aphrodisiac and testosterone booster. One of the more researched natural testosterone supplements.',
 ARRAY['longjack', 'eurycoma longifolia', 'malaysian ginseng', 'pasak bumi'], TRUE),

('Turkesterone', 'turkesterone', 1,
 'Ecdysteroid compound from Ajuga turkestanica, heavily marketed as a natural anabolic. Popularized by fitness influencers despite limited human research.',
 ARRAY['ajuga turkestanica', 'ecdysteroid'], TRUE),

('Fadogia Agrestis', 'fadogia-agrestis', 1,
 'Nigerian shrub promoted by Andrew Huberman for testosterone. Research limited to rat studies with potential toxicity concerns.',
 ARRAY['fadogia'], TRUE),

('Shilajit', 'shilajit', 1,
 'Mineral-rich tar-like substance from Himalayan rocks. Contains fulvic acid and trace minerals. Traditional Ayurvedic remedy.',
 ARRAY['mumijo', 'mineral pitch'], TRUE),

('Ashwagandha', 'ashwagandha', 1,
 'Adaptogenic herb (Withania somnifera) with solid research for stress reduction and cortisol management. Testosterone claims are secondary.',
 ARRAY['withania somnifera', 'indian ginseng', 'winter cherry'], TRUE),

-- Mental Health & Cognition
('Magnesium Glycinate', 'magnesium-glycinate', 2,
 'Highly bioavailable form of magnesium bound to glycine. Popular for anxiety, sleep, and muscle relaxation.',
 ARRAY['magnesium bisglycinate', 'chelated magnesium'], TRUE),

('L-Theanine', 'l-theanine', 2,
 'Amino acid found in tea leaves. Promotes calm alertness without sedation. Often stacked with caffeine.',
 ARRAY['theanine', 'suntheanine'], TRUE),

('Inositol', 'inositol', 2,
 'Sugar alcohol used at high doses (12-18g) for panic disorder and anxiety. Surprisingly robust research for specific conditions.',
 ARRAY['myo-inositol', 'vitamin b8'], TRUE),

('Lion''s Mane', 'lions-mane', 2,
 'Medicinal mushroom (Hericium erinaceus) studied for nerve growth factor stimulation. Popular for cognitive enhancement.',
 ARRAY['hericium erinaceus', 'yamabushitake', 'hedgehog mushroom'], TRUE),

('Apigenin', 'apigenin', 6,
 'Flavonoid found in chamomile, used as a sleep aid. Huberman-popularized. Limited human research.',
 ARRAY['chamomile extract'], TRUE),

-- Gut & Metabolic Health
('Berberine', 'berberine', 3,
 'Plant alkaloid marketed as "nature''s Ozempic" for blood sugar and weight. Actually has decent metabolic research.',
 ARRAY['berberine hcl', 'goldenseal extract'], TRUE),

('Sea Moss', 'sea-moss', 3,
 'Red algae (Chondrus crispus) viral on TikTok for thyroid and skin benefits. Mostly mineral content; claims far exceed evidence.',
 ARRAY['irish moss', 'chondrus crispus', 'carrageen moss'], TRUE),

('Beef Liver Supplements', 'beef-liver-supplements', 3,
 'Desiccated organ meat capsules popular in ancestral health circles. Real nutrients, but specific health claims often overstated.',
 ARRAY['desiccated liver', 'liver capsules', 'organ supplements'], TRUE),

-- Devices & Protocols
('Red Light Therapy', 'red-light-therapy', 4,
 'Photobiomodulation using red and near-infrared wavelengths. Specific wavelengths have research for skin and wound healing.',
 ARRAY['photobiomodulation', 'low-level light therapy', 'lllt', 'led therapy'], TRUE),

('Cold Plunge', 'cold-plunge', 4,
 'Cold water immersion for recovery and dopamine. Research exists but optimal protocols and long-term benefits debated.',
 ARRAY['cold water immersion', 'ice bath', 'cold exposure', 'cold therapy'], TRUE),

('Mouth Taping', 'mouth-taping', 4,
 'Taping mouth shut during sleep to promote nasal breathing. Viral trend with very limited research.',
 ARRAY['sleep taping', 'nasal breathing tape'], TRUE),

('Grounding Mats', 'grounding-mats', 4,
 'Mats that connect to electrical ground, claimed to reduce inflammation via electron transfer. Almost no rigorous evidence.',
 ARRAY['earthing mats', 'earthing', 'grounding therapy'], TRUE),

-- General Wellness
('Creatine', 'creatine', 1,
 'Most researched sports supplement. Well-established for strength/muscle. Cognitive benefits in specific populations emerging.',
 ARRAY['creatine monohydrate', 'creatine hcl'], TRUE),

('Collagen Peptides', 'collagen-peptides', 5,
 'Hydrolyzed collagen protein for skin, joints, and gut. Some positive research but effect sizes often modest.',
 ARRAY['hydrolyzed collagen', 'collagen powder', 'marine collagen', 'bovine collagen'], TRUE),

('Raw Milk', 'raw-milk', 7,
 'Unpasteurized milk claimed to have superior nutrition and probiotics. Real pathogen risks; benefits vs pasteurized not established.',
 ARRAY['unpasteurized milk', 'farm fresh milk'], TRUE);

-- ============================================================================
-- SEED DATA: Initial Claims for Each Trend
-- ============================================================================

-- Tongkat Ali claims
INSERT INTO claims (trend_id, claim_text, claim_slug, is_primary_claim) VALUES
(1, 'Increases testosterone levels', 'increases-testosterone', TRUE),
(1, 'Improves libido and sexual function', 'improves-libido', FALSE),
(1, 'Reduces cortisol and stress', 'reduces-cortisol', FALSE),
(1, 'Increases muscle mass and strength', 'increases-muscle', FALSE);

-- Turkesterone claims
INSERT INTO claims (trend_id, claim_text, claim_slug, is_primary_claim) VALUES
(2, 'Increases muscle protein synthesis', 'increases-muscle-synthesis', TRUE),
(2, 'Builds lean muscle mass', 'builds-muscle', FALSE),
(2, 'Enhances athletic performance', 'enhances-performance', FALSE);

-- Fadogia Agrestis claims
INSERT INTO claims (trend_id, claim_text, claim_slug, is_primary_claim) VALUES
(3, 'Increases testosterone levels', 'increases-testosterone', TRUE),
(3, 'Improves libido', 'improves-libido', FALSE),
(3, 'Safe for long-term use', 'safe-long-term', FALSE);

-- Shilajit claims
INSERT INTO claims (trend_id, claim_text, claim_slug, is_primary_claim) VALUES
(4, 'Increases testosterone levels', 'increases-testosterone', TRUE),
(4, 'Improves energy and reduces fatigue', 'improves-energy', FALSE),
(4, 'Provides bioavailable minerals', 'provides-minerals', FALSE);

-- Ashwagandha claims
INSERT INTO claims (trend_id, claim_text, claim_slug, is_primary_claim) VALUES
(5, 'Reduces cortisol and stress', 'reduces-cortisol', TRUE),
(5, 'Reduces anxiety symptoms', 'reduces-anxiety', FALSE),
(5, 'Increases testosterone', 'increases-testosterone', FALSE),
(5, 'Improves sleep quality', 'improves-sleep', FALSE);

-- Magnesium Glycinate claims
INSERT INTO claims (trend_id, claim_text, claim_slug, is_primary_claim) VALUES
(6, 'Reduces anxiety symptoms', 'reduces-anxiety', TRUE),
(6, 'Improves sleep quality', 'improves-sleep', FALSE),
(6, 'Reduces muscle cramps', 'reduces-cramps', FALSE);

-- L-Theanine claims
INSERT INTO claims (trend_id, claim_text, claim_slug, is_primary_claim) VALUES
(7, 'Promotes relaxation without sedation', 'promotes-relaxation', TRUE),
(7, 'Improves focus when combined with caffeine', 'improves-focus', FALSE),
(7, 'Reduces stress and anxiety', 'reduces-stress', FALSE);

-- Inositol claims
INSERT INTO claims (trend_id, claim_text, claim_slug, is_primary_claim) VALUES
(8, 'Reduces panic attack frequency', 'reduces-panic', TRUE),
(8, 'Reduces anxiety symptoms', 'reduces-anxiety', FALSE),
(8, 'Helps with PCOS symptoms', 'helps-pcos', FALSE);

-- Lion''s Mane claims
INSERT INTO claims (trend_id, claim_text, claim_slug, is_primary_claim) VALUES
(9, 'Improves cognitive function and memory', 'improves-cognition', TRUE),
(9, 'Stimulates nerve growth factor (NGF)', 'stimulates-ngf', FALSE),
(9, 'Reduces symptoms of depression and anxiety', 'reduces-depression', FALSE);

-- Apigenin claims
INSERT INTO claims (trend_id, claim_text, claim_slug, is_primary_claim) VALUES
(10, 'Improves sleep quality', 'improves-sleep', TRUE),
(10, 'Reduces anxiety', 'reduces-anxiety', FALSE);

-- Berberine claims
INSERT INTO claims (trend_id, claim_text, claim_slug, is_primary_claim) VALUES
(11, 'Lowers blood sugar levels', 'lowers-blood-sugar', TRUE),
(11, 'Promotes weight loss', 'promotes-weight-loss', FALSE),
(11, 'Improves cholesterol profile', 'improves-cholesterol', FALSE);

-- Sea Moss claims
INSERT INTO claims (trend_id, claim_text, claim_slug, is_primary_claim) VALUES
(12, 'Supports thyroid function', 'supports-thyroid', TRUE),
(12, 'Improves skin health', 'improves-skin', FALSE),
(12, 'Provides essential minerals', 'provides-minerals', FALSE);

-- Beef Liver claims
INSERT INTO claims (trend_id, claim_text, claim_slug, is_primary_claim) VALUES
(13, 'Provides highly bioavailable nutrients', 'provides-nutrients', TRUE),
(13, 'Increases energy levels', 'increases-energy', FALSE),
(13, 'Supports liver detoxification', 'supports-detox', FALSE);

-- Red Light Therapy claims
INSERT INTO claims (trend_id, claim_text, claim_slug, is_primary_claim) VALUES
(14, 'Improves skin health and reduces wrinkles', 'improves-skin', TRUE),
(14, 'Accelerates wound healing', 'accelerates-healing', FALSE),
(14, 'Reduces muscle soreness and improves recovery', 'reduces-soreness', FALSE),
(14, 'Promotes hair growth', 'promotes-hair-growth', FALSE);

-- Cold Plunge claims
INSERT INTO claims (trend_id, claim_text, claim_slug, is_primary_claim) VALUES
(15, 'Reduces inflammation and muscle soreness', 'reduces-inflammation', TRUE),
(15, 'Increases dopamine and alertness', 'increases-dopamine', FALSE),
(15, 'Improves immune function', 'improves-immunity', FALSE);

-- Mouth Taping claims
INSERT INTO claims (trend_id, claim_text, claim_slug, is_primary_claim) VALUES
(16, 'Improves sleep quality', 'improves-sleep', TRUE),
(16, 'Reduces snoring', 'reduces-snoring', FALSE),
(16, 'Promotes proper facial development', 'facial-development', FALSE);

-- Grounding Mats claims
INSERT INTO claims (trend_id, claim_text, claim_slug, is_primary_claim) VALUES
(17, 'Reduces inflammation', 'reduces-inflammation', TRUE),
(17, 'Improves sleep quality', 'improves-sleep', FALSE),
(17, 'Reduces stress and cortisol', 'reduces-stress', FALSE);

-- Creatine claims
INSERT INTO claims (trend_id, claim_text, claim_slug, is_primary_claim) VALUES
(18, 'Increases strength and power output', 'increases-strength', TRUE),
(18, 'Increases muscle mass', 'increases-muscle', FALSE),
(18, 'Improves cognitive function', 'improves-cognition', FALSE);

-- Collagen Peptides claims
INSERT INTO claims (trend_id, claim_text, claim_slug, is_primary_claim) VALUES
(19, 'Improves skin elasticity and hydration', 'improves-skin', TRUE),
(19, 'Reduces joint pain', 'reduces-joint-pain', FALSE),
(19, 'Supports gut health', 'supports-gut', FALSE);

-- Raw Milk claims
INSERT INTO claims (trend_id, claim_text, claim_slug, is_primary_claim) VALUES
(20, 'Contains beneficial probiotics', 'contains-probiotics', TRUE),
(20, 'More nutritious than pasteurized milk', 'more-nutritious', FALSE),
(20, 'Reduces allergies and asthma', 'reduces-allergies', FALSE);

-- ============================================================================
-- VIEWS
-- ============================================================================

-- View: Trends with their aggregate data
CREATE VIEW v_trends_overview AS
SELECT 
    t.id,
    t.name,
    t.slug,
    c.name as category,
    t.overall_score,
    t.evidence_grade,
    t.confidence_level,
    COUNT(cl.id) as num_claims,
    t.is_published,
    t.updated_at
FROM trends t
LEFT JOIN categories c ON t.category_id = c.id
LEFT JOIN claims cl ON t.id = cl.trend_id
GROUP BY t.id, c.name;

-- View: Claims with study counts
CREATE VIEW v_claims_with_studies AS
SELECT 
    cl.id,
    cl.claim_text,
    t.name as trend_name,
    cl.evidence_score,
    cl.evidence_grade,
    COUNT(cs.id) as num_studies,
    COUNT(CASE WHEN cs.supports_claim = 'yes' THEN 1 END) as supporting_studies,
    COUNT(CASE WHEN cs.supports_claim = 'no' THEN 1 END) as contradicting_studies
FROM claims cl
JOIN trends t ON cl.trend_id = t.id
LEFT JOIN claim_studies cs ON cl.id = cs.claim_id
GROUP BY cl.id, t.name;

-- ============================================================================
-- COMMENTS
-- ============================================================================

COMMENT ON TABLE trends IS 'Main table storing health trends, supplements, devices, and protocols';
COMMENT ON TABLE claims IS 'Specific health claims associated with each trend';
COMMENT ON TABLE studies IS 'Scientific studies from PubMed supporting or refuting claims';
COMMENT ON TABLE claim_studies IS 'Many-to-many relationship between claims and studies';
COMMENT ON TABLE trending_snapshots IS 'Historical tracking of trend popularity from various sources';
COMMENT ON COLUMN claims.evidence_score IS 'Score from 0-10 based on study quantity, quality, and consistency';
COMMENT ON COLUMN claims.confidence_level IS 'auto = algorithm scored, reviewed = manually checked, expert_verified = expert sign-off';
