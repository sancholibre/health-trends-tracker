"""
Evidence Scoring System for Health Trends Tracker

This module implements a rules-based scoring system that evaluates
the strength of evidence for health claims based on:
- Number and type of studies
- Study quality indicators
- Consistency of findings
- Recency of research

The scoring outputs:
- Numerical score (0-10)
- Letter grade (A+ to F)
- Confidence level (auto/reviewed/expert_verified)
- Detailed breakdown of scoring components
"""

from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class StudyType(Enum):
    """Types of studies, roughly ordered by evidence quality"""
    META_ANALYSIS = "meta_analysis"
    SYSTEMATIC_REVIEW = "systematic_review"
    RCT = "rct"
    CLINICAL_TRIAL = "clinical_trial"
    OBSERVATIONAL = "observational"
    CASE_STUDY = "case_study"
    ANIMAL = "animal"
    IN_VITRO = "in_vitro"
    REVIEW = "review"
    UNKNOWN = "unknown"


class EvidenceGrade(Enum):
    """Letter grades for evidence quality"""
    A_PLUS = "A+"
    A = "A"
    A_MINUS = "A-"
    B_PLUS = "B+"
    B = "B"
    B_MINUS = "B-"
    C_PLUS = "C+"
    C = "C"
    C_MINUS = "C-"
    D = "D"
    F = "F"


@dataclass
class StudySummary:
    """Summary of a study for scoring purposes"""
    study_type: StudyType
    is_human: bool
    sample_size: Optional[int] = None
    publication_year: Optional[int] = None
    supports_claim: Optional[str] = None  # 'yes', 'no', 'mixed'


@dataclass
class ScoreBreakdown:
    """Detailed breakdown of how a score was calculated"""
    
    # Raw counts
    total_studies: int = 0
    human_rcts: int = 0
    meta_analyses: int = 0
    human_other: int = 0
    animal_studies: int = 0
    in_vitro_studies: int = 0
    
    # Quality metrics
    avg_sample_size: Optional[float] = None
    largest_sample: Optional[int] = None
    most_recent_year: Optional[int] = None
    years_since_last_study: Optional[int] = None
    
    # Consistency
    supporting_studies: int = 0
    contradicting_studies: int = 0
    mixed_studies: int = 0
    consistency_ratio: Optional[float] = None
    
    # Component scores (each 0-10)
    quantity_score: float = 0.0
    quality_score: float = 0.0
    consistency_score: float = 0.0
    recency_score: float = 0.0
    
    # Final
    raw_score: float = 0.0
    final_score: float = 0.0
    grade: str = "F"
    
    # Penalties/bonuses applied
    penalties: list[str] = field(default_factory=list)
    bonuses: list[str] = field(default_factory=list)


