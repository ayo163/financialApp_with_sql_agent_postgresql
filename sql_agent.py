from langchain_openai import ChatOpenAI
from os import environ
import load_env_vars
from agent_toolkit import tools
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent

api_key = environ.get('OPENAI_API_KEY', '')



#MODEL
model = ChatOpenAI(model = 'gpt-4o-mini', api_key = api_key)


agent = create_agent(model =model, tools = tools)


question = "give me the list of account holders"

for step in agent.stream(
    {"messages": [{"role": "user", "content": question}]},
    stream_mode = "values"
): step['messages'][-1].pretty_print()