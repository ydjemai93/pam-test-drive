# 🎯 Multi-Agent Pathway Implementation Plan

## 📊 **Executive Summary**

Transform the current single WorkflowAgent system into a LiveKit-native multi-agent architecture where each pathway conversation node becomes a specialized agent class, with global context sharing and seamless transitions.

## 🎯 **Core Goals**

1. **LLM Accuracy**: Make AI decisions more focused and accurate through specialized agents
2. **True Node Transitions**: Actually move between pathway nodes (currently stays in same node)
3. **Seamless UX**: User sees one continuous agent (same voice, personality)
4. **Global Context**: Shared context across all pathway agents
5. **LiveKit Native**: Follow official LiveKit patterns and best practices

## 📁 **Files to be Created/Modified**

### 🆕 **New Files**

```
MARK_I/backend_python/agents/
├── multi_agent_pathway_system.py          # Main factory and coordination
├── specialized_pathway_agents.py          # Base classes and specialized agents
├── pathway_global_context.py              # Enhanced global context (existing, improve)
├── pathway_agent_factory.py               # Factory for creating agents from pathway config
├── test_multi_agent_pathways.py           # Comprehensive test suite
└── migration_helper.py                    # Helps migrate from single to multi-agent

supabase/migrations/
└── 20250131_add_global_pathway_context.sql  # Database schema enhancements

polymet-app/src/polymet/components/
└── global-prompt-editor.tsx               # Frontend component for global prompts
```

### 🔄 **Modified Files**

```
MARK_I/backend_python/agents/
├── workflow_agent.py                      # Adapt for multi-agent coordination
├── outbound_agent.py                      # Update agent creation logic
└── [workflow integration files]

MARK_I/backend_python/outbound/
└── agent.py                               # Update agent creation logic

polymet-app/src/polymet/
├── pages/pathway-builder.tsx               # Add global prompt editing
└── types/pathway.ts                       # Update type definitions
```

## 🗄️ **Database Schema Changes**

### **Enhanced Pathways Table**
```sql
ALTER TABLE pathways 
ADD COLUMN global_instructions TEXT,
ADD COLUMN brand_voice TEXT,
ADD COLUMN company_name TEXT,
ADD COLUMN agent_role TEXT,
ADD COLUMN global_context JSONB DEFAULT '{}';
```

### **Agent Session Tracking**
```sql
-- Track which agents are created for each pathway execution
ALTER TABLE pathway_executions
ADD COLUMN active_agent_type TEXT,
ADD COLUMN agent_context JSONB DEFAULT '{}',
ADD COLUMN agent_handoff_history JSONB DEFAULT '[]';
```

## 🏗️ **Implementation Phases**

### **Phase 1: Core Infrastructure** (Days 1-2)

#### **Step 1.1: Enhanced Global Context System**
- Improve existing `pathway_global_context.py`
- Add database schema for global prompts
- Create migration script

#### **Step 1.2: Agent Factory System**
- Create `pathway_agent_factory.py`
- Build dynamic agent class generation
- Map pathway nodes → agent classes

#### **Step 1.3: Database Migration**
- Add global context fields to pathways table
- Update existing pathway records
- Test data migration

### **Phase 2: Multi-Agent Core** (Days 3-4)

#### **Step 2.1: Specialized Agent Classes**
- Create base `PathwayAgent` class
- Implement conversation-specific agents
- Add function tools for transitions

#### **Step 2.2: Agent Coordination System**
- Build multi-agent orchestration
- Implement agent handoff logic
- Preserve chat context and userdata

#### **Step 2.3: Update Agent Creation Points**
- Modify `outbound_agent.py` to use factory
- Update `agent.py` creation logic
- Ensure backward compatibility

### **Phase 3: Frontend Integration** (Days 5-6)

#### **Step 3.1: Global Prompt Editor**
- Add global prompt UI to pathway builder
- Update pathway save/load logic
- Add validation for global context

#### **Step 3.2: Node Configuration Updates**
- Enhance node configuration for multi-agent
- Add agent specialization options
- Update pathway preview system

### **Phase 4: Testing & Validation** (Days 7-8)

#### **Step 4.1: Comprehensive Testing**
- Unit tests for agent factory
- Integration tests for handoffs
- End-to-end pathway tests

#### **Step 4.2: Migration Testing**
- Test existing pathway migration
- Verify backward compatibility
- Performance benchmarking

## 📝 **Detailed Implementation Specifications**

### **1. Pathway Agent Factory**

```python
class PathwayAgentFactory:
    """
    Creates specialized agents for each pathway conversation node.
    Follows LiveKit's recommended multi-agent pattern.
    """
    
    @staticmethod
    def create_pathway_session(pathway_config: Dict[str, Any]) -> AgentSession:
        """Create session with global context and initial agent"""
        
    @staticmethod  
    def create_specialized_agent(node_config: Dict, global_context: GlobalContext) -> Agent:
        """Create agent specialized for specific conversation node"""
        
    @staticmethod
    def get_agent_for_node_type(node_type: str) -> Type[Agent]:
        """Get agent class for specific node type"""
```

### **2. Specialized Agent Architecture**

