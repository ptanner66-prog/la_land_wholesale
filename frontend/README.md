# LA Land Wholesale Dashboard

A modern SaaS dashboard for managing Louisiana land wholesaling operations.

## Tech Stack

- **React 18** - UI Framework
- **TypeScript** - Type safety
- **Vite** - Build tool and dev server
- **TailwindCSS** - Utility-first CSS
- **shadcn/ui** - Component library
- **React Router** - Client-side routing
- **Axios** - HTTP client
- **Lucide React** - Icons
- **Recharts** - Charts

## Getting Started

### Prerequisites

- Node.js 18+
- npm or pnpm

### Installation

```bash
# Install dependencies
npm install

# Start development server
npm run dev
```

The dashboard will be available at `http://localhost:5173`.

### Backend Connection

The dashboard expects the FastAPI backend to be running at `http://localhost:8001`.

To start the backend:
```bash
# From the project root directory
uvicorn src.api.app:app --host 0.0.0.0 --port 8001 --reload
```

You can change the API URL in several ways:
1. Through the Settings page in the dashboard
2. By setting `api_base_url` in localStorage
3. By setting `VITE_API_BASE_URL` environment variable
4. By modifying `src/api/client.ts`

## Project Structure

```
src/
├── api/                 # API client and service wrappers
│   ├── client.ts        # Axios instance configuration
│   ├── leads.ts         # Lead API endpoints
│   ├── owners.ts        # Owner API endpoints
│   ├── parcels.ts       # Parcel API endpoints
│   ├── outreach.ts      # Outreach API endpoints
│   ├── scoring.ts       # Scoring API endpoints
│   ├── ingestion.ts     # Ingestion API endpoints
│   └── health.ts        # Health check endpoints
├── components/
│   ├── layout/          # Layout components
│   │   ├── Sidebar.tsx
│   │   ├── Topbar.tsx
│   │   └── MainLayout.tsx
│   ├── ui/              # shadcn/ui components
│   └── theme-provider.tsx
├── hooks/               # Custom React hooks
│   ├── useLeads.ts
│   └── useOutreach.ts
├── lib/
│   ├── types.ts         # TypeScript types
│   ├── utils.ts         # Utility functions
│   └── format.ts        # Formatting helpers
├── pages/               # Page components
│   ├── Dashboard.tsx
│   ├── Leads.tsx
│   ├── LeadDetail.tsx
│   ├── Outreach.tsx
│   ├── Owners.tsx
│   ├── Parcels.tsx
│   ├── Ingestion.tsx
│   └── Settings.tsx
├── App.tsx              # Main app component
├── main.tsx             # Entry point
└── index.css            # Global styles
```

## Features

### Dashboard
- Overview metrics (total leads, owners, outreach stats)
- Lead status breakdown
- Quick action links
- System configuration display

### Leads Management
- List all leads with filtering
- Search by name, address, or parcel ID
- Manual lead entry with enrichment
- Lead detail view with full information
- Status management
- Lead rescoring

### Outreach
- View all outreach attempts
- Batch outreach with configuration
- Dry run support
- Status tracking

### Owners
- List all property owners
- Search functionality
- TCPA status management
- DNR list management

### Parcels
- Browse all parcels
- View adjudicated properties
- Tax delinquent filtering
- Assessment data display

### Data Ingestion
- Run individual ingestion jobs
- Full pipeline execution
- Lead scoring
- Status monitoring

### Settings
- Theme switching (light/dark/system)
- API URL configuration
- External services status
- System health display

## Customization

### Theme

The dashboard supports light and dark themes. Theme preference is stored in localStorage.

### API Configuration

The API base URL can be configured:
1. Through the Settings page
2. By setting `api_base_url` in localStorage
3. By modifying `src/api/client.ts`

## Building for Production

```bash
npm run build
```

The built files will be in the `dist` directory.

## License

MIT

