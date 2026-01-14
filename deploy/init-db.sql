-- =============================================================================
-- LA Land Wholesale - Database Initialization Script
-- Runs on first container start
-- =============================================================================

-- Enable PostGIS extension
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;

-- Create any additional extensions
CREATE EXTENSION IF NOT EXISTS pg_trgm;  -- For fuzzy text matching
CREATE EXTENSION IF NOT EXISTS btree_gist;  -- For better indexing

-- Log successful initialization
DO $$
BEGIN
    RAISE NOTICE 'Database initialized with PostGIS version: %', PostGIS_Version();
END $$;