```python
# Base agent for all pathway nodes
class BasePathwayAgent(Agent):
    def __init__(self, global_context, node_config, chat_ctx=None):
        # Combine global + node instructions
        combined_instructions = self._build_instructions(global_context, node_config)
        super().__init__(instructions=combined_instructions, chat_ctx=chat_ctx)

# Specialized agents for different conversation phases  
class GreetingAgent(BasePathwayAgent):
    """Specialized for greeting and initial assessment"""
    
class QualificationAgent(BasePathwayAgent):
    """Specialized for lead qualification"""
    
class BookingAgent(BasePathwayAgent):
    """Specialized for appointment booking"""
```

### **3. Global Context Integration**

```python
@dataclass
class PathwayGlobalContext:
    # Agent identity
    company_name: str = ""
    agent_name: str = ""
    agent_role: str = ""
    
    # Global instructions  
    global_instructions: str = ""
    brand_voice: str = ""
    
    # Pathway configuration
    pathway_config: Dict[str, Any] = field(default_factory=dict)
    
    # Runtime data
    customer_data: Dict[str, Any] = field(default_factory=dict)
    collected_information: Dict[str, Any] = field(default_factory=dict)
    conversation_history: List[str] = field(default_factory=list)
```

### **4. Agent Transition Logic**

```python
@function_tool()
async def transition_to_qualification(self, context: RunContext) -> Agent:
    """Transition from greeting to qualification phase"""
    global_ctx = context.session.userdata
    
    # Find qualification node from pathway config
    qualification_node = self._find_node_by_id('qualification_phase')
    
    # Create specialized qualification agent
    return QualificationAgent(
        global_context=global_ctx,
        node_config=qualification_node,
        chat_ctx=context.session.chat_ctx  # Preserve conversation
    )
```

## 🧪 **Testing Strategy**

### **Unit Tests**
- Agent factory creation logic
- Global context merging
- Function tool transitions
- Configuration validation

### **Integration Tests** 
- Agent handoff preservation
- Context sharing across agents
- Database integration
- Frontend pathway loading

### **End-to-End Tests**
- Complete pathway execution
- Multi-node conversation flows
- Error handling and recovery
- Performance under load

## 📈 **Backward Compatibility Plan**

### **Migration Strategy**
1. **Dual Mode Support**: Support both single and multi-agent pathways
2. **Gradual Migration**: Migrate pathways one by one
3. **Fallback Mechanism**: Fall back to single agent if multi-agent fails
4. **Configuration Detection**: Auto-detect pathway format

### **Legacy Support**
```python
def create_pathway_agent(pathway_config: Dict[str, Any]) -> Agent:
    """
    Smart agent creation that supports both legacy and new formats
    """
    if pathway_config.get('multi_agent_enabled', False):
        return PathwayAgentFactory.create_pathway_session(pathway_config)
    else:
        return WorkflowAgent(pathway_config)  # Legacy single agent
```

## 🚀 **Deployment Strategy**

### **Development Phase**
1. Feature flag for multi-agent pathways
2. Test with specific pathway IDs
3. Gradual rollout to test users

### **Production Rollout**
1. Deploy backend changes (backward compatible)
2. Update frontend with global prompt features  
3. Migrate existing pathways (optional)
4. Enable multi-agent by default for new pathways

## 📊 **Success Metrics**

### **Accuracy Improvements**
- Pathway completion rates
- Correct node transitions
- Function tool execution success
- User intent recognition accuracy

### **Performance Metrics**
- Agent handoff latency
- Memory usage per pathway
- Database query performance
- Overall call quality

### **User Experience**
- Seamless conversation flow
- No perceptible agent switches
- Improved conversation outcomes
- Reduced user frustration

## ⚠️ **Risk Mitigation**

### **Technical Risks**
- **Agent Handoff Failures**: Implement robust error handling and fallbacks
- **Context Loss**: Extensive testing of context preservation
- **Performance Impact**: Monitor resource usage and optimize

### **Business Risks**  
- **User Experience**: Thorough testing to ensure seamless experience
- **Migration Issues**: Comprehensive backup and rollback strategy
- **Compatibility**: Maintain full backward compatibility

## 🔄 **Rollback Plan**

### **Quick Rollback**
- Feature flag to disable multi-agent
- Automatic fallback to single WorkflowAgent
- No data loss or corruption

### **Full Rollback**
- Revert database migrations
- Restore original agent creation logic
- Maintain existing pathway configurations

---

## ✅ **Implementation Checklist**

### **Backend Development**
- [ ] Create agent factory system
- [ ] Implement specialized agent classes
- [ ] Add global context database fields
- [ ] Update agent creation points
- [ ] Implement function tool transitions
- [ ] Add comprehensive error handling

### **Database Changes**
- [ ] Create migration for global context
- [ ] Update pathway schema
- [ ] Test migration on sample data
- [ ] Create rollback scripts

### **Frontend Development**
- [ ] Add global prompt editor
- [ ] Update pathway builder UI
- [ ] Add multi-agent indicators
- [ ] Test pathway saving/loading

### **Testing**
- [ ] Unit tests for all components
- [ ] Integration tests for handoffs  
- [ ] End-to-end pathway tests
- [ ] Performance benchmarking
- [ ] User acceptance testing

### **Documentation**
- [ ] API documentation updates
- [ ] User guide for global prompts
- [ ] Migration guide
- [ ] Troubleshooting guide

---

This plan ensures a systematic, safe, and effective implementation of the multi-agent pathway system while maintaining the quality and reliability of your existing platform. 