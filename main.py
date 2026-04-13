"""
A-share Investment Agent System - Main Entry Point
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "."))

def main():
    """Main function"""
    print("A-share Investment Agent System is starting...")
    print("Please run specific modules as needed:")
    print("- For data fetching: python -m src.data.api")
    print("- For agent execution: python -m src.agents.investment_agent")
    print("- For full analysis: python -m src.core.workflow")

if __name__ == "__main__":
    main()
