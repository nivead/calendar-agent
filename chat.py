# ── Phoenix setup FIRST, before warnings filter ──
import phoenix as px
from phoenix.otel import register
from openinference.instrumentation.langchain import LangChainInstrumentor

import warnings
warnings.filterwarnings("ignore")  # AFTER imports so errors aren't hidden

session = px.launch_app()

tracer_provider = register(
    project_name="cal-agent",
    endpoint="http://localhost:6006/v1/traces",
    protocol="http/protobuf",
)

LangChainInstrumentor().instrument(tracer_provider=tracer_provider)

# ── Now the rest ──
from datetime import datetime
from zoneinfo import ZoneInfo
from langchain_core.messages import HumanMessage
from agent.graph import owner_graph as graph


USER_TIMEZONE = "America/Los_Angeles"


def chat(thread_id: str = "default"):
    print("Calendar Agent ready. Type 'quit' to exit.\n")
    config = {"configurable": {"thread_id": thread_id}}

    while True:
        user_input = input("You: ").strip()
        if not user_input or user_input.lower() in ("quit", "exit"):
            print("Goodbye!")
            break

        now = datetime.now(ZoneInfo(USER_TIMEZONE))
        time_context = f"[Current time: {now.strftime('%A, %B %d %Y %I:%M %p %Z')}]"
        full_message = f"{time_context}\n\n{user_input}"

        print()
        final_reply = None

        for event in graph.stream(
            {"messages": [HumanMessage(content=full_message)]},
            config=config,
            stream_mode="updates",
        ):
            for node_name, node_output in event.items():
                messages = node_output.get("messages", [])
                for msg in messages:
                    msg_type = type(msg).__name__
                    if msg_type == "AIMessage":
                        if msg.tool_calls:
                            for tc in msg.tool_calls:
                                print(f"  [llm]   → {tc['name']}({tc['args']})")
                        else:
                            final_reply = msg.content
                    elif msg_type == "ToolMessage":
                        content = msg.content
                        if len(content) > 200:
                            content = content[:200] + "..."
                        print(f"  [tool]  ← {msg.name}: {content}")

        if final_reply:
            print(f"\nAgent: {final_reply}\n")


if __name__ == "__main__":
    chat()
