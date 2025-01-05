import ast
from langchain_community.utilities.sql_database import SQLDatabase
from chatbot.chains.base import PromptTemplate, generate_prompt_templates
from pydantic import BaseModel
from langchain.tools import BaseTool
from langchain.schema.runnable.base import Runnable
from langchain_community.chat_models import ChatOpenAI
from langchain.output_parsers import PydanticOutputParser
from typing import Type
import sqlitecloud
from fuzzywuzzy import process

class FavAuthorGenreToInsert(BaseModel):
    field_to_insert: str
    value: str

class ExtractFavAuthorGenreToInsert(Runnable):
    def __init__(self, llm, memory=False):
        super().__init__()

        self.llm = llm

        con = sqlitecloud.connect("sqlitecloud://cikwryuhhz.g6.sqlite.cloud:8860/shelfmate.db?apikey=fxZSlHTpxWU109u7go8avF2RRHsZ43JUxDfarjdFpYg")
        cursor = con.cursor()
        cursor.execute("SELECT genre FROM genres")
        self.genres_list = [row[0] for row in cursor.fetchall()]
        cursor = con.cursor()
        cursor.execute("SELECT author_name FROM authors")
        self.authors_list = [row[0] for row in cursor.fetchall()]
        con.close()
        
        prompt_template = PromptTemplate(
            system_template = """
            You are a part of the database manager team for a book recommendation platform. 
            Given the user input, your task is to identify if the user wants to add a new favorite author or genre, and which author or genre they want to add.
            Return if they want to add a new favorite author or genre with just the word 'author' or 'genre'.

            The system will search for the author or genre in the database based on the name you extract from the user input. 
            Ensure you extract the author's name or genre as accurately as possible.
            You can also take into consideration the chat history between you and the user.

            Here is the user input:
            {user_input}

            Chat History:
            {chat_history}

            {format_instructions}
            """,
            human_template = "user input: {user_input}"
        )

        self.prompt = generate_prompt_templates(prompt_template, memory=memory)
        self.output_parser = PydanticOutputParser(pydantic_object=FavAuthorGenreToInsert)
        self.format_instructions = self.output_parser.get_format_instructions()

        self.chain = self.prompt | self.llm | self.output_parser


    def invoke(self, inputs):
        result = self.chain.invoke(
            {
                "user_input": inputs["user_input"],
                "chat_history": inputs["chat_history"],
                "format_instructions": self.format_instructions,
            })
        con = sqlitecloud.connect("sqlitecloud://cikwryuhhz.g6.sqlite.cloud:8860/shelfmate.db?apikey=fxZSlHTpxWU109u7go8avF2RRHsZ43JUxDfarjdFpYg")
        if result.field_to_insert == 'genre':
            closest_match, score = process.extractOne(result.value, self.genres_list)
            if score > 90:  
                result.value = closest_match
                cursor = con.cursor()
                query = f"SELECT genre_id, genre FROM genres WHERE genre = '{result.value}'"
                cursor.execute(query)
                results = cursor.fetchone()
                result.value = results[0]
            else:
                return 'Genre not found.'
            
            
        elif result.field_to_insert == 'author':
            closest_match, score = process.extractOne(result.value, self.authors_list)
            if score > 90:
                result.value = closest_match
                cursor = con.cursor()
                query = f"SELECT author_id, author_name FROM authors WHERE author_name = '{result.value}'"
                cursor.execute(query)
                results = cursor.fetchone()
                result.value = results[0]
            else:
                return 'Author not found.'
            
        con.close()
        return result

######################################################

class AddFavAuthorGenreOutput(BaseModel):
    output: str

class AddFavAuthorGenreChain(Runnable):

    def __init__(self, memory: bool = True) -> str:
        self.llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        self.extract_chain = ExtractFavAuthorGenreToInsert(self.llm)

        prompt_bot_return = PromptTemplate(
            system_template = """
            You are a part of the database manager team for a book recommendation platform called Shelfmate. 
            The user asked to add an author or genre to be added to their favorites list. 
            There are 3 possible outcomes:
            - The author or genre was successfully added to the favorites list (status='success').
            - The author or genre was already on the favorites list (status='no_change').
            - The user intention was not clear (status='error').
            
            Given the user input, the chat history and the operation status, your task is to return to the user a message stating the result of the operation in a friendly way \
            and guide the user to what more they can do on the platform. That includes adding books to their read list, adding genres \
            and authors to their favorites list, receiving suggestions of books and authors, and creating a reading plan.
            Do not greet the user in the beggining of the message as this is already in the middle of the conversation.
            
            Here is the user input:
            {user_input}
            
            Here is the chat history:
            {chat_history}

            Status of the operation:
            {status}

            {format_instructions}
            """,
            human_template = "user input: {user_input}"
        )

        self.prompt = generate_prompt_templates(prompt_bot_return, memory=memory)
        self.output_parser = PydanticOutputParser(pydantic_object=AddFavAuthorGenreOutput)
        self.format_instructions = self.output_parser.get_format_instructions()
        self.chain = (self.prompt | self.llm | self.output_parser).with_config({"run_name": self.__class__.__name__})

    def invoke(self, user_input, config):
        username = config.get('configurable').get('user_id')
        fav_info = self.extract_chain.invoke(user_input)
        con = sqlitecloud.connect("sqlitecloud://cikwryuhhz.g6.sqlite.cloud:8860/shelfmate.db?apikey=fxZSlHTpxWU109u7go8avF2RRHsZ43JUxDfarjdFpYg")
        cursor = con.cursor()

        # Checking if the author/genre already exists in the fav_authors/genres tables
        if fav_info.field_to_insert in ['author','genre']:
            field = fav_info.field_to_insert + '_id'
            table = 'fav_' + fav_info.field_to_insert + 's'
        else:
            self.status = 'error'
        cursor = con.cursor()
        cursor.execute(f"SELECT {field} FROM {table} WHERE username = ? AND {field} = ?", (username, fav_info.value))
        query_results = cursor.fetchone()
    
        if not query_results: # if does not exist already in the table
            try:
                cursor = con.cursor()
                cursor.execute(
                    f"INSERT INTO {table} (username, {field}) VALUES (?, ?)",
                    (username, fav_info.value),
                )
                con.commit()
                self.status = 'success'

            except sqlitecloud.OperationalError as e:
                print(f"Error: {e}")
                self.status = 'error'
            finally:
                cursor.close()
                con.close()
        else:
            if query_results[0]==fav_info.value:
                self.status = 'no_change'
        con.close()
        response = self.chain.invoke({
                "user_input": user_input['user_input'],
                'chat_history': user_input['chat_history'],
                "status": self.status,
                "format_instructions": self.format_instructions
            })

        return response.output