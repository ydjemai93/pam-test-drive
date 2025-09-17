"""
CSV Reports Service for PAM Analytics Export
Uses Supabase MCP to generate comprehensive call and campaign reports
"""

import csv
import io
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Header, Response
from pydantic import BaseModel

from api.db_client import supabase_service_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/reports", tags=["csv_reports"])

class ReportGenerationRequest(BaseModel):
    report_type: str  # "calls", "campaigns", "agents", "comprehensive"
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    time_filter: str = "30d"  # "7d", "30d", "90d", "1y", "all"
    campaign_id: Optional[str] = None
    agent_id: Optional[int] = None
    format: str = "csv"  # "csv", "excel" (future)

def escape_csv_field(field: Any) -> str:
    """Escape CSV field to handle commas, quotes, and newlines"""
    if field is None:
        return ""
    
    field_str = str(field)
    
    # If field contains comma, quote, or newline, wrap in quotes and escape quotes
    if ',' in field_str or '"' in field_str or '\n' in field_str or '\r' in field_str:
        # Escape quotes by doubling them
        field_str = field_str.replace('"', '""')
        return f'"{field_str}"'
    
    return field_str

def format_duration(seconds: Optional[int]) -> str:
    """Format duration in seconds to human readable format"""
    if seconds is None or seconds == 0:
        return "0:00"
    
    minutes = seconds // 60
    remaining_seconds = seconds % 60
    return f"{minutes}:{remaining_seconds:02d}"

def get_geographic_region(phone_number: str) -> str:
    """Get geographic region from phone number"""
    if not phone_number or not phone_number.startswith('+'):
        return "Unknown"
    
    if phone_number.startswith('+1'):
        return "US/Canada"
    elif phone_number.startswith('+33'):
        return "France"
    elif phone_number.startswith('+44'):
        return "United Kingdom"
    elif phone_number.startswith('+49'):
        return "Germany"
    elif phone_number.startswith('+34'):
        return "Spain"
    elif phone_number.startswith('+39'):
        return "Italy"
    elif phone_number.startswith('+61'):
        return "Australia"
    elif phone_number.startswith('+81'):
        return "Japan"
    elif phone_number.startswith('+86'):
        return "China"
    elif phone_number.startswith('+91'):
        return "India"
    else:
        return "International"

def get_call_outcome(status: str, duration: Optional[int]) -> str:
    """Determine call outcome based on status and duration"""
    if not status:
        return "Unknown"
    
    status_lower = status.lower()
    duration = duration or 0
    
    if status_lower in ["completed", "ended"]:
        if duration > 30:
            return "Connected (Human)"
        elif duration > 5:
            return "Connected (Voicemail)"
        else:
            return "No Answer"
    elif status_lower == "busy":
        return "Busy"
    elif status_lower in ["no_answer", "timeout"]:
        return "No Answer"
    elif status_lower == "calling":
        return "In Progress"
    elif status_lower == "failed":
        return "Failed"
    else:
        return "Other"

