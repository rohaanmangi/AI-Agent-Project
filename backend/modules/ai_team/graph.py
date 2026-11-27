import os

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langgraph_supervisor import create_supervisor


# from core import settings  # noqa: F401  (loads .env)
from modules.ai_team.tools import list_files, read_file, web_search, write_file


MAX_DEVELOPER_PASSES = 3


# ponytail: both speak the OpenAI API, so one ChatOpenAI class covers both
LLMS = {
   "ollama": dict(
       base_url="http://localhost:11434/v1",
       api_key="ollama",
       model=os.getenv("OLLAMA_MODEL", "qwen3:4b")),
   "groq": dict(
       base_url="https://api.groq.com/openai/v1",
       api_key=os.getenv("GROQ_API_KEY"),
       model=os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")),
}


def create_chat_model(llm="groq"):
   # max_retries: free tiers hit tokens-per-minute limits; this waits them out
   return ChatOpenAI(**LLMS[llm], temperature=0, max_retries=6)


def build_team(model=None, docs_tools=()):
   model = model or create_chat_model()
   planner_tools = [list_files, read_file, *docs_tools] + ([web_search] if os.getenv("TAVILY_API_KEY") else [])

   docs_names = ", ".join(t.name for t in docs_tools)
   docs_hint = (f" Your Context7 documentation tools are: {docs_names}. "
                 "Use them for library docs.") if docs_tools else ""


   planner = create_agent(
       model, planner_tools, name="planner",
       system_prompt=("You are a Python planner. Read the request and any existing files. "
                      "Reply with short requirements, implementation steps and numbered "
                      "acceptance criteria. If you search the web, list source URLs. "
                      "Do not write code." + docs_hint),
   )
   developer = create_agent(
       model, [list_files, read_file, write_file, *docs_tools], name="developer",
       system_prompt=("You are a Python developer. Implement the plan by saving complete files "
                       "with write_file. Keep each file small (split large modules) and make "
                       "one write_file call per file, one at a time. "
                       "If the reviewer gave feedback, fix every point. "
                       "Reply with the files you changed. Never claim you ran the code." + docs_hint),
   )
   reviewer = create_agent(
       model, [list_files, read_file], name="reviewer",
       system_prompt=("You are a code reviewer. Read every file and check it against the "
                      "acceptance criteria and edge cases. Start your reply with exactly "
                      "APPROVED or CHANGES REQUESTED, then list specific fixes. "
                      "You cannot run code: never claim tests passed."),
   )


   return create_supervisor(
       agents=[planner, developer, reviewer],
       model=model,
       prompt=(
           "You manage a Python development team. You never write code yourself.\n"
           "1. New request -> planner.\n"
           "2. After a plan -> developer.\n"
           "3. After the developer saves files -> reviewer.\n"
           "4. CHANGES REQUESTED -> developer with the feedback.\n"
           f"5. Stop when APPROVED, or after {MAX_DEVELOPER_PASSES} developer passes.\n"
           "A revision request starts from the previous run's files: skip the planner if the change is small.\n"
           "Finish with a short summary: approved or draft, files changed, open feedback."
           + (f"\nThe planner and developer have these Context7 documentation tools: {docs_names}. "
               "If asked which tools exist, list them yourself. Send library documentation "
               "questions to the planner and pass on its answer; no developer or reviewer "
               "is needed for those." if docs_tools else "")
       ),
   ).compile()


if __name__ == "__main__":
   print(build_team().get_graph().draw_mermaid())   # show students the supervisor graph
