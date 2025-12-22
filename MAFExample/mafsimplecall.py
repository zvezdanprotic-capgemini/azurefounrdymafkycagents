# import asyncio
# from agent_framework.azure import AzureAIClient
# from azure.identity.aio import AzureCliCredential

# async def main():
#     async with (
#         AzureCliCredential() as credential,
#         AzureAIClient(async_credential=credential).create_agent(
#             instructions="You are good at telling jokes."
#         ) as agent,
#     ):
#         result = await agent.run("Tell me a joke about a pirate.")
#         print(result.text)

# if __name__ == "__main__":
#     asyncio.run(main())
import os
import asyncio
from agent_framework import ChatAgent
from agent_framework.azure import AzureOpenAIChatClient
from dotenv import load_dotenv

load_dotenv()

async def main():
    # Create a chat client using API key (no Entra ID, no AzureCliCredential)
    chat_client = AzureOpenAIChatClient(
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
            deployment_name=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME"),
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT")
    )  # reads env vars by default

    # Create the agent directly over the chat client
    async with ChatAgent(
        chat_client=chat_client,
        instructions="You are good at telling jokes."
    ) as agent:
        result = await agent.run("Tell me a joke about a pirate.")
        print(result.text)

if __name__ == "__main__":
    asyncio.run(main())