def get_date_range_filter(time_filter: str, start_date: Optional[str], end_date: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """Get date range based on filter"""
    now = datetime.now(timezone.utc)
    
    if start_date and end_date:
        return start_date, end_date
    
    if time_filter == "7d":
        start = (now - timedelta(days=7)).isoformat()
        end = now.isoformat()
    elif time_filter == "30d":
        start = (now - timedelta(days=30)).isoformat()
        end = now.isoformat()
    elif time_filter == "90d":
        start = (now - timedelta(days=90)).isoformat()
        end = now.isoformat()
    elif time_filter == "1y":
        start = (now - timedelta(days=365)).isoformat()
        end = now.isoformat()
    else:  # "all"
        start = None
        end = None
    
    return start, end

async def generate_calls_report(user_id: str, request: ReportGenerationRequest) -> str:
    """Generate detailed calls report using Supabase MCP"""
    start_date, end_date = get_date_range_filter(request.time_filter, request.start_date, request.end_date)
    
    try:
        # Build query conditions
        query_conditions = [f"user_id.eq.{user_id}"]
        
        if start_date:
            query_conditions.append(f"created_at.gte.{start_date}")
        if end_date:
            query_conditions.append(f"created_at.lte.{end_date}")
        if request.campaign_id and request.campaign_id != "all":
            query_conditions.append(f"batch_campaign_id.eq.{request.campaign_id}")
        if request.agent_id and request.agent_id != "all":
            query_conditions.append(f"agent_id.eq.{request.agent_id}")
        
        # Use Supabase client to get calls data
        result = supabase_service_client.table("calls").select("""
            id, status, call_duration, phone_number_e164, contact_name, created_at, 
            initiated_at, answered_at, ended_at, call_direction, call_type, ended_reason,
            from_phone_number, to_phone_number, call_control_id, telnyx_call_session_id,
            agent_id, batch_campaign_id, batch_call_item_id,
            agents(name),
            batch_campaigns(name, id),
            batch_call_items(contact_name, custom_data)
        """).eq("user_id", user_id)
        
        if start_date:
            result = result.gte("created_at", start_date)
        if end_date:
            result = result.lte("created_at", end_date)
        if request.campaign_id and request.campaign_id != "all":
            result = result.eq("batch_campaign_id", request.campaign_id)
        if request.agent_id and request.agent_id != "all":
            result = result.eq("agent_id", request.agent_id)
            
        result = result.order("created_at", desc=True).limit(10000)
        response = result.execute()
        calls_data = response.data or []
        
    except Exception as e:
        logger.error(f"Error fetching calls data: {e}")
        calls_data = []
    
    # Generate CSV
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write headers
    headers = [
        "Call ID", "Status", "Call Outcome", "Duration (MM:SS)", "Duration (Seconds)",
        "Phone Number", "Contact Name", "Geographic Region", "Agent Name", "Agent ID",
        "Campaign Name", "Campaign ID", "Call Type", "From Number",
        "To Number", "Created At", "Initiated At", "Answered At", "Ended At",
        "Date", "Time", "Day of Week", "Hour of Day", "Ended Reason"
    ]
    writer.writerow(headers)
    
    # Write data rows
    for call in calls_data:
        # Extract nested data safely
        agent_name = ""
        if call.get("agents"):
            agent_name = call["agents"].get("name", "")
        
        campaign_name = ""
        campaign_id = call.get("batch_campaign_id", "")
        if call.get("batch_campaigns"):
            campaign_name = call["batch_campaigns"].get("name", "")
        
        # Format timestamps
        created_at = call.get("created_at", "")
        if created_at:
            try:
                created_dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                date_str = created_dt.strftime("%Y-%m-%d")
                time_str = created_dt.strftime("%H:%M:%S")
                day_of_week = created_dt.strftime("%A")
                hour_of_day = created_dt.strftime("%H:00")
            except:
                date_str = time_str = day_of_week = hour_of_day = ""
        else:
            date_str = time_str = day_of_week = hour_of_day = ""
        
        duration = call.get("call_duration")
        phone_number = call.get("phone_number_e164", "") or call.get("to_phone_number", "")
        
        row = [
            escape_csv_field(call.get("id", "")),
            escape_csv_field(call.get("status", "")),
            escape_csv_field(get_call_outcome(call.get("status", ""), duration)),
            escape_csv_field(format_duration(duration)),
            escape_csv_field(duration or 0),
            escape_csv_field(phone_number),
            escape_csv_field(call.get("contact_name", "")),
            escape_csv_field(get_geographic_region(phone_number)),
            escape_csv_field(agent_name),
            escape_csv_field(call.get("agent_id", "")),
            escape_csv_field(campaign_name),
            escape_csv_field(campaign_id),
            escape_csv_field(call.get("call_type", "")),
            escape_csv_field(call.get("from_phone_number", "")),
            escape_csv_field(call.get("to_phone_number", "")),
            escape_csv_field(created_at),
            escape_csv_field(call.get("initiated_at", "")),
            escape_csv_field(call.get("answered_at", "")),
            escape_csv_field(call.get("ended_at", "")),
            escape_csv_field(date_str),
            escape_csv_field(time_str),
            escape_csv_field(day_of_week),
            escape_csv_field(hour_of_day),
            escape_csv_field(call.get("ended_reason", ""))
        ]
        writer.writerow(row)
    
    return output.getvalue()

async def generate_campaigns_report(user_id: str, request: ReportGenerationRequest) -> str:
    """Generate campaigns performance report"""
    start_date, end_date = get_date_range_filter(request.time_filter, request.start_date, request.end_date)
    
    try:
        # Get campaigns data
        query = supabase_service_client.postgrest.from_("batch_campaigns").select("""
            id, name, description, status, total_numbers, completed_calls, successful_calls, 
            failed_calls, concurrency_limit, retry_failed, max_retries, scheduled_at, 
            started_at, completed_at, created_at, updated_at,
            agents(name, id),
            users(name, email)
        """).eq("user_id", user_id)
        
        if start_date:
            query = query.gte("created_at", start_date)
        if end_date:
            query = query.lte("created_at", end_date)
        if request.campaign_id and request.campaign_id != "all":
            query = query.eq("id", request.campaign_id)
        
        query = query.order("created_at", desc=True)
        response = query.execute()
        campaigns_data = response.data or []
        
    except Exception as e:
        logger.error(f"Error fetching campaigns data: {e}")
        campaigns_data = []
    
    # Generate CSV
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write headers
    headers = [
        "Campaign ID", "Campaign Name", "Description", "Status", "Agent Name", "Agent ID",
        "Total Numbers", "Completed Calls", "Successful Calls", "Failed Calls",
        "Success Rate (%)", "Completion Rate (%)", "Concurrency Limit", "Retry Failed",
        "Max Retries", "Created At", "Scheduled At", "Started At", "Completed At",
        "Duration (Hours)", "Calls per Hour", "User Name", "User Email"
    ]
    writer.writerow(headers)
    
    # Write data rows
    for campaign in campaigns_data:
        # Extract nested data
        agent_name = ""
        agent_id = ""
        if isinstance(campaign.get("agents"), dict):
            agent_name = campaign["agents"].get("name", "")
            agent_id = campaign["agents"].get("id", "")
        
        user_name = ""
        user_email = ""
        if isinstance(campaign.get("users"), dict):
            user_name = campaign["users"].get("name", "")
            user_email = campaign["users"].get("email", "")
        
        # Calculate metrics
        total_numbers = campaign.get("total_numbers", 0) or 0
        completed_calls = campaign.get("completed_calls", 0) or 0
        successful_calls = campaign.get("successful_calls", 0) or 0
        failed_calls = campaign.get("failed_calls", 0) or 0
        
        success_rate = (successful_calls / total_numbers * 100) if total_numbers > 0 else 0
        completion_rate = (completed_calls / total_numbers * 100) if total_numbers > 0 else 0
        
        # Calculate duration and calls per hour
        started_at = campaign.get("started_at")
        completed_at = campaign.get("completed_at")
        duration_hours = 0
        calls_per_hour = 0
        
        if started_at and completed_at:
            try:
                start_dt = datetime.fromisoformat(started_at.replace('Z', '+00:00'))
                end_dt = datetime.fromisoformat(completed_at.replace('Z', '+00:00'))
                duration = end_dt - start_dt
                duration_hours = duration.total_seconds() / 3600
                if duration_hours > 0:
                    calls_per_hour = completed_calls / duration_hours
            except:
                pass
        
        row = [
            escape_csv_field(campaign.get("id", "")),
            escape_csv_field(campaign.get("name", "")),
            escape_csv_field(campaign.get("description", "")),
            escape_csv_field(campaign.get("status", "")),
            escape_csv_field(agent_name),
            escape_csv_field(agent_id),
            escape_csv_field(total_numbers),
            escape_csv_field(completed_calls),
            escape_csv_field(successful_calls),
            escape_csv_field(failed_calls),
            escape_csv_field(round(success_rate, 2)),
            escape_csv_field(round(completion_rate, 2)),
            escape_csv_field(campaign.get("concurrency_limit", "")),
            escape_csv_field(campaign.get("retry_failed", "")),
            escape_csv_field(campaign.get("max_retries", "")),
            escape_csv_field(campaign.get("created_at", "")),
            escape_csv_field(campaign.get("scheduled_at", "")),
            escape_csv_field(campaign.get("started_at", "")),
            escape_csv_field(campaign.get("completed_at", "")),
            escape_csv_field(round(duration_hours, 2)),
            escape_csv_field(round(calls_per_hour, 2)),
            escape_csv_field(user_name),
            escape_csv_field(user_email)
        ]
        writer.writerow(row)
    
    return output.getvalue()

async def generate_comprehensive_report(user_id: str, request: ReportGenerationRequest) -> str:
    """Generate comprehensive report with all data"""
    start_date, end_date = get_date_range_filter(request.time_filter, request.start_date, request.end_date)
    
    # Generate all individual reports
    calls_csv = await generate_calls_report(user_id, request)
    campaigns_csv = await generate_campaigns_report(user_id, request)
    
    # Combine into a comprehensive report with sections
    output = io.StringIO()
    
    # Add report header
    output.write("PAM Analytics Comprehensive Report\n")
    output.write(f"Generated on: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}\n")
    output.write(f"Time Filter: {request.time_filter}\n")
    if request.start_date:
        output.write(f"Start Date: {request.start_date}\n")
    if request.end_date:
        output.write(f"End Date: {request.end_date}\n")
    if request.campaign_id and request.campaign_id != "all":
        output.write(f"Campaign ID: {request.campaign_id}\n")
    if request.agent_id and request.agent_id != "all":
        output.write(f"Agent ID: {request.agent_id}\n")
    output.write("\n")
    
    # Add calls section
    output.write("=== CALLS REPORT ===\n")
    output.write(calls_csv)
    output.write("\n\n")
    
    # Add campaigns section
    output.write("=== CAMPAIGNS REPORT ===\n")
    output.write(campaigns_csv)
    output.write("\n")
    
    return output.getvalue()

@router.post("/generate")
async def generate_report(
    request: ReportGenerationRequest,
    authorization: str = Header(None, alias="Authorization")
):
    """Generate and download CSV report"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    
    token = authorization.replace("Bearer ", "")
    
    try:
        # Verify token
        user_response = supabase_service_client.auth.get_user(token)
        if not user_response.user:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        user_id = user_response.user.id
        
        # Generate the appropriate report
        if request.report_type == "calls":
            csv_content = await generate_calls_report(user_id, request)
            filename = f"pam_calls_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        elif request.report_type == "campaigns":
            csv_content = await generate_campaigns_report(user_id, request)
            filename = f"pam_campaigns_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        elif request.report_type == "comprehensive":
            csv_content = await generate_comprehensive_report(user_id, request)
            filename = f"pam_comprehensive_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        else:
            raise HTTPException(status_code=400, detail="Invalid report type")
        
        # Return CSV as downloadable response
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating report: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate report")

@router.get("/types")
async def get_report_types():
    """Get available report types"""
    return {
        "report_types": [
            {
                "id": "calls",
                "name": "Calls Report",
                "description": "Detailed call logs with performance metrics"
            },
            {
                "id": "campaigns",
                "name": "Campaigns Report", 
                "description": "Batch campaign performance and statistics"
            },
            {
                "id": "comprehensive",
                "name": "Comprehensive Report",
                "description": "All reports combined with summary statistics"
            }
        ],
        "time_filters": [
            {"id": "7d", "name": "Last 7 days"},
            {"id": "30d", "name": "Last 30 days"},
            {"id": "90d", "name": "Last 90 days"},
            {"id": "1y", "name": "Last year"},
            {"id": "all", "name": "All time"}
        ],
        "formats": [
            {"id": "csv", "name": "CSV", "description": "Comma-separated values"}
        ]
    } 