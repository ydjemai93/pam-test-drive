#!/usr/bin/env python3
"""
Completely rewrite the fucked up _handle_transition_to_target method
"""

# Read the file
with open('pathway_global_context.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Define the clean method
clean_method = '''    async def _handle_transition_to_target(self, target_node_partial_id: str, transition_type: str) -> Agent:
        """
        Handle transition to target node following LiveKit workflow pattern.
        This method finds the actual target node and creates/returns the appropriate agent.
        """
        logger.info(f"🎯 Attempting transition from {self.node_config.get('id')} to {target_node_partial_id} ({transition_type})")
        
        # Find the actual target node in the pathway
        all_nodes = self.pathway_config.get('nodes', [])
        target_node = None
        
        # For app_action and end_call nodes, find by partial ID match
        if target_node_partial_id.startswith('app_action') or target_node_partial_id.startswith('end_call'):
            target_node = next((n for n in all_nodes if target_node_partial_id in n.get('id', '')), None)
        else:
            # For conversation nodes, find by exact ID
            target_node = next((n for n in all_nodes if n.get('id') == target_node_partial_id), None)
            
        if not target_node:
            logger.warning(f"❌ Target node {target_node_partial_id} not found in pathway")
            # Return self to stay in current node
            return self
        
        target_node_id = target_node.get('id')
        logger.info(f"✅ Found target node: {target_node_id}")
        
        # Update session tracking
        self.session_data.current_node_id = target_node_id
        
        # Get or create the target agent
        if target_node_id in self.session_data.agent_instances:
            target_agent = self.session_data.agent_instances[target_node_id]
            logger.info(f"✅ Using existing PathwayNodeAgent for: {target_node_id}")
        else:
            # Create new agent for this node
            target_agent = PathwayNodeAgent(
                node_config=target_node, 
                session_data=self.session_data,
                chat_ctx=None  # ✅ FIX: Use None instead of accessing session.chat_ctx
            )
            self.session_data.agent_instances[target_node_id] = target_agent
            logger.info(f"✅ Created new PathwayNodeAgent for: {target_node_id}")
        
        return target_agent'''

# Find the start and end of the method to replace
start_marker = "    async def _handle_transition_to_target(self, target_node_partial_id: str, transition_type: str) -> Agent:"
end_marker = "    async def on_enter(self):"

start_index = content.find(start_marker)
end_index = content.find(end_marker)

if start_index != -1 and end_index != -1:
    # Replace the method
    new_content = content[:start_index] + clean_method + "\n\n" + content[end_index:]
    
    # Write the fixed file
    with open('pathway_global_context.py', 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    print("✅ COMPLETELY REWROTE THE FUCKED UP METHOD!")
else:
    print("❌ Could not find method boundaries") 