class EvidenceScorer:
    """
    Rules-based evidence scoring system.
    
    Scoring Philosophy:
    - A grade = Multiple high-quality human RCTs with consistent results
    - B grade = Some human RCTs or strong observational evidence
    - C grade = Limited human studies or mostly animal research
    - D grade = Only animal/in-vitro studies
    - F grade = No real evidence or only anecdotal
    
    The system is intentionally conservative - extraordinary claims
    require extraordinary evidence.
    """
    
    # Weights for different components
    WEIGHTS = {
        'quantity': 0.25,    # How many studies
        'quality': 0.40,     # Type and rigor of studies
        'consistency': 0.20, # Do results agree
        'recency': 0.15      # How recent is the research
    }
    
    # Study type weights for quality scoring
    STUDY_TYPE_WEIGHTS = {
        StudyType.META_ANALYSIS: 10.0,
        StudyType.SYSTEMATIC_REVIEW: 8.0,
        StudyType.RCT: 8.0,
        StudyType.CLINICAL_TRIAL: 6.0,
        StudyType.OBSERVATIONAL: 4.0,
        StudyType.CASE_STUDY: 2.0,
        StudyType.ANIMAL: 2.0,
        StudyType.IN_VITRO: 1.0,
        StudyType.REVIEW: 1.0,
        StudyType.UNKNOWN: 0.5
    }
    
    def __init__(self, current_year: int = 2025):
        self.current_year = current_year
    
    def score_claim(self, studies: list[StudySummary]) -> ScoreBreakdown:
        """
        Score a health claim based on its supporting studies.
        
        Args:
            studies: List of StudySummary objects
            
        Returns:
            ScoreBreakdown with detailed scoring information
        """
        breakdown = ScoreBreakdown()
        
        if not studies:
            breakdown.grade = "F"
            breakdown.penalties.append("No studies found")
            return breakdown
        
        # Count study types
        self._count_studies(studies, breakdown)
        
        # Calculate component scores
        breakdown.quantity_score = self._score_quantity(breakdown)
        breakdown.quality_score = self._score_quality(studies, breakdown)
        breakdown.consistency_score = self._score_consistency(studies, breakdown)
        breakdown.recency_score = self._score_recency(studies, breakdown)
        
        # Calculate weighted raw score
        breakdown.raw_score = (
            breakdown.quantity_score * self.WEIGHTS['quantity'] +
            breakdown.quality_score * self.WEIGHTS['quality'] +
            breakdown.consistency_score * self.WEIGHTS['consistency'] +
            breakdown.recency_score * self.WEIGHTS['recency']
        )
        
        # Apply penalties and bonuses
        breakdown.final_score = self._apply_adjustments(breakdown)
        
        # Ensure score is in valid range
        breakdown.final_score = max(0.0, min(10.0, breakdown.final_score))
        
        # Convert to grade
        breakdown.grade = self._score_to_grade(breakdown.final_score)
        
        return breakdown
    
    def _count_studies(self, studies: list[StudySummary], breakdown: ScoreBreakdown):
        """Count different types of studies"""
        breakdown.total_studies = len(studies)
        
        sample_sizes = []
        years = []
        
        for study in studies:
            # Count by type
            if study.study_type == StudyType.META_ANALYSIS:
                breakdown.meta_analyses += 1
            elif study.study_type == StudyType.RCT and study.is_human:
                breakdown.human_rcts += 1
            elif study.is_human:
                breakdown.human_other += 1
            elif study.study_type == StudyType.ANIMAL:
                breakdown.animal_studies += 1
            elif study.study_type == StudyType.IN_VITRO:
                breakdown.in_vitro_studies += 1
            
            # Track sample sizes
            if study.sample_size and study.sample_size > 0:
                sample_sizes.append(study.sample_size)
            
            # Track years
            if study.publication_year:
                years.append(study.publication_year)
            
            # Track support
            if study.supports_claim == 'yes':
                breakdown.supporting_studies += 1
            elif study.supports_claim == 'no':
                breakdown.contradicting_studies += 1
            elif study.supports_claim == 'mixed':
                breakdown.mixed_studies += 1
        
        # Calculate averages
        if sample_sizes:
            breakdown.avg_sample_size = sum(sample_sizes) / len(sample_sizes)
            breakdown.largest_sample = max(sample_sizes)
        
        if years:
            breakdown.most_recent_year = max(years)
            breakdown.years_since_last_study = self.current_year - breakdown.most_recent_year
    
    def _score_quantity(self, breakdown: ScoreBreakdown) -> float:
        """
        Score based on number of studies.
        More studies = more confidence, but diminishing returns.
        """
        # Human studies matter most
        human_studies = breakdown.human_rcts + breakdown.human_other + breakdown.meta_analyses
        
        if human_studies == 0:
            # Only animal/in-vitro studies
            total = breakdown.animal_studies + breakdown.in_vitro_studies
            if total == 0:
                return 0.0
            # Cap at 4.0 for non-human studies
            return min(4.0, total * 0.5)
        
        # Score human studies with diminishing returns
        # 1 study = 3, 3 studies = 6, 5+ studies = 8, 10+ studies = 10
        if human_studies >= 10:
            return 10.0
        elif human_studies >= 5:
            return 8.0 + (human_studies - 5) * 0.4
        elif human_studies >= 3:
            return 6.0 + (human_studies - 3) * 1.0
        else:
            return human_studies * 3.0
    
    def _score_quality(self, studies: list[StudySummary], breakdown: ScoreBreakdown) -> float:
        """
        Score based on study quality.
        Meta-analyses and RCTs score highest.
        """
        if not studies:
            return 0.0
        
        # Calculate weighted average of study types
        total_weight = 0.0
        weighted_sum = 0.0
        
        for study in studies:
            weight = self.STUDY_TYPE_WEIGHTS.get(study.study_type, 0.5)
            
            # Bonus for human studies
            if study.is_human:
                weight *= 1.5
            
            # Bonus for larger sample sizes
            if study.sample_size:
                if study.sample_size >= 100:
                    weight *= 1.3
                elif study.sample_size >= 50:
                    weight *= 1.1
            
            weighted_sum += weight
            total_weight += 1
        
        avg_quality = weighted_sum / total_weight if total_weight > 0 else 0
        
        # Normalize to 0-10 scale
        # Max possible single study score is ~15.6 (meta-analysis * 1.5 human * 1.3 large)
        normalized = min(10.0, avg_quality * 0.8)
        
        # Bonus for having meta-analyses
        if breakdown.meta_analyses >= 1:
            normalized = min(10.0, normalized + 1.0)
            breakdown.bonuses.append(f"{breakdown.meta_analyses} meta-analysis")
        
        # Bonus for multiple RCTs
        if breakdown.human_rcts >= 3:
            normalized = min(10.0, normalized + 0.5)
            breakdown.bonuses.append(f"{breakdown.human_rcts} human RCTs")
        
        return normalized
    
    def _score_consistency(self, studies: list[StudySummary], breakdown: ScoreBreakdown) -> float:
        """
        Score based on consistency of findings.
        Contradictory results reduce confidence.
        """
        total_evaluated = (
            breakdown.supporting_studies + 
            breakdown.contradicting_studies + 
            breakdown.mixed_studies
        )
        
        if total_evaluated == 0:
            # No studies have been evaluated for support
            # This is okay for auto-scoring, return neutral
            return 5.0
        
        # Calculate consistency ratio
        breakdown.consistency_ratio = breakdown.supporting_studies / total_evaluated
        
        # Convert to score
        # 100% supporting = 10, 50% = 5, 0% = 0
        base_score = breakdown.consistency_ratio * 10
        
        # Penalty for contradicting studies (not just "not supporting")
        if breakdown.contradicting_studies > 0:
            penalty = min(3.0, breakdown.contradicting_studies * 0.5)
            base_score -= penalty
            breakdown.penalties.append(f"{breakdown.contradicting_studies} contradicting studies")
        
        return max(0.0, base_score)
    
    def _score_recency(self, studies: list[StudySummary], breakdown: ScoreBreakdown) -> float:
        """
        Score based on how recent the research is.
        Science evolves - old studies may be outdated.
        """
        if breakdown.years_since_last_study is None:
            return 5.0  # Neutral if no dates
        
        years = breakdown.years_since_last_study
        
        if years <= 2:
            return 10.0  # Very recent
        elif years <= 5:
            return 8.0
        elif years <= 10:
            return 6.0
        elif years <= 15:
            return 4.0
            breakdown.penalties.append("Research is 10-15 years old")
        else:
            breakdown.penalties.append("Research is over 15 years old")
            return 2.0
    
    def _apply_adjustments(self, breakdown: ScoreBreakdown) -> float:
        """Apply penalties and bonuses to the raw score"""
        score = breakdown.raw_score
        
        # Penalty: No human studies at all
        if breakdown.human_rcts + breakdown.human_other == 0:
            if breakdown.meta_analyses == 0:
                score -= 2.0
                breakdown.penalties.append("No human studies")
        
        # Penalty: Only tiny sample sizes
        if breakdown.avg_sample_size and breakdown.avg_sample_size < 30:
            score -= 1.0
            breakdown.penalties.append("Very small sample sizes")
        
        # Penalty: Only one study
        if breakdown.total_studies == 1:
            score -= 1.5
            breakdown.penalties.append("Only one study exists")
        
        # Bonus: Large, high-quality trial
        if breakdown.largest_sample and breakdown.largest_sample >= 200:
            if breakdown.human_rcts > 0:
                score += 0.5
                breakdown.bonuses.append(f"Large RCT (n={breakdown.largest_sample})")
        
        # Bonus: Consistent replication
        if breakdown.supporting_studies >= 3 and breakdown.contradicting_studies == 0:
            score += 0.5
            breakdown.bonuses.append("Consistent replication")
        
        return score
    
    def _score_to_grade(self, score: float) -> str:
        """Convert numerical score to letter grade"""
        if score >= 9.5:
            return "A+"
        elif score >= 9.0:
            return "A"
        elif score >= 8.5:
            return "A-"
        elif score >= 8.0:
            return "B+"
        elif score >= 7.0:
            return "B"
        elif score >= 6.0:
            return "B-"
        elif score >= 5.0:
            return "C+"
        elif score >= 4.0:
            return "C"
        elif score >= 3.0:
            return "C-"
        elif score >= 2.0:
            return "D"
        else:
            return "F"


