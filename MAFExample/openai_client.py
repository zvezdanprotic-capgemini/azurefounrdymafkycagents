import os
from openai import AsyncAzureOpenAI
from dotenv import load_dotenv

load_dotenv()

client = AsyncAzureOpenAI(
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT")
)

async def get_llm_response(user_message: str) -> str:
    try:
        response = await client.chat.completions.create(
            model=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME"),
            messages=[{"role": "user", "content": user_message}]
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"OpenAI API error: {str(e)}")
        return "⚠️ Sorry, I couldn't process your request."

if __name__ == "__main__":
    import asyncio

    user_input = "Tell me a joke about a pirate."
    response = asyncio.run(get_llm_response(user_input))
    print(f"Response from LLM: {response}")