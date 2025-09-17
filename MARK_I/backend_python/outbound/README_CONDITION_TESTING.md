# 🧪 Condition Node Testing (No Voice Calls Required!)

Perfect for office testing! Test your condition node routing logic using text instead of voice calls.

## 🚀 Quick Start Options

### Option 1: Web Browser (Easiest!)
1. Open `test_condition_web.html` in any browser
2. Enter your condition and user message
3. See instant routing results!

### Option 2: Command Line (Quick)
```bash
cd MARK_I/backend_python/outbound
python run_condition_test.py "User wants appointment" "I need to schedule a meeting"
```

### Option 3: Full Test Suite
```bash
python test_condition_routing.py
# Choose option 1 for predefined scenarios or 2 for interactive mode
```

## 📋 Example Tests

### Appointment Routing
```bash
python run_condition_test.py "User needs appointment scheduling" "I want to book a meeting with Dr. Smith"
```
**Expected Result:** Routes to "Appointment Booking" with high confidence

### Technical Support
```bash
python run_condition_test.py "Customer has technical issues" "I'm having trouble logging into my account"
```
**Expected Result:** Routes to "Technical Support" with high confidence

### Sales Inquiry
```bash
python run_condition_test.py "User interested in purchasing" "What are your pricing options for enterprise?"
```
**Expected Result:** Routes to "Sales Team" with high confidence

## 🎯 What Gets Tested

✅ **Condition Analysis** - How well the AI understands your condition  
✅ **Keyword Matching** - Does it pick up on key terms?  
✅ **Confidence Scoring** - How sure is it about the routing decision?  
✅ **Multiple Targets** - Shows all possible routes ranked by confidence  
✅ **Reasoning** - Explains why each routing decision was made  

## 📊 Understanding Results

The test shows:
- **🎯 Best Route**: The top routing choice
- **Confidence %**: How confident the AI is (higher = better)
- **Reasoning**: Why this route was chosen
- **All Options**: Complete ranking of all possible routes

## 🔧 How It Works

The test simulates the exact same logic your condition nodes use in production:

1. **Analyzes Conversation**: Looks at user messages for routing signals
2. **Evaluates Condition**: Matches conversation against your condition statement  
3. **Scores Confidence**: Calculates how well each target fits
4. **Returns Best Route**: Selects the highest-confidence target

This gives you **immediate feedback** on how your condition nodes will behave in real calls!

## 💡 Pro Tips

- **Test Edge Cases**: Try messages that could go multiple ways
- **Check Confidence**: Aim for >70% confidence on your main scenarios
- **Refine Conditions**: Adjust your condition text based on test results
- **Test Variations**: Try different ways users might express the same intent

Perfect for rapid iteration and debugging your pathway logic! 🎉 