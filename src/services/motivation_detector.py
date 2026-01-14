"""Motivation Spike Detector for Lead Prioritization.

This module detects high-motivation leads based on:
- Behavioral signals (reply patterns, engagement)
- Property indicators (tax delinquency spikes, adjudication)
- Market signals (price drops, listing expirations)
- Temporal patterns (time-sensitive situations)

Designed to surface the hottest leads for immediate action.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from core.config import get_settings
from core.logging_config import get_logger
from core.models import Lead, Owner, Parcel, OutreachAttempt, TimelineEvent
from core.utils import utcnow, ensure_aware

LOGGER = get_logger(__name__)
SETTINGS = get_settings()


@dataclass
class MotivationSignal:
    """A single motivation indicator."""
    signal_type: str
    severity: str  # low, medium, high, critical
    score_impact: int
    description: str
    detected_at: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "signal_type": self.signal_type,
            "severity": self.severity,
            "score_impact": self.score_impact,
            "description": self.description,
            "detected_at": self.detected_at.isoformat() if self.detected_at else None,
            "metadata": self.metadata,
        }


@dataclass
class MotivationSpikeResult:
    """Result of motivation spike analysis."""
    lead_id: int
    is_spike_detected: bool
    spike_severity: str  # none, moderate, high, critical
    total_spike_score: int
    signals: List[MotivationSignal]
    recommendation: str
    priority_rank: int
    needs_immediate_action: bool
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "lead_id": self.lead_id,
            "is_spike_detected": self.is_spike_detected,
            "spike_severity": self.spike_severity,
            "total_spike_score": self.total_spike_score,
            "signals": [s.to_dict() for s in self.signals],
            "recommendation": self.recommendation,
            "priority_rank": self.priority_rank,
            "needs_immediate_action": self.needs_immediate_action,
        }


class MotivationSpikeDetector:
    """
    Detects motivation spikes in leads.
    
    Monitors for:
    1. Reply engagement patterns
    2. Property distress signals
    3. Time-based urgency
    4. Market movement indicators
    """
    
    # Signal severity thresholds
    SEVERITY_THRESHOLDS = {
        "critical": 50,  # Immediate action required
        "high": 35,
        "moderate": 20,
        "low": 10,
    }
    
    # Signal weights by type
    SIGNAL_WEIGHTS = {
        # Reply signals
        "positive_reply": 25,
        "interested_reply": 35,
        "price_inquiry": 30,
        "callback_request": 40,
        "multiple_replies": 20,
        
        # Property signals
        "new_adjudication": 30,
        "tax_delinquency_increase": 20,
        "vacancy_detected": 15,
        "code_violation": 25,
        
        # Time signals
        "deadline_approaching": 35,
        "listing_expired": 20,
        "price_reduction": 25,
        
        # Behavioral signals
        "quick_response": 15,
        "multiple_properties": 20,
        "referred_lead": 25,
    }
    
    def __init__(self, session: Session):
        """Initialize the detector with a database session."""
        self.session = session
        self.now = utcnow()
    
    def analyze_lead(self, lead_id: int) -> MotivationSpikeResult:
        """
        Analyze a single lead for motivation spikes.
        
        Args:
            lead_id: The lead ID to analyze.
        
        Returns:
            MotivationSpikeResult with signals and recommendations.
        """
        lead = self.session.query(Lead).filter(Lead.id == lead_id).first()
        if not lead:
            return self._empty_result(lead_id)
        
        signals: List[MotivationSignal] = []
        
        # 1. Check reply engagement
        signals.extend(self._analyze_replies(lead))
        
        # 2. Check property distress
        signals.extend(self._analyze_property_distress(lead))
        
        # 3. Check time-based factors
        signals.extend(self._analyze_temporal_signals(lead))
        
        # 4. Check behavioral patterns
        signals.extend(self._analyze_behavioral_patterns(lead))
        
        # Calculate total spike score
        total_score = sum(s.score_impact for s in signals)
        
        # Determine severity
        if total_score >= self.SEVERITY_THRESHOLDS["critical"]:
            severity = "critical"
            recommendation = "IMMEDIATE ACTION: High-motivation lead - contact within 1 hour"
            needs_immediate = True
        elif total_score >= self.SEVERITY_THRESHOLDS["high"]:
            severity = "high"
            recommendation = "HIGH PRIORITY: Contact today with a strong offer"
            needs_immediate = True
        elif total_score >= self.SEVERITY_THRESHOLDS["moderate"]:
            severity = "moderate"
            recommendation = "Follow up promptly - motivation indicators detected"
            needs_immediate = False
        else:
            severity = "none"
            recommendation = "Standard follow-up schedule"
            needs_immediate = False
        
        is_spike = total_score >= self.SEVERITY_THRESHOLDS["low"]
        
        return MotivationSpikeResult(
            lead_id=lead_id,
            is_spike_detected=is_spike,
            spike_severity=severity,
            total_spike_score=total_score,
            signals=signals,
            recommendation=recommendation,
            priority_rank=self._calculate_priority_rank(total_score, lead.motivation_score),
            needs_immediate_action=needs_immediate,
        )
    
    def find_spiking_leads(
        self,
        market_code: Optional[str] = None,
        min_score: int = 20,
        limit: int = 50,
    ) -> List[MotivationSpikeResult]:
        """
        Find all leads with motivation spikes.
        
        Args:
            market_code: Optional filter by market.
            min_score: Minimum spike score to include.
            limit: Maximum results to return.
        
        Returns:
            List of MotivationSpikeResult sorted by priority.
        """
        query = self.session.query(Lead)
        
        if market_code:
            query = query.filter(Lead.market_code == market_code.upper())
        
        # Filter for active leads
        query = query.filter(Lead.status.notin_(["closed", "dnc", "dead"]))
        
        leads = query.all()
        
        results = []
        for lead in leads:
            result = self.analyze_lead(lead.id)
            if result.total_spike_score >= min_score:
                results.append(result)
        
        # Sort by priority (spike score + base motivation)
        results.sort(key=lambda r: r.priority_rank, reverse=True)
        
        return results[:limit]
    
    def _analyze_replies(self, lead: Lead) -> List[MotivationSignal]:
        """Analyze reply engagement patterns."""
        signals = []
        
        # Get recent outreach attempts
        attempts = (
            self.session.query(OutreachAttempt)
            .filter(OutreachAttempt.lead_id == lead.id)
            .order_by(OutreachAttempt.created_at.desc())
            .limit(10)
            .all()
        )
        
        # Count replies in last 7 days
        recent_replies = 0
        for attempt in attempts:
            if attempt.response_body:
                created_at = ensure_aware(attempt.created_at)
                if created_at and self.now - created_at < timedelta(days=7):
                    recent_replies += 1
        
        # Multiple replies signal
        if recent_replies >= 2:
            signals.append(MotivationSignal(
                signal_type="multiple_replies",
                severity="high",
                score_impact=self.SIGNAL_WEIGHTS["multiple_replies"],
                description=f"Multiple replies ({recent_replies}) in last 7 days",
                detected_at=self.now,
                metadata={"reply_count": recent_replies},
            ))
        
        # Check reply classifications
        for attempt in attempts:
            if attempt.reply_classification in ["INTERESTED", "WARM"]:
                signals.append(MotivationSignal(
                    signal_type="interested_reply",
                    severity="critical",
                    score_impact=self.SIGNAL_WEIGHTS["interested_reply"],
                    description="Owner expressed interest",
                    detected_at=ensure_aware(attempt.created_at) or self.now,
                    metadata={"classification": attempt.reply_classification},
                ))
                break  # Only count once
            elif attempt.reply_classification == "PRICE_INQUIRY":
                signals.append(MotivationSignal(
                    signal_type="price_inquiry",
                    severity="high",
                    score_impact=self.SIGNAL_WEIGHTS["price_inquiry"],
                    description="Owner asked about price",
                    detected_at=ensure_aware(attempt.created_at) or self.now,
                ))
                break
        
        # Quick response (within 2 hours of outreach)
        for attempt in attempts:
            if attempt.response_body and attempt.sent_at and attempt.created_at:
                sent = ensure_aware(attempt.sent_at)
                response = ensure_aware(attempt.created_at)
                if sent and response and (response - sent) < timedelta(hours=2):
                    signals.append(MotivationSignal(
                        signal_type="quick_response",
                        severity="medium",
                        score_impact=self.SIGNAL_WEIGHTS["quick_response"],
                        description="Quick response to outreach",
                        detected_at=response,
                    ))
                    break
        
        return signals
    
    def _analyze_property_distress(self, lead: Lead) -> List[MotivationSignal]:
        """Analyze property distress indicators."""
        signals = []
        parcel = lead.parcel
        
        if not parcel:
            return signals
        
        # Adjudicated property
        if parcel.is_adjudicated:
            signals.append(MotivationSignal(
                signal_type="new_adjudication",
                severity="high",
                score_impact=self.SIGNAL_WEIGHTS["new_adjudication"],
                description="Property is adjudicated (tax sale)",
                detected_at=self.now,
            ))
        
        # High tax delinquency
        if parcel.years_tax_delinquent >= 3:
            signals.append(MotivationSignal(
                signal_type="tax_delinquency_increase",
                severity="high",
                score_impact=self.SIGNAL_WEIGHTS["tax_delinquency_increase"],
                description=f"Severe tax delinquency: {parcel.years_tax_delinquent} years",
                detected_at=self.now,
                metadata={"years": parcel.years_tax_delinquent},
            ))
        elif parcel.years_tax_delinquent >= 1:
            signals.append(MotivationSignal(
                signal_type="tax_delinquency_increase",
                severity="medium",
                score_impact=self.SIGNAL_WEIGHTS["tax_delinquency_increase"] // 2,
                description=f"Tax delinquent: {parcel.years_tax_delinquent} year(s)",
                detected_at=self.now,
                metadata={"years": parcel.years_tax_delinquent},
            ))
        
        # Low/no improvements (vacant land motivation)
        if parcel.improvement_assessed_value is not None:
            imp_val = float(parcel.improvement_assessed_value or 0)
            land_val = float(parcel.land_assessed_value or 1)
            if imp_val < land_val * 0.05:  # Less than 5% improvements
                signals.append(MotivationSignal(
                    signal_type="vacancy_detected",
                    severity="medium",
                    score_impact=self.SIGNAL_WEIGHTS["vacancy_detected"],
                    description="Vacant or unimproved land",
                    detected_at=self.now,
                ))
        
        return signals
    
    def _analyze_temporal_signals(self, lead: Lead) -> List[MotivationSignal]:
        """Analyze time-based urgency factors."""
        signals = []
        
        # Check if follow-up is overdue
        if lead.next_followup_at:
            next_followup = ensure_aware(lead.next_followup_at)
            if next_followup and self.now > next_followup:
                overdue_days = (self.now - next_followup).days
                if overdue_days >= 7:
                    signals.append(MotivationSignal(
                        signal_type="deadline_approaching",
                        severity="high",
                        score_impact=self.SIGNAL_WEIGHTS["deadline_approaching"],
                        description=f"Follow-up overdue by {overdue_days} days",
                        detected_at=self.now,
                        metadata={"overdue_days": overdue_days},
                    ))
        
        # Check timeline for price reduction events
        events = (
            self.session.query(TimelineEvent)
            .filter(
                TimelineEvent.lead_id == lead.id,
                TimelineEvent.event_type == "price_reduction",
            )
            .order_by(TimelineEvent.created_at.desc())
            .limit(1)
            .all()
        )
        
        for event in events:
            created = ensure_aware(event.created_at)
            if created and self.now - created < timedelta(days=14):
                signals.append(MotivationSignal(
                    signal_type="price_reduction",
                    severity="high",
                    score_impact=self.SIGNAL_WEIGHTS["price_reduction"],
                    description="Recent price reduction detected",
                    detected_at=created,
                ))
        
        return signals
    
    def _analyze_behavioral_patterns(self, lead: Lead) -> List[MotivationSignal]:
        """Analyze behavioral patterns indicating motivation."""
        signals = []
        owner = lead.owner
        
        if not owner:
            return signals
        
        # Check if owner has multiple properties
        owner_leads = (
            self.session.query(Lead)
            .filter(Lead.owner_id == owner.id)
            .count()
        )
        
        if owner_leads >= 2:
            signals.append(MotivationSignal(
                signal_type="multiple_properties",
                severity="medium",
                score_impact=self.SIGNAL_WEIGHTS["multiple_properties"],
                description=f"Owner has {owner_leads} properties",
                detected_at=self.now,
                metadata={"property_count": owner_leads},
            ))
        
        return signals
    
    def _calculate_priority_rank(self, spike_score: int, base_score: int) -> int:
        """Calculate overall priority rank."""
        # Combine spike score (weighted more) with base motivation
        return int(spike_score * 1.5) + base_score
    
    def _empty_result(self, lead_id: int) -> MotivationSpikeResult:
        """Return empty result for missing lead."""
        return MotivationSpikeResult(
            lead_id=lead_id,
            is_spike_detected=False,
            spike_severity="none",
            total_spike_score=0,
            signals=[],
            recommendation="Lead not found",
            priority_rank=0,
            needs_immediate_action=False,
        )


def get_motivation_detector(session: Session) -> MotivationSpikeDetector:
    """Get a MotivationSpikeDetector instance."""
    return MotivationSpikeDetector(session)


def detect_spike(session: Session, lead_id: int) -> MotivationSpikeResult:
    """
    Convenience function to detect motivation spike for a lead.
    """
    detector = get_motivation_detector(session)
    return detector.analyze_lead(lead_id)


def find_hot_leads(
    session: Session,
    market_code: Optional[str] = None,
    limit: int = 20,
) -> List[MotivationSpikeResult]:
    """
    Convenience function to find hot leads with motivation spikes.
    """
    detector = get_motivation_detector(session)
    return detector.find_spiking_leads(
        market_code=market_code,
        min_score=20,
        limit=limit,
    )


__all__ = [
    "MotivationSpikeDetector",
    "MotivationSpikeResult",
    "MotivationSignal",
    "get_motivation_detector",
    "detect_spike",
    "find_hot_leads",
]

