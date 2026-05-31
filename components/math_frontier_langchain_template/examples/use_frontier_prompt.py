from langchain_openai import ChatOpenAI
from math_frontier_templates import frontier_master_prompt, default_inputs

# Requires OPENAI_API_KEY or equivalent LangChain OpenAI setup.
llm = ChatOpenAI(model="gpt-4.1", temperature=0.2)
prompt = frontier_master_prompt()
messages = prompt.format_messages(**default_inputs())

print("--- Rendered prompt preview ---")
print(messages[-1].content[:4000])

# Uncomment to run:
# response = llm.invoke(messages)
# print(response.content)
