# LA Land Wholesale - Real Estate Wholesaling Platform

A comprehensive Louisiana land wholesaling automation platform with lead ingestion, enrichment, motivation scoring, SMS automation, buyer matching, and deal management.

## Quick Start

### Prerequisites
- Python 3.10+
- Node.js 18+ (for frontend)
- SQLite (default) or PostgreSQL

### Backend Setup

1. **Create virtual environment:**
```bash
python -m venv .venv
.venv\Scripts\activate  # Windows
# or
source .venv/bin/activate  # Linux/Mac
```

2. **Install dependencies:**
```bash
pip install -r requirements.txt
```

3. **Configure environment:**
```bash
# Copy the example env file
cp .env.example .env

# Edit .env and fill in your API keys:
# - ANTHROPIC_API_KEY (Claude AI)
# - TWILIO_* (SMS sending)
# - GOOGLE_MAPS_API_KEY (Geocoding)
```

4. **Run database migrations:**
```bash
python -m alembic upgrade head
```

5. **Start the backend:**
```bash
uvicorn src.api.app:app --host 0.0.0.0 --port 8001 --reload
```

The API will be available at `http://localhost:8001`
- API Docs: `http://localhost:8001/docs`
- Health Check: `http://localhost:8001/`

### Frontend Setup

1. **Navigate to frontend:**
```bash
cd frontend
```

2. **Install dependencies:**
```bash
npm install
```

3. **Start development server:**
```bash
npm run dev
```

The dashboard will be available at `http://localhost:5173`

## Architecture

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Ingestion  │────▶│  Enrichment  │────▶│   Scoring    │
│   Pipeline   │     │   Pipeline   │     │   Engine     │
└──────────────┘     └──────────────┘     └──────────────┘
       │                    │                    │
       │                    │                    ▼
       │                    │            ┌──────────────┐
       │                    │            │    Deal      │
       │                    │            │   Sheet      │
       │                    │            └──────────────┘
       │                    │                    │
       ▼                    ▼                    ▼
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Outreach   │◀────│    Buyer     │◀────│ Disposition  │
│   Engine     │     │   Matching   │     │   Engine     │
└──────────────┘     └──────────────┘     └──────────────┘
       │                    │                    │
       │                    ▼                    │
       │            ┌──────────────┐             │
       │            │    Blast     │             │
       │            │   Engine     │             │
       │            └──────────────┘             │
       │                    │                    │
       └────────────────────┴────────────────────┘
                           │
                           ▼
                    ┌──────────────┐
                    │   Twilio     │
                    │   (SMS)      │
                    └──────────────┘
```

## Data Flow

1. **Ingestion** → Raw leads from county records, tax rolls, adjudicated lists
2. **Enrichment** → USPS verification, Google Maps geocoding, comps lookup
3. **Scoring** → AI-powered motivation scoring based on property/owner factors
4. **Deal Sheet** → Generate offer ranges, assignment fees, buyer descriptions
5. **Buyer Matching** → Match leads to buyers by criteria (market, acreage, budget)
6. **Blast Engine** → Send templated messages to matched buyers via SMS/email
7. **Outreach** → SMS conversation automation with sellers via Twilio

## Key Features

### Lead Engine
- Multi-source lead ingestion (EBR tax roll, adjudicated, GIS)
- Address standardization via USPS API
- Geocoding via Google Maps API
- Property classification (vacant land, residential, commercial)
- Owner profiling (absentee, corporate, trust detection)

### Offer Engine
- MAO (Maximum Allowable Offer) calculation
- Risk-adjusted pricing based on motivation score
- Comparable sales analysis
- Assignment fee optimization

### Disposition Engine
- Intelligent buyer matching by criteria
- Match scoring with detailed factor breakdown
- Deal sheet generation with AI descriptions
- Buyer blast messaging

### Outreach Engine
- Claude-powered message generation
- Reply intent classification
- STOP/DNC enforcement
- Follow-up sequence automation

## API Endpoints

### Core Endpoints
- `GET /` - Health check
- `GET /docs` - Swagger UI
- `GET /detailed` - Detailed service status

### Leads
- `GET /leads/` - List leads
- `POST /leads/manual` - Create lead manually
- `GET /leads/{id}` - Get lead details
- `GET /leads/{id}/offer` - Calculate offer
- `GET /leads/{id}/comps` - Get comparable sales
- `GET /leads/{id}/timeline` - Get activity timeline

### Buyers
- `GET /buyers/` - List buyers
- `POST /buyers/` - Create buyer
- `POST /buyers/match/{lead_id}` - Match buyers to lead
- `POST /buyers/blast/{lead_id}` - Send buyer blast

### Dispositions
- `GET /dispo/dealsheet/{lead_id}` - Generate deal sheet
- `GET /dispo/callscript/{lead_id}` - Generate call script
- `GET /dispo/matches/{lead_id}` - Get buyer matches
- `GET /dispo/assignment-fee/{lead_id}` - Calculate assignment fee
- `GET /dispo/lead/{lead_id}/disposition-summary` - Full disposition summary

### Scoring
- `GET /scoring/config` - Get scoring weights
- `GET /scoring/spikes` - Find high-motivation leads
- `GET /scoring/spike/{lead_id}` - Analyze specific lead

### Dashboard
- `GET /dashboard/pipeline/stats` - Pipeline statistics
- `GET /markets/` - Available markets

## Configuration

### Environment Variables

```bash
# Core
DATABASE_URL=sqlite:///./la_land_wholesale.db
ENVIRONMENT=development
DRY_RUN=true  # Set to false for production

# Claude AI
ANTHROPIC_API_KEY=sk-ant-api03-...

# Twilio SMS
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
TWILIO_FROM_NUMBER=+1...

# Google Maps
GOOGLE_MAPS_API_KEY=AIza...
ENABLE_GOOGLE=true

# Optional Services
USPS_USER_ID=  # Add for address verification
ENABLE_USPS=false

PROPSTREAM_API_KEY=  # Add for property data
ENABLE_PROPSTREAM=false
```

### Feature Flags
- `ENABLE_GOOGLE` - Google Maps geocoding
- `ENABLE_USPS` - USPS address verification
- `ENABLE_PROPSTREAM` - PropStream property data
- `ENABLE_COMPS` - Comparable sales lookup
- `DRY_RUN` - Prevent actual SMS sends

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_core_flows.py -v

# Run with coverage
pytest tests/ --cov=src --cov-report=html
```

## Project Structure

```
la_land_wholesale/
├── src/
│   ├── api/              # FastAPI routes
│   │   ├── routes/       # Route handlers
│   │   └── deps.py       # Dependencies
│   ├── core/             # Core utilities
│   │   ├── config.py     # Settings
│   │   ├── models.py     # SQLAlchemy models
│   │   └── db.py         # Database setup
│   ├── domain/           # Business logic
│   ├── services/         # External integrations
│   ├── ingestion/        # Lead ingestion
│   ├── outreach/         # SMS/Twilio
│   ├── scoring/          # Motivation scoring
│   └── llm/              # AI/Claude integration
├── frontend/             # React dashboard
├── alembic/              # Database migrations
├── tests/                # Test suite
└── requirements.txt      # Python dependencies
```

## License

Proprietary - All rights reserved

