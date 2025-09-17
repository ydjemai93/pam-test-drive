"""
B2B Sales Multi-Agent Implementation - LiveKit Native Pattern
This shows how to convert your B2B Sales pathway to separate Agent classes
following LiveKit's recommended multi-agent workflow pattern.
"""

import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass

from livekit.agents import (
    Agent, 
    AgentSession, 
    function_tool,
    RunContext
)
from livekit.agents.llm import ChatContext

logger = logging.getLogger("b2b-sales-agents")

# ===== SHARED DATA STRUCTURES =====

@dataclass
class SalesContext:
    """Shared context passed between all sales agents"""
    customer_name: str = "Valued Customer"
    phone_number: str = ""
    email: str = ""
    interest_level: str = ""
    qualification_notes: str = ""
    availability: str = ""
    callback_time: str = ""
    appointment_time: str = ""
    decline_reason: str = ""
    conversation_history: str = ""

# ===== AGENT 1: GREETING AGENT =====

class GreetingAgent(Agent):
    """
    Handles initial greeting and determines conversation direction.
    Equivalent to your 'Greeting' conversation node.
    """
    
    def __init__(self, chat_ctx: Optional[ChatContext] = None, sales_context: Optional[SalesContext] = None):
        super().__init__()
        self.sales_context = sales_context or SalesContext()
        self._chat_ctx = chat_ctx
        
    async def on_enter(self, ctx: AgentSession):
        """LiveKit lifecycle hook - executes when agent becomes active"""
        logger.info("🎯 GreetingAgent entering - starting B2B sales conversation")
        
        # Your pathway's greeting message
        await ctx.say("Hi this is Pam from Dunder Mifflin")
        
        # Update instructions for this phase
        self.update_instructions("""
        You are Pam from Dunder Mifflin. You are making an outbound sales call to someone 
        who previously inquired about your services. Your goal is to determine if this is a 
        good time to talk. Be friendly and professional. Start by introducing yourself and 
        your company, mention that you are following up on their inquiry, then ask if they 
        have a few minutes to talk. Listen carefully to their response to gauge their 
        availability and interest level. Extract any information about their current 
        situation or needs they mention.
        """)

    @function_tool
    async def person_available_and_interested(self, ctx: RunContext) -> "QualifyLeadAgent":
        """
        Condition: Person is available to talk now and shows interest in the conversation
        → Transitions to Qualify Lead phase
        """
        logger.info("✅ Person available and interested → Transitioning to QualifyLeadAgent")
        
        self.sales_context.interest_level = "high"
        self.sales_context.availability = "available_now"
        
        return QualifyLeadAgent(
            chat_ctx=ctx.session.chat_ctx,
            sales_context=self.sales_context
        )

    @function_tool  
    async def person_busy_wants_callback(self, ctx: RunContext, preferred_time: str = "") -> "ScheduleCallbackAgent":
        """
        Condition: Person is busy or wants to be called back later
        → Transitions to Schedule Callback phase
        """
        logger.info(f"📞 Person wants callback for {preferred_time} → Transitioning to ScheduleCallbackAgent")
        
        self.sales_context.availability = "busy"
        self.sales_context.callback_time = preferred_time
        
        return ScheduleCallbackAgent(
            chat_ctx=ctx.session.chat_ctx,
            sales_context=self.sales_context
        )

    @function_tool
    async def person_uninterested_or_hostile(self, ctx: RunContext, reason: str = "") -> "PoliteDeclineAgent":
        """
        Condition: Person seems uninterested, hostile, or wants to end the call
        → Transitions to Polite Decline phase
        """
        logger.info(f"❌ Person uninterested/hostile: {reason} → Transitioning to PoliteDeclineAgent")
        
        self.sales_context.interest_level = "low"
        self.sales_context.decline_reason = reason
        
        return PoliteDeclineAgent(
            chat_ctx=ctx.session.chat_ctx,
            sales_context=self.sales_context
        )

# ===== AGENT 2: QUALIFY LEAD AGENT =====

