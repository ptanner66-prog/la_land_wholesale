"""External data services for LA Land Wholesale.

This module provides integrations with:
- Google Maps Geocoding API
- USPS Address Verification
- Zillow/Redfin Comps Scraping
- EBR County Records Scraping
- Multi-market support
- Reply classification
- Offer calculation
- Followup automation
- Hot lead notifications

All services have:
- Feature flag checks (ENABLE_* in .env)
- Graceful fallbacks (disabled/missing API key returns sensible defaults)
- Caching (TTLCache for repeated lookups)
- Retry logic (with exponential backoff)
- Structured logging
"""
from __future__ import annotations

# Cache utilities
from .cache import (
    TTLCache,
    CacheEntry,
    get_geocode_cache,
    get_usps_cache,
    get_comps_cache,
    cached,
)

# Retry utilities
from .retry import (
    with_retry,
    with_timeout,
    timed_call,
    RetryContext,
    RETRY_NETWORK,
    RETRY_RATE_LIMIT,
    RETRY_SERVICE,
)

# Google Maps
from .google_maps import (
    GoogleMapsService,
    GeocodeResult,
    geocode,
    reverse_geocode,
    get_google_maps_service,
)

# USPS
from .usps import (
    USPSService,
    USPSVerificationResult,
    verify_address,
    get_usps_service,
)

# Comps
from .comps import (
    CompsService,
    CompsResult,
    CompSale,
    get_comps_service,
)

# County Scraper
from .county_scraper import (
    CountyScraperService,
    CountySaleRecord,
    scrape_recent_sales,
    get_county_scraper_service,
)

# Orchestrator
from .external_data import (
    ExternalDataService,
    EnrichedLeadData,
    EnrichmentSummary,
    get_external_data_service,
)

# Market configuration
from .market import (
    MarketService,
    MarketConfig,
    get_market_service,
    MARKET_CONFIGS,
)

# Timeline tracking
from .timeline import (
    TimelineService,
    TimelineEventType,
    get_timeline_service,
)

# Reply classification
from .reply_classifier import (
    ReplyClassifierService,
    get_reply_classifier,
)

# Followup automation
from .followup import (
    FollowupService,
    get_followup_service,
)

# Offer calculation
from .offer_calculator import (
    OfferCalculatorService,
    OfferResult,
    get_offer_calculator,
)

# Message generation
from .message_generator import (
    MessageGeneratorService,
    MessageVariant,
    get_message_generator,
)

# Notifications
from .notification import (
    NotificationService,
    get_notification_service,
)

# Scheduler
from .scheduler import (
    SchedulerService,
    get_scheduler_service,
)

# Outreach validation
from .outreach_validator import (
    OutreachValidator,
    OutreachValidationError,
    ValidationResult,
    get_outreach_validator,
)

# Locking services
from .locking import (
    SendLockService,
    SchedulerLockService,
    LockAcquisitionError,
    get_send_lock_service,
    get_scheduler_lock_service,
)

# Idempotency
from .idempotency import (
    IdempotencyService,
    get_idempotency_service,
)

# Task tracking
from .task_tracker import (
    TaskTracker,
    get_task_tracker,
)

# Webhook security
from .webhook_security import (
    TwilioSignatureValidator,
    verify_twilio_signature,
)

# Buyer services
from .buyer import (
    BuyerService,
    BuyerSummary,
    BuyerDetail,
    BuyerCreate,
    get_buyer_service,
)

from .buyer_match import (
    BuyerMatchService,
    BuyerMatch,
    MatchScore,
    get_buyer_match_service,
)

from .buyer_blast import (
    BuyerBlastService,
    BlastResult,
    get_buyer_blast_service,
)

# Disposition services
from .deal_sheet import (
    DealSheetService,
    DealSheetContent,
    get_deal_sheet_service,
)

from .call_script import (
    CallScript,
    generate_call_script,
)

# PropStream
from .propstream import (
    PropStreamService,
    PropStreamProperty,
    PropStreamOwner,
    get_propstream_service,
    is_propstream_available,
)

# Enrichment Pipeline
from .enrichment_pipeline import (
    EnrichmentPipeline,
    EnrichedLead,
    get_enrichment_pipeline,
)

# Conversation Engine
from .conversation_engine import (
    ConversationEngine,
    ConversationIntent,
    ConversationAction,
    get_conversation_engine,
)

# Contract Generator
from .contract_generator import (
    ContractGenerator,
    ContractDocument,
    get_contract_generator,
)

# Skip Trace
from .skip_trace import (
    SkipTraceService,
    SkipTraceResult,
    PhoneNumber,
    EmailAddress,
    get_skip_trace_service,
    skip_trace_person,
)

