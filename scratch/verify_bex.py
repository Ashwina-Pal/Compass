import asyncio
from app.agent import registry_node, safety_gate

class MockContext:
    def __init__(self, user_id):
        self.user_id = user_id
        self.state = {}
        self.route = None
        
    async def run_node(self, agent, node_input):
        return "Mock response"

async def main():
    ctx = MockContext("bex")
    registry_node(ctx, "Hello")
    print(f"Bex Burnout Score: {ctx.state.get('burnout_risk_score')}")
    
    # safety_gate is a FunctionNode and wraps the function in _func
    await safety_gate._func(ctx, "Hello")
    print(f"Routes to hitl_pause: {ctx.route == 'hitl_pause'}")

if __name__ == "__main__":
    asyncio.run(main())
