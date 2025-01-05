from chatbot.chains.base import PromptTemplate, generate_prompt_templates 
from chatbot.chains.suggest_authors_given_favourites import SuggestAuthorsGivenFavChain
from chatbot.chains.suggest_authors_given_input import SuggestAuthorsGivenInputChain
from pydantic import BaseModel
from langchain.tools import BaseTool
from langchain.schema.runnable.base import Runnable
from langchain_community.chat_models import ChatOpenAI
from langchain.output_parsers import PydanticOutputParser
from typing import Type
import openai
import sqlite3


class WhichInput_(BaseModel):
    fav_or_input: str


class ExtractInput_Authors(Runnable):
    def __init__(self, memory= False):
        super().__init__()
        self.llm = ChatOpenAI(model='gpt-4o-mini', temperature=0)
        prompt_template = PromptTemplate(
            system_template=""" 
            You are a part of a book recomendation system team. 
            The user will ask for a author recommendation.
            Your task is to identify if the user wants a suggestion based on a specific books, \
            authors or genres or if the user wants based on his favorites. 
            Return 'fav' if the user wants the recommendation based on his favorite books, authors or genre. \
            Return 'input' if the user wants the recommendation based on a specific book, author or genre.

            Here is the user input:
            {user_input}

            {format_instructions}
            """,
            human_template="user input: {user_input}",
        )

        self.prompt = generate_prompt_templates(prompt_template, memory=memory)
        self.output_parser = PydanticOutputParser(pydantic_object=WhichInput_)
        self.format_instructions = self.output_parser.get_format_instructions()

        self.chain = self.prompt | self.llm | self.output_parser


    def invoke(self, inputs, config):
        result = self.chain.invoke(
            {
                "user_input": inputs["user_input"],
                "format_instructions": self.format_instructions,
            })

        if result.fav_or_input == 'fav':
            chain = SuggestAuthorsGivenFavChain()
            response = chain.invoke(inputs, config)
        elif result.fav_or_input == 'input':
            chain = SuggestAuthorsGivenInputChain()
            response = chain.invoke(inputs, config)

        return response
  