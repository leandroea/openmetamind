"""
Slack bot for OpenMetaMind.

Provides Slack integration for interacting with the swarm via @mention.
"""

import os
import asyncio
import logging
from typing import Dict, Any, Optional

import httpx
from slack_bolt import AsyncApp
from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_sdk.web.async_client import AsyncWebClient

logger = logging.getLogger(__name__)

# API Configuration
API_BASE_URL = "http://localhost:8000"


class OpenMetaMindSlackBot:
    """
    Slack bot for OpenMetaMind swarm interaction.
    
    Handles:
    - App mention events (@openmetamind)
    - Thread replies for follow-up questions
    - Real-time status polling
    - Block Kit approval messages
    """

    def __init__(self):
        """Initialize the Slack bot."""
        self.app = AsyncApp(
            token=os.getenv("SLACK_BOT_TOKEN"),
            signing_secret=os.getenv("SLACK_SIGNING_SECRET")
        )
        self.http_client = httpx.AsyncClient(timeout=30.0)
        self.polling_tasks: Dict[str, asyncio.Task] = {}
        
        # Register event handlers
        self._register_handlers()
    
    def _register_handlers(self):
        """Register all Slack event handlers."""
        
        @self.app.event("app_mention")
        async def handle_app_mention(event, say, client: AsyncWebClient):
            """Handle app mention events."""
            try:
                # Extract text after the mention
                text = event.get("text", "")
                # Remove the mention part (e.g., "<@U123> ")
                mention_removed = text.split(">", 1)[-1].strip() if ">" in text else text
                
                if not mention_removed:
                    await say("Hello! How can I help you with OpenMetadata governance? Just ask me a question and I'll deploy the swarm to investigate.")
                    return
                
                # Get the channel and thread info
                channel_id = event.get("channel")
                thread_ts = event.get("thread_ts") or event.get("ts")
                
                # Post initial message
                initial_response = await say(
                    text="🧠 Deploying swarm to investigate...",
                    channel=channel_id,
                    thread_ts=thread_ts
                )
                
                # Run the swarm
                result = await self._run_swarm(mention_removed, event.get("user", "unknown"))
                
                if result:
                    session_id = result.get("session_id")
                    
                    # Post coordinator response
                    coordinator_response = result.get("coordinator_response", "Swarm analysis complete.")
                    await say(
                        text=f"📊 {coordinator_response}",
                        channel=channel_id,
                        thread_ts=thread_ts
                    )
                    
                    # Start polling for updates
                    self._start_polling(session_id, channel_id, thread_ts, client)
                    
                    # Handle pending approvals
                    pending_approvals = result.get("approved_actions", [])
                    if pending_approvals:
                        await self._post_approval_message(
                            session_id, channel_id, thread_ts, pending_approvals, client
                        )
                else:
                    await say(
                        text="❌ Sorry, I couldn't process your request. Please ensure the backend is running.",
                        channel=channel_id,
                        thread_ts=thread_ts
                    )
                    
            except Exception as e:
                logger.error(f"Error handling app mention: {e}", exc_info=True)
                await say(f"❌ An error occurred: {str(e)}")
        
        @self.app.event("message")
        async def handle_message(event, say, client: AsyncWebClient):
            """Handle messages in threads (follow-up questions)."""
            try:
                # Only handle messages in threads (not top-level)
                if "thread_ts" not in event:
                    return
                
                # Ignore bot messages
                if event.get("subtype") == "bot_message":
                    return
                
                text = event.get("text", "").strip()
                if not text:
                    return
                
                channel_id = event.get("channel")
                thread_ts = event.get("thread_ts")
                user = event.get("user", "unknown")
                
                # Post thinking message
                thinking_msg = await say(
                    text="🧠 Processing your follow-up...",
                    channel=channel_id,
                    thread_ts=thread_ts
                )
                
                # Run the swarm with the follow-up question
                result = await self._run_swarm(text, user)
                
                if result:
                    session_id = result.get("session_id")
                    
                    # Post coordinator response
                    coordinator_response = result.get("coordinator_response", "Analysis complete.")
                    await say(
                        text=f"📊 {coordinator_response}",
                        channel=channel_id,
                        thread_ts=thread_ts
                    )
                    
                    # Start polling for updates
                    self._start_polling(session_id, channel_id, thread_ts, client)
                    
                    # Handle pending approvals
                    pending_approvals = result.get("approved_actions", [])
                    if pending_approvals:
                        await self._post_approval_message(
                            session_id, channel_id, thread_ts, pending_approvals, client
                        )
                else:
                    await say(
                        text="❌ Sorry, I couldn't process your request.",
                        channel=channel_id,
                        thread_ts=thread_ts
                    )
                    
            except Exception as e:
                logger.error(f"Error handling message: {e}", exc_info=True)
        
        @self.app.action("approve_all")
        async def handle_approve_all(ack, body, client: AsyncWebClient):
            """Handle approve all button action."""
            await ack()
            
            try:
                # Extract session_id from action
                session_id = body.get("actions", [{}])[0].get("value", "").split(":")[1]
                
                # Call the approval API
                success = await self._approve_actions(session_id, [], "approve")
                
                if success:
                    await client.chat_postMessage(
                        text="✅ All actions have been approved and will be executed.",
                        channel=body["channel"]["id"],
                        thread_ts=body["message"]["ts"]
                    )
                else:
                    await client.chat_postMessage(
                        text="❌ Failed to approve actions. Please try again.",
                        channel=body["channel"]["id"],
                        thread_ts=body["message"]["ts"]
                    )
                    
            except Exception as e:
                logger.error(f"Error handling approve_all: {e}", exc_info=True)
                await client.chat_postMessage(
                    text=f"❌ An error occurred: {str(e)}",
                    channel=body["channel"]["id"],
                    thread_ts=body["message"]["ts"]
                )
        
        @self.app.action("reject_all")
        async def handle_reject_all(ack, body, client: AsyncWebClient):
            """Handle reject all button action."""
            await ack()
            
            try:
                # Extract session_id from action
                session_id = body.get("actions", [{}])[0].get("value", "").split(":")[1]
                
                # Call the approval API
                success = await self._approve_actions(session_id, [], "reject")
                
                if success:
                    await client.chat_postMessage(
                        text="❌ All actions have been rejected.",
                        channel=body["channel"]["id"],
                        thread_ts=body["message"]["ts"]
                    )
                else:
                    await client.chat_postMessage(
                        text="❌ Failed to reject actions. Please try again.",
                        channel=body["channel"]["id"],
                        thread_ts=body["message"]["ts"]
                    )
                    
            except Exception as e:
                logger.error(f"Error handling reject_all: {e}", exc_info=True)
                await client.chat_postMessage(
                    text=f"❌ An error occurred: {str(e)}",
                    channel=body["channel"]["id"],
                    thread_ts=body["message"]["ts"]
                )
        
        @self.app.action("approve_action")
        async def handle_approve_action(ack, body, client: AsyncWebClient):
            """Handle individual action approval."""
            await ack()
            
            try:
                # Extract session_id and action_id from action
                action_value = body.get("actions", [{}])[0].get("value", "")
                parts = action_value.split(":")
                session_id = parts[1] if len(parts) > 1 else ""
                action_id = parts[2] if len(parts) > 2 else ""
                
                # Call the approval API
                success = await self._approve_actions(session_id, [action_id], "approve")
                
                if success:
                    await client.chat_postMessage(
                        text=f"✅ Action {action_id} approved.",
                        channel=body["channel"]["id"],
                        thread_ts=body["message"]["ts"]
                    )
                else:
                    await client.chat_postMessage(
                        text=f"❌ Failed to approve action {action_id}.",
                        channel=body["channel"]["id"],
                        thread_ts=body["message"]["ts"]
                    )
                    
            except Exception as e:
                logger.error(f"Error handling approve_action: {e}", exc_info=True)
        
        @self.app.action("reject_action")
        async def handle_reject_action(ack, body, client: AsyncWebClient):
            """Handle individual action rejection."""
            await ack()
            
            try:
                # Extract session_id and action_id from action
                action_value = body.get("actions", [{}])[0].get("value", "")
                parts = action_value.split(":")
                session_id = parts[1] if len(parts) > 1 else ""
                action_id = parts[2] if len(parts) > 2 else ""
                
                # Call the approval API
                success = await self._approve_actions(session_id, [action_id], "reject")
                
                if success:
                    await client.chat_postMessage(
                        text=f"❌ Action {action_id} rejected.",
                        channel=body["channel"]["id"],
                        thread_ts=body["message"]["ts"]
                    )
                else:
                    await client.chat_postMessage(
                        text=f"❌ Failed to reject action {action_id}.",
                        channel=body["channel"]["id"],
                        thread_ts=body["message"]["ts"]
                    )
                    
            except Exception as e:
                logger.error(f"Error handling reject_action: {e}", exc_info=True)
    
    async def _run_swarm(self, query: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Run the swarm via API."""
        try:
            response = await self.http_client.post(
                f"{API_BASE_URL}/api/swarm/run",
                json={"query": query, "user_id": user_id},
                timeout=60.0
            )
            if response.status_code == 200:
                return response.json()
        except httpx.RequestError as e:
            logger.error(f"Error running swarm: {e}")
        return None
    
    async def _get_swarm_status(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get swarm status via API."""
        try:
            response = await self.http_client.get(
                f"{API_BASE_URL}/api/swarm/status/{session_id}",
                timeout=10.0
            )
            if response.status_code == 200:
                return response.json()
        except httpx.RequestError as e:
            logger.error(f"Error getting swarm status: {e}")
        return None
    
    async def _approve_actions(
        self, 
        session_id: str, 
        action_ids: list, 
        decision: str
    ) -> bool:
        """Approve or reject actions via API."""
        try:
            response = await self.http_client.post(
                f"{API_BASE_URL}/api/swarm/approve",
                json={
                    "session_id": session_id,
                    "action_ids": action_ids,
                    "decision": decision
                },
                timeout=30.0
            )
            return response.status_code == 200
        except httpx.RequestError as e:
            logger.error(f"Error approving actions: {e}")
        return False
    
    def _start_polling(
        self, 
        session_id: str, 
        channel_id: str, 
        thread_ts: str,
        client: AsyncWebClient
    ):
        """Start polling for swarm status updates."""
        # Cancel any existing polling for this session
        if session_id in self.polling_tasks:
            self.polling_tasks[session_id].cancel()
        
        # Create new polling task
        task = asyncio.create_task(
            self._poll_for_updates(session_id, channel_id, thread_ts, client)
        )
        self.polling_tasks[session_id] = task
    
    async def _poll_for_updates(
        self, 
        session_id: str, 
        channel_id: str, 
        thread_ts: str,
        client: AsyncWebClient
    ):
        """Poll for swarm status updates and post them to Slack."""
        last_findings_count = 0
        last_conflicts_count = 0
        last_agent_statuses = {}
        
        try:
            while True:
                await asyncio.sleep(3)  # Poll every 3 seconds
                
                status = await self._get_swarm_status(session_id)
                if not status:
                    continue
                
                blackboard = status.get("blackboard", {})
                findings = blackboard.get("findings", [])
                conflicts = blackboard.get("conflicts", [])
                agent_statuses = blackboard.get("agent_statuses", {})
                
                # Check for new findings
                if len(findings) > last_findings_count:
                    new_findings = findings[last_findings_count:]
                    for finding in new_findings:
                        agent_id = finding.get("agent_id", "unknown")
                        summary = finding.get("summary", "Task completed")
                        confidence = finding.get("confidence", 0.0)
                        
                        emoji = "✅" if confidence >= 0.7 else "⚠️"
                        await client.chat_postMessage(
                            text=f"{emoji} *{agent_id}*: {summary}",
                            channel=channel_id,
                            thread_ts=thread_ts
                        )
                    last_findings_count = len(findings)
                
                # Check for new conflicts
                if len(conflicts) > last_conflicts_count:
                    new_conflicts = conflicts[last_conflicts_count:]
                    for conflict in new_conflicts:
                        description = conflict.get("description", "Conflict detected")
                        severity = conflict.get("severity", "warning")
                        
                        emoji = "🚨" if severity == "critical" else "⚠️"
                        await client.chat_postMessage(
                            text=f"{emoji} *Conflict Detected*: {description}",
                            channel=channel_id,
                            thread_ts=thread_ts
                        )
                    last_conflicts_count = len(conflicts)
                
                # Check for agent status changes
                for agent_id, status_val in agent_statuses.items():
                    if agent_id in last_agent_statuses:
                        if last_agent_statuses[agent_id] != status_val:
                            if status_val == "completed":
                                await client.chat_postMessage(
                                    text=f"✅ *{agent_id}*: Task completed",
                                    channel=channel_id,
                                    thread_ts=thread_ts
                                )
                            elif status_val == "failed":
                                await client.chat_postMessage(
                                    text=f"❌ *{agent_id}*: Task failed",
                                    channel=channel_id,
                                    thread_ts=thread_ts
                                )
                    last_agent_statuses[agent_id] = status_val
                
                # Check for critic review
                critic_review = status.get("critic_review")
                if critic_review and critic_review.get("findings_reviewed", 0) > 0:
                    findings_reviewed = critic_review.get("findings_reviewed", 0)
                    conflicts_detected = critic_review.get("conflicts_detected", 0)
                    await client.chat_postMessage(
                        text=f"🔍 *Critic Review*: Validated {findings_reviewed} findings, {conflicts_detected} conflicts detected",
                        channel=channel_id,
                        thread_ts=thread_ts
                    )
                    # Stop polling after critic review
                    break
                
                # Check for completion
                execution_phase = blackboard.get("execution_phase", "")
                if execution_phase == "completed":
                    await client.chat_postMessage(
                        text="✅ *Swarm execution complete*",
                        channel=channel_id,
                        thread_ts=thread_ts
                    )
                    break
                    
        except asyncio.CancelledError:
            logger.info(f"Polling cancelled for session {session_id}")
        except Exception as e:
            logger.error(f"Error polling for updates: {e}", exc_info=True)
        finally:
            if session_id in self.polling_tasks:
                del self.polling_tasks[session_id]
    
    async def _post_approval_message(
        self, 
        session_id: str, 
        channel_id: str, 
        thread_ts: str,
        pending_approvals: list,
        client: AsyncWebClient
    ):
        """Post a Block Kit message with approval buttons."""
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "📋 Actions Pending Approval",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{len(pending_approvals)} actions require your approval before execution.*"
                }
            },
            {"type": "divider"}
        ]
        
        # Add each action as a section
        for i, action in enumerate(pending_approvals[:5]):  # Limit to 5 actions
            action_type = action.get("action_type", "unknown")
            entity_fqn = action.get("entity_fqn", "unknown")
            confidence = action.get("confidence", 0.0)
            
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Action {i+1}*: `{action_type}` on `{entity_fqn}`\nConfidence: {confidence:.0%}"
                },
                "accessory": {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "✅"},
                    "action_id": "approve_action",
                    "value": f"approve:{session_id}:{i}"
                }
            })
        
        # Add approve/reject all buttons
        blocks.extend([
            {"type": "divider"},
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "✅ Approve All"},
                        "style": "primary",
                        "action_id": "approve_all",
                        "value": f"approve_all:{session_id}"
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "❌ Reject All"},
                        "style": "danger",
                        "action_id": "reject_all",
                        "value": f"reject_all:{session_id}"
                    }
                ]
            }
        ])
        
        try:
            await client.chat_postMessage(
                blocks=blocks,
                channel=channel_id,
                thread_ts=thread_ts
            )
        except Exception as e:
            logger.error(f"Error posting approval message: {e}", exc_info=True)
            # Fallback to simple message
            await client.chat_postMessage(
                text=f"📋 *{len(pending_approvals)} actions pending approval*\nUse the web interface to approve or reject.",
                channel=channel_id,
                thread_ts=thread_ts
            )
    
    async def start(self):
        """Start the Slack bot with Socket Mode."""
        handler = SocketModeHandler(self.app, os.getenv("SLACK_APP_TOKEN"))
        await handler.start_async()


def main():
    """Main entry point for the Slack bot."""
    logging.basicConfig(level=logging.INFO)
    
    # Check for required environment variables
    if not os.getenv("SLACK_BOT_TOKEN"):
        raise ValueError("SLACK_BOT_TOKEN environment variable is required")
    if not os.getenv("SLACK_SIGNING_SECRET"):
        raise ValueError("SLACK_SIGNING_SECRET environment variable is required")
    
    bot = OpenMetaMindSlackBot()
    
    print("Starting OpenMetaMind Slack bot...")
    print("Bot is ready and listening for @mentions!")
    
    # Start the bot
    asyncio.run(bot.start())


if __name__ == "__main__":
    main()