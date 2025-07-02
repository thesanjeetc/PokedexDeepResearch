import os
from tavily import TavilyClient
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("TAVILY_API_KEY")
client = TavilyClient(api_key)


async def search_pokemon_wiki(query: str):
    response = client.search(
        query=query,
        search_depth="advanced",
        include_answer="advanced",
        chunks_per_source=5,
        include_domains=[
            "https://www.serebii.net/",
            "https://bulbapedia.bulbagarden.net/",
            "https://pokemondb.net/",
            "https://www.smogon.com/",
        ],
    )
    return response["answer"]