# =============================================================================
# Convenience Functions
# =============================================================================

def score_from_counts(
    human_rcts: int = 0,
    meta_analyses: int = 0,
    human_other: int = 0,
    animal_studies: int = 0,
    avg_sample_size: Optional[int] = None,
    years_since_last: Optional[int] = None,
    contradicting: int = 0
) -> ScoreBreakdown:
    """
    Quick scoring from study counts (without full study objects).
    Useful for manual data entry.
    """
    studies = []
    
    # Create dummy study objects
    for _ in range(meta_analyses):
        studies.append(StudySummary(
            study_type=StudyType.META_ANALYSIS,
            is_human=True,
            sample_size=avg_sample_size,
            supports_claim='yes'
        ))
    
    for _ in range(human_rcts):
        studies.append(StudySummary(
            study_type=StudyType.RCT,
            is_human=True,
            sample_size=avg_sample_size,
            supports_claim='yes'
        ))
    
    for _ in range(human_other):
        studies.append(StudySummary(
            study_type=StudyType.OBSERVATIONAL,
            is_human=True,
            sample_size=avg_sample_size,
            supports_claim='yes'
        ))
    
    for _ in range(animal_studies):
        studies.append(StudySummary(
            study_type=StudyType.ANIMAL,
            is_human=False,
            supports_claim='yes'
        ))
    
    for _ in range(contradicting):
        studies.append(StudySummary(
            study_type=StudyType.RCT,
            is_human=True,
            supports_claim='no'
        ))
    
    # Add year to one study if provided
    if studies and years_since_last is not None:
        studies[0].publication_year = 2025 - years_since_last
    
    scorer = EvidenceScorer()
    return scorer.score_claim(studies)