class QualifyLeadAgent(Agent):
    """
    Qualifies the lead and determines next steps.
    Equivalent to your 'Qualify Lead' conversation node.
    """
    
    def __init__(self, chat_ctx: Optional[ChatContext] = None, sales_context: Optional[SalesContext] = None):
        super().__init__()
        self.sales_context = sales_context or SalesContext()
        self._chat_ctx = chat_ctx
        
    async def on_enter(self, ctx: AgentSession):
        logger.info("🎯 QualifyLeadAgent entering - qualifying the lead")
        
        self.update_instructions("""
        The person is willing to talk. Now you need to qualify them as a potential customer. 
        Ask about their current situation, what specific services they're looking for, their 
        timeline, and any challenges they're facing. Be conversational but focused on gathering 
        key qualifying information: budget range, decision-making authority, urgency of need, 
        and fit for your services. Listen for buying signals and pain points. Ask open-ended 
        questions to understand their needs deeply.
        """)

    @function_tool
    async def qualified_lead_ready_to_book(self, ctx: RunContext) -> "BookAppointmentAgent":
        """
        Condition: Person is a qualified lead with genuine interest and potential budget
        → Transitions to Book Appointment phase
        """
        logger.info("✅ Qualified lead identified → Transitioning to BookAppointmentAgent")
        
        self.sales_context.interest_level = "qualified"
        
        return BookAppointmentAgent(
            chat_ctx=ctx.session.chat_ctx,
            sales_context=self.sales_context
        )

    @function_tool
    async def interested_but_wants_information(self, ctx: RunContext) -> "SendInformationAgent":
        """
        Condition: Person expressed interest but wants more information before scheduling
        → Transitions to Send Information phase
        """
        logger.info("📧 Person wants information first → Transitioning to SendInformationAgent")
        
        self.sales_context.interest_level = "interested_needs_info"
        
        return SendInformationAgent(
            chat_ctx=ctx.session.chat_ctx,
            sales_context=self.sales_context
        )

    @function_tool
    async def poor_fit_no_budget(self, ctx: RunContext, reason: str = "") -> "PoliteDeclineAgent":
        """
        Condition: Person seems like a poor fit with no budget, authority, need, or timing
        → Transitions to Polite Decline phase
        """
        logger.info(f"❌ Poor fit identified: {reason} → Transitioning to PoliteDeclineAgent")
        
        self.sales_context.interest_level = "poor_fit"
        self.sales_context.decline_reason = reason
        
        return PoliteDeclineAgent(
            chat_ctx=ctx.session.chat_ctx,
            sales_context=self.sales_context
        )

# ===== AGENT 3: SCHEDULE CALLBACK AGENT =====

class ScheduleCallbackAgent(Agent):
    """
    Handles callback scheduling when person is busy.
    Equivalent to your 'Schedule Callback' conversation node.
    """
    
    def __init__(self, chat_ctx: Optional[ChatContext] = None, sales_context: Optional[SalesContext] = None):
        super().__init__()
        self.sales_context = sales_context or SalesContext()
        self._chat_ctx = chat_ctx
        
    async def on_enter(self, ctx: AgentSession):
        logger.info("🎯 ScheduleCallbackAgent entering - scheduling callback")
        
        self.update_instructions("""
        The person indicated they're busy or want to be called back later. Be understanding 
        and accommodating. Ask for their preferred time for a callback - offer specific options 
        like 'tomorrow afternoon' or 'later this week'. Try to get a specific day and time range. 
        Also ask if there's any particular information they'd like you to have ready for the 
        callback. Be flexible and work around their schedule.
        """)

    @function_tool
    async def callback_time_provided(self, ctx: RunContext, callback_time: str) -> str:
        """
        Condition: Person provided a specific time for callback
        → Executes callback scheduling tool and ends call
        """
        logger.info(f"📅 Callback scheduled for: {callback_time}")
        
        self.sales_context.callback_time = callback_time
        
        # In your pathway, this triggers a 'tools' node for scheduling
        # Here we'd integrate with your scheduling system
        await self._schedule_callback_tool(ctx, callback_time)
        
        # End the call with success message
        await ctx.session.say(f"Perfect! I'll call you back at {callback_time}. Have a great day!")
        
        return "callback_scheduled_successfully"

    @function_tool
    async def person_declining_callback(self, ctx: RunContext) -> str:
        """
        Condition: Person is politely trying to end call without genuine callback interest
        → Ends call politely
        """
        logger.info("❌ Person declining callback → Ending call politely")
        
        await ctx.session.say("Thank you for your time. Have a great day!")
        return "call_ended_politely"

    async def _schedule_callback_tool(self, ctx: RunContext, callback_time: str):
        """Helper method to execute callback scheduling tool"""
        # This would integrate with your scheduling system
        logger.info(f"🛠️ Executing callback scheduling tool for {callback_time}")

