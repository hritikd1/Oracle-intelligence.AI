import asyncio
import sys
import uvicorn
from dotenv import load_dotenv

load_dotenv()

async def main():
    print("=" * 60)
    print("🧠 STOCK INTELLIGENCE SYSTEM — MASTER ORCHESTRATOR")
    print("=" * 60)
    print()
    print("  Agents:")
    print("    🔍 News Scanner         — every 5 min")
    print("    📊 Market Analyzer      — every 2 hours")
    print("    💡 Opportunity Finder   — every 2 hours")
    print("    🔥 Trending Tracker     — every 15 min")
    print("    🇮🇳 Indian Market Tracker — every 10 min")
    print()
    print("  API Server: http://localhost:8000")
    print("  Dashboard:  http://localhost:3000")
    print("=" * 60)
    print()

    # Import agents
    from agents import start_all_agents

    # Create the FastAPI server config
    config = uvicorn.Config("api:app", host="0.0.0.0", port=8000, log_level="info")
    server = uvicorn.Server(config)

    # Run the API server and all agents concurrently
    try:
        await asyncio.gather(
            server.serve(),
            start_all_agents(),
        )
    except KeyboardInterrupt:
        print("\n⚠️ Shutting down system...")
    except Exception as e:
        print(f"\n❌ System error: {e}")
    finally:
        print("🛑 System stopped.")

if __name__ == '__main__':
    asyncio.run(main())