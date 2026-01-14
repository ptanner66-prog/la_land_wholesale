"""Streamlit dashboard for LA Land Wholesale Engine.

Requires: API server running at http://localhost:8000
Start API: cd src && python cli.py server
Start Dashboard: streamlit run dashboard/streamlit_app.py
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Optional, Dict, Any, List

import httpx
import pandas as pd
import streamlit as st

# Configuration
API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")

st.set_page_config(
    page_title="LA Land Wholesale",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded",
)


# =============================================================================
# API Helper Functions
# =============================================================================


def api_request(
    method: str,
    endpoint: str,
    json: Optional[Dict] = None,
    params: Optional[Dict] = None,
    timeout: float = 30.0,
) -> Any:
    """Make API request with error handling."""
    try:
        with httpx.Client(base_url=API_BASE_URL, timeout=timeout) as client:
            if method == "GET":
                resp = client.get(endpoint, params=params)
            elif method == "POST":
                resp = client.post(endpoint, json=json, params=params)
            elif method == "PATCH":
                resp = client.patch(endpoint, json=json, params=params)
            else:
                raise ValueError(f"Unsupported method: {method}")

            resp.raise_for_status()
            return resp.json()
    except httpx.ConnectError:
        st.error(f"❌ Cannot connect to API at {API_BASE_URL}. Is the server running?")
        st.info("💡 Start the API server with: `cd src && python cli.py server`")
        return None
    except httpx.HTTPStatusError as e:
        st.error(f"API Error: {e.response.status_code} - {e.response.text}")
        return None
    except Exception as e:
        st.error(f"Request Failed: {e}")
        return None


def check_api_health() -> bool:
    """Check if API is responding."""
    try:
        with httpx.Client(base_url=API_BASE_URL, timeout=5.0) as client:
            resp = client.get("/health")
            return resp.status_code == 200
    except Exception:
        return False


# =============================================================================
# Sidebar
# =============================================================================


def render_sidebar() -> None:
    """Render sidebar with system info and navigation."""
    with st.sidebar:
        st.title("🏠 LA Land Wholesale")
        st.caption("Automated Real Estate Wholesaling")

        st.divider()

        # System health
        st.subheader("🔌 System Status")
        if check_api_health():
            st.success("✅ API Online")
        else:
            st.error("❌ API Offline")
            st.caption(f"Expected at: {API_BASE_URL}")

        st.divider()

        # Quick stats
        st.subheader("📊 Quick Stats")
        stats = api_request("GET", "/leads/statistics")
        if stats:
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Total Leads", stats.get("total_leads", 0))
                st.metric("TCPA Safe", stats.get("tcpa_safe_leads", 0))
            with col2:
                st.metric("High Score", stats.get("high_score_leads", 0))
                st.metric("Avg Score", f"{stats.get('average_score', 0):.1f}")
        
        st.divider()
        
        # Config info
        st.subheader("⚙️ Config")
        config = api_request("GET", "/scoring/config")
        if config:
            st.caption(f"Min Score: {config.get('thresholds', {}).get('min_motivation_score', 65)}")


# =============================================================================
# Tab 1: Overview Dashboard
# =============================================================================


def render_overview_tab() -> None:
    """Render main dashboard overview."""
    st.header("📊 Dashboard Overview")

    # Health check banner
    if not check_api_health():
        st.warning("⚠️ API server is not running. Start it with: `cd src && python cli.py server`")
        return

    # Row 1: Key Metrics
    col1, col2, col3, col4 = st.columns(4)

    stats = api_request("GET", "/leads/statistics")
    outreach_stats = api_request("GET", "/outreach/stats")

    if stats:
        with col1:
            st.metric("📋 Total Leads", stats.get("total_leads", 0))
        with col2:
            st.metric("🎯 High Value Leads", stats.get("high_score_leads", 0))
        with col3:
            st.metric("✅ TCPA Safe", stats.get("tcpa_safe_leads", 0))
        with col4:
            avg = stats.get("average_score", 0)
            st.metric("📈 Avg Score", f"{avg:.1f}")

    st.divider()

    # Row 2: Charts
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("📊 Score Distribution")
        distribution = api_request("GET", "/scoring/distribution")
        if distribution:
            dist_data = distribution.get("distribution", {})
            if dist_data:
                df = pd.DataFrame({
                    "Score Range": list(dist_data.keys()),
                    "Count": list(dist_data.values()),
                })
                st.bar_chart(df.set_index("Score Range"))
        else:
            st.info("No score data available")

    with col2:
        st.subheader("📱 Outreach Stats")
        if outreach_stats:
            col2a, col2b = st.columns(2)
            with col2a:
                st.metric("Total Sent", outreach_stats.get("total_sent", 0))
            with col2b:
                st.metric("Dry Runs", outreach_stats.get("total_dry_run", 0))
            st.caption(f"Max per day: {outreach_stats.get('max_per_day', 0)}")
        else:
            st.info("No outreach data available")

    st.divider()

    # Row 3: Status Breakdown
    st.subheader("📋 Lead Status Breakdown")
    if stats:
        status_breakdown = stats.get("status_breakdown", {})
        if status_breakdown:
            cols = st.columns(len(status_breakdown))
            for i, (status, count) in enumerate(status_breakdown.items()):
                with cols[i]:
                    st.metric(status.title(), count)
        else:
            st.info("No status data available")

    # Row 4: Recent Activity Log
    st.subheader("📜 Recent Outreach Activity")
    history = api_request("GET", "/outreach/history", params={"limit": 10})
    if history and len(history) > 0:
        df = pd.DataFrame(history)
        display_cols = ["lead_id", "channel", "result", "created_at"]
        available = [c for c in display_cols if c in df.columns]
        st.dataframe(df[available], use_container_width=True, hide_index=True)
    else:
        st.info("No recent outreach activity")


# =============================================================================
# Tab 2: Lead Explorer
# =============================================================================


def render_lead_explorer_tab() -> None:
    """Render lead exploration and search tab."""
    st.header("🔍 Lead Explorer")

    # Search Section
    st.subheader("Search Leads")
    col1, col2 = st.columns([3, 1])
    
    with col1:
        search_query = st.text_input(
            "Search by owner name, address, or parcel ID",
            placeholder="Enter search term...",
            key="lead_search"
        )
    
    with col2:
        search_button = st.button("🔍 Search", use_container_width=True)

    if search_query and search_button:
        results = api_request("GET", "/leads/search", params={"q": search_query, "limit": 50})
        if results:
            st.success(f"Found {len(results)} leads")
            if len(results) > 0:
                df = pd.DataFrame(results)
                st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("No results found")

    st.divider()

    # Filters Section
    st.subheader("Browse Leads")
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        min_score = st.slider("Min Score", 0, 100, 0, key="browse_min_score")
    with col2:
        status_options = ["All", "new", "contacted", "negotiating", "closed", "dead"]
        status = st.selectbox("Status", status_options, key="browse_status")
    with col3:
        tcpa_only = st.checkbox("TCPA Safe Only", value=False, key="browse_tcpa")
    with col4:
        limit = st.number_input("Limit", min_value=10, max_value=500, value=100, key="browse_limit")

    # Fetch and display leads
    params: Dict[str, Any] = {
        "min_score": min_score,
        "tcpa_safe_only": tcpa_only,
        "limit": limit,
    }
    if status != "All":
        params["status"] = status

    leads_data = api_request("GET", "/leads", params=params)

    if leads_data:
        if len(leads_data) > 0:
            st.success(f"Showing {len(leads_data)} leads")
            df = pd.DataFrame(leads_data)
            
            # Reorder columns for display
            priority_cols = ["id", "owner_name", "motivation_score", "status", 
                          "is_tcpa_safe", "parcel_id", "parish", "city"]
            available_cols = [c for c in priority_cols if c in df.columns]
            other_cols = [c for c in df.columns if c not in priority_cols]
            df = df[available_cols + other_cols]
            
            st.dataframe(df, use_container_width=True, hide_index=True)
            
            # Lead detail viewer
            st.subheader("📄 Lead Details")
            lead_id = st.number_input("Enter Lead ID to view details", min_value=1, step=1, key="detail_lead_id")
            if st.button("View Details", key="view_lead_btn"):
                lead_detail = api_request("GET", f"/leads/{lead_id}")
                if lead_detail:
                    col1, col2 = st.columns(2)
                    with col1:
                        st.json(lead_detail)
                    with col2:
                        st.metric("Motivation Score", lead_detail.get("motivation_score", 0))
                        st.write(f"**Status:** {lead_detail.get('status', 'unknown')}")
                        st.write(f"**Address:** {lead_detail.get('situs_address', 'N/A')}")
                        st.write(f"**Phone:** {lead_detail.get('owner_phone', 'N/A')}")
        else:
            st.info("No leads match the current filters.")
    else:
        st.warning("Could not load leads. Is the API running?")


# =============================================================================
# Tab 3: Manual Lead Entry
# =============================================================================


def render_manual_entry_tab() -> None:
    """Render manual lead entry form."""
    st.header("✏️ Manual Lead Entry")
    
    st.info("Add a new lead manually by entering property and owner information.")

    with st.form("manual_lead_form", clear_on_submit=True):
        st.subheader("Property Information")
        col1, col2 = st.columns(2)
        
        with col1:
            address = st.text_input("Property Address *", placeholder="123 Main Street")
            city = st.text_input("City", value="Baton Rouge")
            postal_code = st.text_input("ZIP Code", placeholder="70808")
        
        with col2:
            parish = st.text_input("Parish", value="East Baton Rouge")
            state = st.text_input("State", value="LA", max_chars=2)
        
        st.subheader("Owner Information")
        col1, col2 = st.columns(2)
        
        with col1:
            owner_name = st.text_input("Owner Name *", placeholder="John Smith")
        
        with col2:
            phone = st.text_input("Phone Number", placeholder="225-555-0100")
        
        st.subheader("Additional Information")
        notes = st.text_area("Notes", placeholder="Any additional notes about this lead...")
        
        submitted = st.form_submit_button("➕ Add Lead", use_container_width=True, type="primary")
        
        if submitted:
            # Validate required fields
            if not address or not owner_name:
                st.error("❌ Address and Owner Name are required.")
            else:
                # Send to API
                payload = {
                    "owner_name": owner_name,
                    "phone": phone if phone else None,
                    "address": address,
                    "city": city,
                    "state": state,
                    "postal_code": postal_code,
                    "parish": parish,
                    "notes": notes if notes else None,
                }
                
                result = api_request("POST", "/leads/manual", json=payload)
                
                if result:
                    if result.get("success"):
                        st.success(f"✅ {result.get('message', 'Lead created!')}")
                        st.metric("Lead ID", result.get("lead_id"))
                        st.metric("Motivation Score", result.get("motivation_score", 0))
                        st.balloons()
                    else:
                        st.error(f"❌ {result.get('message', 'Failed to create lead')}")
                else:
                    st.error("❌ Failed to communicate with API")


# =============================================================================
# Tab 4: Ingestion Control
# =============================================================================


def render_ingestion_tab() -> None:
    """Render data ingestion control tab."""
    st.header("📥 Data Ingestion")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("📄 Tax Roll Import")
        tax_file = st.text_input("Tax Roll CSV Path", value="data/raw/ebr_tax_roll.csv", key="tax_path")
        if st.button("📄 Ingest Tax Roll", key="ingest_tax"):
            with st.spinner("Starting ingestion..."):
                resp = api_request("POST", "/ingest/tax-roll", params={"file_path": tax_file})
                if resp:
                    st.success(f"✅ {resp.get('message', 'Started!')}")

        st.divider()

        st.subheader("🗺️ GIS Data Import")
        gis_file = st.text_input("GIS File Path", value="data/raw/ebr_gis.geojson", key="gis_path")
        if st.button("🗺️ Ingest GIS", key="ingest_gis"):
            with st.spinner("Starting GIS ingestion..."):
                resp = api_request("POST", "/ingest/gis", params={"file_path": gis_file})
                if resp:
                    st.success(f"✅ {resp.get('message', 'Started!')}")

        st.divider()

        st.subheader("⚖️ Adjudicated Properties")
        adj_file = st.text_input("Adjudicated CSV Path", value="data/raw/ebr_adjudicated.csv", key="adj_path")
        if st.button("⚖️ Ingest Adjudicated", key="ingest_adj"):
            with st.spinner("Starting adjudicated ingestion..."):
                resp = api_request("POST", "/ingest/adjudicated", params={"file_path": adj_file})
                if resp:
                    st.success(f"✅ {resp.get('message', 'Started!')}")

    with col2:
        st.subheader("🔄 Full Pipeline")
        st.write("Run all ingestion stages with default files:")
        
        if st.button("🚀 Run Full Pipeline", type="primary", use_container_width=True, key="full_pipeline"):
            with st.spinner("Running full ingestion pipeline..."):
                resp = api_request("POST", "/ingest/full")
                if resp:
                    st.success(f"✅ {resp.get('message', 'Pipeline started!')}")

        st.divider()

        st.subheader("📊 Current Data Statistics")
        if st.button("🔄 Refresh Stats", key="refresh_ingest_stats"):
            pass  # Triggers rerun
        
        stats = api_request("GET", "/ingest/statistics")
        if stats:
            st.json(stats)
        else:
            st.info("No statistics available")

        st.divider()

        st.subheader("🎯 Score All Leads")
        if st.button("📊 Run Scoring", use_container_width=True, key="run_scoring"):
            with st.spinner("Scoring leads..."):
                resp = api_request("POST", "/leads/score-sync")
                if resp:
                    st.success(f"✅ Scored {resp.get('updated', 0)} leads")
                    st.metric("Average Score", f"{resp.get('average_score', 0):.1f}")


# =============================================================================
# Tab 5: Outreach Control
# =============================================================================


def render_outreach_tab() -> None:
    """Render outreach campaign control tab."""
    st.header("📱 Outreach Control")

    col1, col2 = st.columns([1, 2])

    with col1:
        st.subheader("🚀 Run Outreach Batch")
        
        with st.form("outreach_form"):
            batch_size = st.number_input("Batch Size", min_value=1, max_value=500, value=25)
            min_score = st.number_input("Min Motivation Score", min_value=0, max_value=100, value=65)
            
            st.caption("⚠️ Note: System respects DRY_RUN setting from environment")
            
            run_batch = st.form_submit_button("📤 Run Outreach Batch", use_container_width=True)
            
            if run_batch:
                with st.spinner("Running outreach batch..."):
                    resp = api_request(
                        "POST", 
                        "/outreach/run", 
                        params={"limit": batch_size, "min_score": min_score}
                    )
                    if resp:
                        if "message" in resp:
                            st.success(f"✅ {resp['message']}")
                        else:
                            st.success(f"✅ Sent: {resp.get('successful', 0)}/{resp.get('total_attempted', 0)}")
                            if resp.get('failed', 0) > 0:
                                st.warning(f"⚠️ {resp.get('failed', 0)} failed")

        st.divider()

        st.subheader("📊 Daily Stats")
        days = st.slider("Days to show", 1, 30, 7, key="outreach_days")
        outreach_stats = api_request("GET", "/outreach/stats", params={"days": days})
        
        if outreach_stats:
            st.metric("Total Sent", outreach_stats.get("total_sent", 0))
            st.metric("Dry Runs", outreach_stats.get("total_dry_run", 0))
            st.caption(f"Daily Limit: {outreach_stats.get('max_per_day', 0)}")

    with col2:
        st.subheader("📜 Recent Messages")
        
        lead_filter = st.number_input("Filter by Lead ID (0 for all)", min_value=0, value=0, key="outreach_lead_filter")
        
        params = {"limit": 50}
        if lead_filter > 0:
            params["lead_id"] = lead_filter
        
        history = api_request("GET", "/outreach/history", params=params)
        
        if history and len(history) > 0:
            df = pd.DataFrame(history)
            
            # Format for display
            display_cols = ["id", "lead_id", "channel", "result", "phone", "message_body", "created_at"]
            available = [c for c in display_cols if c in df.columns]
            
            st.dataframe(df[available], use_container_width=True, hide_index=True)
            
            # Show message details
            st.subheader("📝 Message Preview")
            if len(history) > 0:
                selected_idx = st.selectbox(
                    "Select message to view",
                    range(len(history)),
                    format_func=lambda i: f"ID {history[i].get('id', i)} - {history[i].get('result', 'unknown')}"
                )
                if selected_idx is not None:
                    selected = history[selected_idx]
                    st.text_area(
                        "Message Body",
                        value=selected.get("message_body", "No message"),
                        height=100,
                        disabled=True
                    )
        else:
            st.info("No outreach history yet")


# =============================================================================
# Tab 6: Configuration
# =============================================================================


def render_config_tab() -> None:
    """Render configuration and settings tab."""
    st.header("⚙️ Configuration")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("🎯 Scoring Weights")
        config = api_request("GET", "/scoring/config")
        if config:
            weights = config.get("weights", {})
            for name, value in weights.items():
                st.write(f"**{name.replace('_', ' ').title()}:** {value}")

            st.divider()

            thresholds = config.get("thresholds", {})
            st.write("**Thresholds:**")
            for name, value in thresholds.items():
                st.write(f"  • {name.replace('_', ' ').title()}: {value}")

    with col2:
        st.subheader("📊 System Metrics")
        metrics = api_request("GET", "/metrics/json")
        if metrics:
            cfg = metrics.get("config", {})
            st.write(f"**Environment:** {cfg.get('environment', 'unknown')}")
            st.write(f"**Dry Run:** {'✅ Yes' if cfg.get('dry_run', True) else '❌ No'}")
            st.write(f"**Max SMS/Day:** {cfg.get('max_sms_per_day', 0)}")
            st.write(f"**Min Score:** {cfg.get('min_motivation_score', 0)}")

            st.divider()

            st.write("**Database Counts:**")
            st.write(f"  • Leads: {metrics.get('leads', {}).get('total', 0)}")
            st.write(f"  • Owners: {metrics.get('owners', {}).get('total', 0)}")
            st.write(f"  • Parcels: {metrics.get('parcels', {}).get('total', 0)}")
            st.write(f"  • Outreach: {metrics.get('outreach', {}).get('total_attempts', 0)}")

        st.divider()

        st.subheader("🔧 API Connection")
        st.code(f"API_BASE_URL = {API_BASE_URL}")
        
        if st.button("🔄 Test Connection"):
            if check_api_health():
                st.success("✅ API is responding")
            else:
                st.error("❌ Cannot connect to API")


# =============================================================================
# Main Application
# =============================================================================


def main() -> None:
    """Main application entry point."""
    render_sidebar()

    tabs = st.tabs([
        "📊 Overview",
        "🔍 Lead Explorer", 
        "✏️ Manual Entry",
        "📥 Ingestion",
        "📱 Outreach",
        "⚙️ Config"
    ])

    with tabs[0]:
        render_overview_tab()

    with tabs[1]:
        render_lead_explorer_tab()

    with tabs[2]:
        render_manual_entry_tab()

    with tabs[3]:
        render_ingestion_tab()

    with tabs[4]:
        render_outreach_tab()

    with tabs[5]:
        render_config_tab()


if __name__ == "__main__":
    main()