# ===== AGENT 4: BOOK APPOINTMENT AGENT =====

class BookAppointmentAgent(Agent):
    """
    Handles appointment booking for qualified leads.
    Equivalent to your 'Book Appointment' conversation node.
    """
    
    def __init__(self, chat_ctx: Optional[ChatContext] = None, sales_context: Optional[SalesContext] = None):
        super().__init__()
        self.sales_context = sales_context or SalesContext()
        self._chat_ctx = chat_ctx
        
    async def on_enter(self, ctx: AgentSession):
        logger.info("🎯 BookAppointmentAgent entering - booking appointment")
        
        self.update_instructions("""
        This is a qualified lead who has shown interest. Your goal is to schedule a consultation 
        or appointment. Mention the value they'll get from the meeting and how it will help solve 
        their specific needs you've identified. Offer specific time slots and be flexible with 
        scheduling. Try to get their availability, preferred meeting type (phone, video, in-person), 
        and contact details for scheduling. If they hesitate, address their concerns and offer to 
        send more information first.
        """)

    @function_tool
    async def appointment_agreed_time_provided(self, ctx: RunContext, appointment_time: str, contact_email: str = "") -> "ConfirmAppointmentAgent":
        """
        Condition: Person agreed to schedule and provided availability/preferred time
        → Creates calendar event and transitions to confirmation
        """
        logger.info(f"📅 Appointment agreed for: {appointment_time}")
        
        self.sales_context.appointment_time = appointment_time
        self.sales_context.email = contact_email
        
        # Execute calendar creation (your app_action node)
        success = await self._create_calendar_event(ctx, appointment_time, contact_email)
        
        if success:
            return ConfirmAppointmentAgent(
                chat_ctx=ctx.session.chat_ctx,
                sales_context=self.sales_context
            )
        else:
            # If calendar creation fails, send information instead
            return SendInformationAgent(
                chat_ctx=ctx.session.chat_ctx,
                sales_context=self.sales_context
            )

    @function_tool
    async def wants_information_first(self, ctx: RunContext) -> "SendInformationAgent":
        """
        Condition: Person wants to schedule but asked for information first
        → Transitions to Send Information phase
        """
        logger.info("📧 Person wants information before booking → Transitioning to SendInformationAgent")
        
        return SendInformationAgent(
            chat_ctx=ctx.session.chat_ctx,
            sales_context=self.sales_context
        )

    @function_tool
    async def declined_to_schedule(self, ctx: RunContext, reason: str = "") -> "PoliteDeclineAgent":
        """
        Condition: Person declined to schedule or seems hesitant
        → Transitions to Polite Decline phase
        """
        logger.info(f"❌ Appointment declined: {reason} → Transitioning to PoliteDeclineAgent")
        
        self.sales_context.decline_reason = reason
        
        return PoliteDeclineAgent(
            chat_ctx=ctx.session.chat_ctx,
            sales_context=self.sales_context
        )

    async def _create_calendar_event(self, ctx: RunContext, appointment_time: str, contact_email: str) -> bool:
        """Helper method to create calendar event (your app_action logic)"""
        try:
            logger.info(f"🗓️ Creating calendar event for {appointment_time}")
            # This would integrate with your Google Calendar app action
            # Return True if successful, False if failed
            return True
        except Exception as e:
            logger.error(f"Calendar creation failed: {e}")
            return False

# ===== AGENT 5: SEND INFORMATION AGENT =====