def print_score_report(breakdown: ScoreBreakdown):
    """Print a formatted score report"""
    print("\n" + "="*60)
    print(f"EVIDENCE SCORE: {breakdown.final_score:.1f}/10 ({breakdown.grade})")
    print("="*60)
    
    print(f"\nStudy Counts:")
    print(f"  • Total studies: {breakdown.total_studies}")
    print(f"  • Meta-analyses: {breakdown.meta_analyses}")
    print(f"  • Human RCTs: {breakdown.human_rcts}")
    print(f"  • Other human studies: {breakdown.human_other}")
    print(f"  • Animal studies: {breakdown.animal_studies}")
    print(f"  • In vitro: {breakdown.in_vitro_studies}")
    
    print(f"\nQuality Metrics:")
    if breakdown.avg_sample_size:
        print(f"  • Avg sample size: {breakdown.avg_sample_size:.0f}")
    if breakdown.largest_sample:
        print(f"  • Largest sample: {breakdown.largest_sample}")
    if breakdown.most_recent_year:
        print(f"  • Most recent: {breakdown.most_recent_year}")
    
    print(f"\nComponent Scores:")
    print(f"  • Quantity:    {breakdown.quantity_score:.1f}/10")
    print(f"  • Quality:     {breakdown.quality_score:.1f}/10")
    print(f"  • Consistency: {breakdown.consistency_score:.1f}/10")
    print(f"  • Recency:     {breakdown.recency_score:.1f}/10")
    print(f"  • Raw Score:   {breakdown.raw_score:.1f}/10")
    
    if breakdown.bonuses:
        print(f"\nBonuses Applied:")
        for bonus in breakdown.bonuses:
            print(f"  ✓ {bonus}")
    
    if breakdown.penalties:
        print(f"\nPenalties Applied:")
        for penalty in breakdown.penalties:
            print(f"  ✗ {penalty}")
    
    print(f"\n{'='*60}")


# =============================================================================
# Example Usage
# =============================================================================

if __name__ == "__main__":
    print("\n" + "#"*60)
    print("# EVIDENCE SCORING EXAMPLES")
    print("#"*60)
    
    # Example 1: Well-researched supplement (Creatine for strength)
    print("\n>>> CREATINE FOR STRENGTH")
    result = score_from_counts(
        human_rcts=15,
        meta_analyses=3,
        human_other=20,
        avg_sample_size=50,
        years_since_last=1
    )
    print_score_report(result)
    
    # Example 2: Moderately researched (Ashwagandha for anxiety)
    print("\n>>> ASHWAGANDHA FOR ANXIETY")
    result = score_from_counts(
        human_rcts=5,
        meta_analyses=1,
        human_other=3,
        avg_sample_size=60,
        years_since_last=2
    )
    print_score_report(result)
    
    # Example 3: Poorly researched (Turkesterone for muscle)
    print("\n>>> TURKESTERONE FOR MUSCLE")
    result = score_from_counts(
        human_rcts=1,
        meta_analyses=0,
        human_other=1,
        animal_studies=3,
        avg_sample_size=20,
        years_since_last=3
    )
    print_score_report(result)
    
    # Example 4: Only animal studies (Fadogia)
    print("\n>>> FADOGIA AGRESTIS FOR TESTOSTERONE")
    result = score_from_counts(
        human_rcts=0,
        meta_analyses=0,
        human_other=0,
        animal_studies=3,
        years_since_last=10
    )
    print_score_report(result)
    
    # Example 5: No studies (Grounding mats)
    print("\n>>> GROUNDING MATS FOR INFLAMMATION")
    result = score_from_counts(
        human_rcts=0,
        meta_analyses=0,
        human_other=2,
        animal_studies=0,
        avg_sample_size=12,
        years_since_last=8
    )
    print_score_report(result)