# Assignment Fee Optimizer
from .assignment_fee_optimizer import (
    AssignmentFeeOptimizer,
    AssignmentFeeRange,
    DealAnalysis,
    get_assignment_fee_optimizer,
    calculate_assignment_fee,
)

# Motivation Spike Detector
from .motivation_detector import (
    MotivationSpikeDetector,
    MotivationSpikeResult,
    MotivationSignal,
    get_motivation_detector,
    detect_spike,
    find_hot_leads,
)

__all__ = [
    # Cache utilities
    "TTLCache",
    "CacheEntry",
    "get_geocode_cache",
    "get_usps_cache",
    "get_comps_cache",
    "cached",
    # Retry utilities
    "with_retry",
    "with_timeout",
    "timed_call",
    "RetryContext",
    "RETRY_NETWORK",
    "RETRY_RATE_LIMIT",
    "RETRY_SERVICE",
    # Google Maps
    "GoogleMapsService",
    "GeocodeResult",
    "geocode",
    "reverse_geocode",
    "get_google_maps_service",
    # USPS
    "USPSService",
    "USPSVerificationResult",
    "verify_address",
    "get_usps_service",
    # Comps
    "CompsService",
    "CompsResult",
    "CompSale",
    "get_comps_service",
    # County Scraper
    "CountyScraperService",
    "CountySaleRecord",
    "scrape_recent_sales",
    "get_county_scraper_service",
    # Orchestrator
    "ExternalDataService",
    "EnrichedLeadData",
    "EnrichmentSummary",
    "get_external_data_service",
    # Market
    "MarketService",
    "MarketConfig",
    "get_market_service",
    "MARKET_CONFIGS",
    # Timeline
    "TimelineService",
    "TimelineEventType",
    "get_timeline_service",
    # Reply Classifier
    "ReplyClassifierService",
    "get_reply_classifier",
    # Followup
    "FollowupService",
    "get_followup_service",
    # Offer Calculator
    "OfferCalculatorService",
    "OfferResult",
    "get_offer_calculator",
    # Message Generator
    "MessageGeneratorService",
    "MessageVariant",
    "get_message_generator",
    # Notification
    "NotificationService",
    "get_notification_service",
    # Scheduler
    "SchedulerService",
    "get_scheduler_service",
    # Outreach Validation
    "OutreachValidator",
    "OutreachValidationError",
    "ValidationResult",
    "get_outreach_validator",
    # Locking
    "SendLockService",
    "SchedulerLockService",
    "LockAcquisitionError",
    "get_send_lock_service",
    "get_scheduler_lock_service",
    # Idempotency
    "IdempotencyService",
    "get_idempotency_service",
    # Task Tracking
    "TaskTracker",
    "get_task_tracker",
    # Webhook Security
    "TwilioSignatureValidator",
    "verify_twilio_signature",
    # Buyer Services
    "BuyerService",
    "BuyerSummary",
    "BuyerDetail",
    "BuyerCreate",
    "get_buyer_service",
    "BuyerMatchService",
    "BuyerMatch",
    "MatchScore",
    "get_buyer_match_service",
    "BuyerBlastService",
    "BlastResult",
    "get_buyer_blast_service",
    # Disposition Services
    "DealSheetService",
    "DealSheetContent",
    "get_deal_sheet_service",
    "CallScriptService",
    "CallScript",
    "get_call_script_service",
    # PropStream
    "PropStreamService",
    "PropStreamProperty",
    "PropStreamOwner",
    "get_propstream_service",
    "is_propstream_available",
    # Enrichment Pipeline
    "EnrichmentPipeline",
    "EnrichedLead",
    "get_enrichment_pipeline",
    # Conversation Engine
    "ConversationEngine",
    "ConversationIntent",
    "ConversationAction",
    "get_conversation_engine",
    # Contract Generator
    "ContractGenerator",
    "ContractDocument",
    "get_contract_generator",
    # Skip Trace
    "SkipTraceService",
    "SkipTraceResult",
    "PhoneNumber",
    "EmailAddress",
    "get_skip_trace_service",
    "skip_trace_person",
    # Assignment Fee Optimizer
    "AssignmentFeeOptimizer",
    "AssignmentFeeRange",
    "DealAnalysis",
    "get_assignment_fee_optimizer",
    "calculate_assignment_fee",
    # Motivation Spike Detector
    "MotivationSpikeDetector",
    "MotivationSpikeResult",
    "MotivationSignal",
    "get_motivation_detector",
    "detect_spike",
    "find_hot_leads",
]