class SendInformationAgent(Agent):
    """
    Handles information sending and email capture.
    Equivalent to your 'Send Information' conversation node.
    """
    
    def __init__(self, chat_ctx: Optional[ChatContext] = None, sales_context: Optional[SalesContext] = None):
        super().__init__()
        self.sales_context = sales_context or SalesContext()
        self._chat_ctx = chat_ctx
        
    async def on_enter(self, ctx: AgentSession):
        logger.info("🎯 SendInformationAgent entering - collecting email for information")
        
        self.update_instructions("""
        The person wants more information before scheduling. Ask for their email address to send 
        details about your services, pricing, case studies, or whatever information would be most 
        relevant to their specific needs. Be specific about what you'll send and when they can 
        expect it. Also ask if they have any specific questions you can address in the information 
        packet. Make them feel comfortable that this isn't high-pressure follow-up.
        """)

    @function_tool
    async def email_provided(self, ctx: RunContext, email_address: str) -> str:
        """
        Condition: Person provided their email for information
        → Executes email capture tool and ends call
        """
        logger.info(f"📧 Email captured: {email_address}")
        
        self.sales_context.email = email_address
        
        # Execute email capture tool (your 'tools' node)
        await self._capture_email_tool(ctx, email_address)
        
        # End call with success message
        await ctx.session.say("Great! I'll send that information right over. Feel free to call us with any questions. Have a wonderful day!")
        
        return "information_sent_successfully"

    @function_tool
    async def declined_to_provide_email(self, ctx: RunContext) -> str:
        """
        Condition: Person declined to provide email or seems uninterested
        → Ends call politely
        """
        logger.info("❌ Email declined → Ending call")
        
        await ctx.session.say("Thank you for your time. Have a great day!")
        return "call_ended_no_email"

    async def _capture_email_tool(self, ctx: RunContext, email: str):
        """Helper method to execute email capture tool"""
        logger.info(f"🛠️ Executing email capture tool for {email}")
        # This would integrate with your CRM/email system

# ===== AGENT 6: CONFIRM APPOINTMENT AGENT =====

class ConfirmAppointmentAgent(Agent):
    """
    Confirms successful appointment booking.
    Equivalent to your 'Confirm Appointment' conversation node.
    """
    
    def __init__(self, chat_ctx: Optional[ChatContext] = None, sales_context: Optional[SalesContext] = None):
        super().__init__()
        self.sales_context = sales_context or SalesContext()
        self._chat_ctx = chat_ctx
        
    async def on_enter(self, ctx: AgentSession):
        logger.info("🎯 ConfirmAppointmentAgent entering - confirming appointment")
        
        self.update_instructions("""
        The calendar event has been successfully created. Confirm the appointment details with 
        enthusiasm. Mention the date, time, and format of the meeting. Let them know they'll 
        receive a calendar invite shortly. Ask if they have any specific topics they'd like to 
        discuss or questions they want addressed during the consultation. Set clear expectations 
        for what the meeting will cover and how long it will take.
        """)

    @function_tool
    async def appointment_confirmed(self, ctx: RunContext) -> str:
        """
        Condition: Appointment confirmed and conversation wrapped up
        → Ends call with success
        """
        logger.info("✅ Appointment confirmed → Ending call successfully")
        
        appointment_time = self.sales_context.appointment_time
        await ctx.session.say(f"Thank you! Looking forward to speaking with you on {appointment_time}. Have a great day!")
        
        return "call_ended_successfully"

# ===== AGENT 7: POLITE DECLINE AGENT =====

class PoliteDeclineAgent(Agent):
    """
    Handles polite decline scenarios.
    Equivalent to your 'Polite Decline' conversation node.
    """
    
    def __init__(self, chat_ctx: Optional[ChatContext] = None, sales_context: Optional[SalesContext] = None):
        super().__init__()
        self.sales_context = sales_context or SalesContext()
        self._chat_ctx = chat_ctx
        
    async def on_enter(self, ctx: AgentSession):
        logger.info("🎯 PoliteDeclineAgent entering - declining politely")
        
        self.update_instructions("""
        This person doesn't seem like a good fit right now. Be polite and professional. Thank 
        them for their time, acknowledge that the timing might not be right, and offer to send 
        them information for future reference. Ask if they'd like to receive updates or if there's 
        a better time to reach out in the future. End on a positive note and leave the door open 
        for future contact.
        """)
        
        # Automatically end call politely
        await ctx.session.say("Thank you for your time. Have a great day!")

# ===== USAGE EXAMPLE =====

def create_b2b_sales_agent_session(customer_name: str = "Valued Customer") -> GreetingAgent:
    """
    Entry point for B2B Sales workflow - starts with GreetingAgent
    This replaces your single WorkflowAgent
    """
    sales_context = SalesContext(customer_name=customer_name)
    
    # Always start with GreetingAgent (your pathway's entry_point)
    return GreetingAgent(sales_context=sales_context) 